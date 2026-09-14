import secrets
from functools import wraps
from flask import Blueprint, jsonify, g, request, session
from models import db, FileRecord, Folder, User
from services.file_service import FileService
from services.folder_service import FolderService
from .decorators import login_required

api_bp = Blueprint("api", __name__)


# ---------- dekorator dla tokenów (używany przez Koloseum) ----------
def require_api_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-API-Token")
        if not token:
            return jsonify({"error": "Brak tokenu"}), 401
        user = User.query.filter_by(api_token=token).first()
        if not user:
            return jsonify({"error": "Nieprawidłowy token"}), 403
        return f(user, *args, **kwargs)
    return decorated


# ---------- dekorator "token LUB sesja" — dla endpointów, z których
# korzysta panel Koloseum (X-API-Token), ale które mogłyby też kiedyś
# przydać się we froncie samego FileVault (sesja) ----------
def require_api_user(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("X-API-Token")
        if token:
            user = User.query.filter_by(api_token=token).first()
            if not user:
                return jsonify({"error": "Nieprawidłowy token"}), 403
        elif "user_id" in session:
            user = User.query.get(session["user_id"])
            if not user or not user.is_active:
                return jsonify({"error": "Brak autoryzacji"}), 401
        else:
            return jsonify({"error": "Brak autoryzacji"}), 401
        return f(user, *args, **kwargs)
    return decorated


# ---------- endpointy dla Koloseum (token) ----------
@api_bp.route("/verify")
@require_api_token
def verify(user):
    """Koloseum weryfikuje czy token jest ważny."""
    return jsonify({
        "valid": True,
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
    })


# ---------- zarządzanie tokenem (sesja użytkownika FileVault) ----------
@api_bp.route("/token/generate", methods=["POST"])
@login_required
def generate_token():
    """Użytkownik generuje sobie token w panelu FileVault."""
    g.user.api_token = secrets.token_hex(32)
    db.session.commit()
    return jsonify({"token": g.user.api_token})


@api_bp.route("/token/revoke", methods=["POST"])
@login_required
def revoke_token():
    g.user.api_token = None
    db.session.commit()
    return jsonify({"revoked": True})


@api_bp.route("/token/status")
@login_required
def token_status():
    has_token = g.user.api_token is not None
    return jsonify({
        "has_token": has_token,
        "token_preview": g.user.api_token[:8] + "..." if has_token else None,
    })


# ---------- listing plików/folderów (token LUB sesja) ----------
@api_bp.route("/files")
@require_api_user
def api_files(user):
    query = FileRecord.query.filter_by(user_id=user.id).order_by(FileRecord.created_at.desc())
    limit = request.args.get("limit", type=int)
    if limit:
        query = query.limit(limit)
    files = query.all()
    return jsonify([{
        "id": f.id,
        "name": f.original_name,
        "extension": f.extension,
        "size": f.size_bytes,
        "size_human": f.size_human,
        "folder_id": f.folder_id,
        "share_url": f.share_url,
        "share_active": f.is_share_active,
        "has_thumbnail": f.has_thumbnail,
        "is_previewable": f.is_previewable,
        "created_at": f.created_at.isoformat(),
    } for f in files])


@api_bp.route("/folders")
@require_api_user
def api_folders(user):
    query = Folder.query.filter_by(user_id=user.id)
    if request.args.get("shared") == "1":
        query = query.filter(Folder.share_token.isnot(None))
    folders = query.order_by(Folder.name).all()
    if request.args.get("shared") == "1":
        folders = [f for f in folders if f.is_share_active]
    return jsonify([{
        "id": f.id,
        "name": f.name,
        "parent_id": f.parent_id,
        "full_path": f.full_path,
        "file_count": f.file_count,
        "share_url": f.share_url,
        "share_active": f.is_share_active,
        "created_at": f.created_at.isoformat(),
    } for f in folders])


# ---------- panel "Wybierz z FileVault" w Koloseum ----------
@api_bp.route("/browse")
@require_api_user
def api_browse(user):
    """Zwraca w jednym wywołaniu: ostatnio dodane pliki użytkownika oraz
    jego foldery, które są aktualnie udostępnione (mają aktywny link).
    Używane przez panel szybkiego wyboru w Koloseum, żeby nie trzeba było
    ręcznie kopiować i wklejać linków."""
    recent_files = (
        FileRecord.query.filter_by(user_id=user.id)
        .order_by(FileRecord.created_at.desc())
        .limit(15)
        .all()
    )
    all_folders = Folder.query.filter_by(user_id=user.id).order_by(Folder.name).all()
    shared_folders = [f for f in all_folders if f.is_share_active]

    return jsonify({
        "recent_files": [{
            "id": f.id,
            "name": f.original_name,
            "extension": f.extension,
            "size_human": f.size_human,
            "folder_id": f.folder_id,
            "share_url": f.share_url,
            "share_active": f.is_share_active,
            "is_previewable": f.is_previewable,
            "created_at": f.created_at.isoformat(),
        } for f in recent_files],
        "shared_folders": [{
            "id": f.id,
            "name": f.name,
            "full_path": f.full_path,
            "file_count": f.file_count,
            "share_url": f.share_url,
            "created_at": f.created_at.isoformat(),
        } for f in shared_folders],
        "all_folders": [{
            "id": f.id,
            "name": f.name,
            "full_path": f.full_path,
            "file_count": f.file_count,
            "share_url": f.share_url,
            "share_active": f.is_share_active,
        } for f in all_folders],
    })


# ---------- "szybkie udostępnienie" — Koloseum woła to, gdy user wybierze
# w panelu plik/folder, który nie ma jeszcze aktywnego linku share ----------
@api_bp.route("/files/<int:file_id>/quick-share", methods=["POST"])
@require_api_user
def api_quick_share_file(user, file_id):
    record = FileRecord.query.filter_by(id=file_id, user_id=user.id).first()
    if not record:
        return jsonify({"error": "Nie znaleziono pliku"}), 404
    if not record.is_share_active:
        # expires_hours=0 -> bez wygaśnięcia, bez hasła: materiał ma zostać
        # dostępny dla studentów przez czas trwania przedmiotu.
        FileService.create_share(record, expires_hours=0)
    return jsonify({"share_url": record.share_url})


@api_bp.route("/folders/<int:folder_id>/quick-share", methods=["POST"])
@require_api_user
def api_quick_share_folder(user, folder_id):
    folder = Folder.query.filter_by(id=folder_id, user_id=user.id).first()
    if not folder:
        return jsonify({"error": "Nie znaleziono folderu"}), 404
    if not folder.is_share_active:
        FolderService.create_share(folder, expires_hours=0)
    return jsonify({"share_url": folder.share_url})