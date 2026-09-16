import secrets
from functools import wraps
from flask import Blueprint, jsonify, g, request, session
from models import db, FileRecord, Folder, User
from models.room import RoomMembership, RoomFile
from models.share_url import build_share_url
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
        "thumbnail_url": f.thumbnail_url,
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


def _file_json(f: FileRecord) -> dict:
    return {
        "id": f.id,
        "name": f.original_name,
        "extension": f.extension,
        "size_human": f.size_human,
        "folder_id": f.folder_id,
        "share_url": f.share_url,
        "share_active": f.is_share_active,
        "has_thumbnail": f.has_thumbnail,
        "thumbnail_url": f.thumbnail_url,
        "is_previewable": f.is_previewable,
        "created_at": f.created_at.isoformat(),
    }


def _folder_json(f: Folder) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "parent_id": f.parent_id,
        "full_path": f.full_path,
        "file_count": f.file_count,
        "share_url": f.share_url,
        "share_active": f.is_share_active,
        "created_at": f.created_at.isoformat(),
    }


# ---------- panel "Dysk" / "Wybierz z FileVault" w Koloseum ----------
@api_bp.route("/browse")
@require_api_user
def api_browse(user):
    """Zwraca w jednym wywołaniu: ostatnio dodane pliki użytkownika,
    WSZYSTKIE jego pliki (nie tylko udostępnione — panel "Dysk" w Koloseum
    ma pokazywać całe konto, a nie wyłącznie to, co już ma aktywny link),
    oraz jego foldery (też wszystkie, z parent_id do budowy drzewa).
    Używane przez panel szybkiego wyboru w Koloseum, żeby nie trzeba było
    ręcznie kopiować i wklejać linków."""
    all_files_query = (
        FileRecord.query.filter_by(user_id=user.id)
        .order_by(FileRecord.created_at.desc())
    )
    recent_files = all_files_query.limit(15).all()
    all_files = all_files_query.all()
    all_folders = Folder.query.filter_by(user_id=user.id).order_by(Folder.name).all()
    shared_folders = [f for f in all_folders if f.is_share_active]

    return jsonify({
        "recent_files": [_file_json(f) for f in recent_files],
        "all_files": [_file_json(f) for f in all_files],
        "shared_folders": [{
            "id": f.id,
            "name": f.name,
            "full_path": f.full_path,
            "file_count": f.file_count,
            "share_url": f.share_url,
            "created_at": f.created_at.isoformat(),
        } for f in shared_folders],
        "all_folders": [_folder_json(f) for f in all_folders],
    })


# ---------- zawartość konkretnego folderu (drill-down w panelu "Dysk") ----------
@api_bp.route("/folders/<int:folder_id>/files")
@require_api_user
def api_folder_files(user, folder_id):
    """Zwraca WSZYSTKIE pliki i podfoldery leżące bezpośrednio w danym
    folderze użytkownika — niezależnie od tego, czy mają aktywny link
    udostępniania. Panel "Dysk" w Koloseum używa tego do przeglądania
    zawartości folderu (klik na folder -> lista jego plików), a nie tylko
    tworzenia linku do całego folderu naraz."""
    folder = Folder.query.filter_by(id=folder_id, user_id=user.id).first()
    if not folder:
        return jsonify({"error": "Nie znaleziono folderu"}), 404

    files = FileRecord.query.filter_by(user_id=user.id, folder_id=folder_id).order_by(FileRecord.created_at.desc()).all()
    subfolders = Folder.query.filter_by(user_id=user.id, parent_id=folder_id).order_by(Folder.name).all()

    breadcrumbs = []
    node = folder
    while node:
        breadcrumbs.insert(0, {"id": node.id, "name": node.name})
        node = db.session.get(Folder, node.parent_id) if node.parent_id else None

    return jsonify({
        "folder": _folder_json(folder),
        "breadcrumbs": breadcrumbs,
        "files": [_file_json(f) for f in files],
        "subfolders": [_folder_json(f) for f in subfolders],
    })


# ---------- pliki udostępnione w pokojach, do których należy user ----------
@api_bp.route("/rooms/shared-files")
@require_api_user
def api_rooms_shared_files(user):
    """Zwraca pokoje (Room), do których user należy, razem ze wszystkimi
    plikami w nich udostępnionymi (z całego drzewa podfolderów pokoju,
    spłaszczone, z podaną ścieżką). Panel "Dysk" w Koloseum pokazuje to
    jako zakładkę "Pokoje". Linki do plików prowadzą do zwykłych,
    sesyjnych endpointów FileVault (nie trzeba tworzyć osobnego publicznego
    share_token) — każdy członek pokoju i tak ma do nich dostęp, patrz
    controllers/files.py:_get_file_with_access."""
    memberships = RoomMembership.query.filter_by(user_id=user.id).all()
    rooms_out = []
    for m in memberships:
        room = m.room
        room_files = RoomFile.query.filter_by(room_id=room.id).order_by(RoomFile.uploaded_at.desc()).all()
        files_out = []
        for rf in room_files:
            record = rf.file_record
            if not record:
                continue
            folder_path = rf.room_folder.full_path if rf.folder_id and rf.room_folder else None
            files_out.append({
                "id": record.id,
                "room_file_id": rf.id,
                "name": record.original_name,
                "extension": record.extension,
                "size_human": record.size_human,
                "folder_path": folder_path,
                "uploaded_by": rf.uploaded_by.username if rf.uploaded_by else None,
                "uploaded_at": rf.uploaded_at.isoformat() if rf.uploaded_at else None,
                "is_previewable": record.is_previewable,
                "has_thumbnail": record.has_thumbnail,
                "thumbnail_url": build_share_url("files.thumbnail", file_id=record.id) if record.has_thumbnail else None,
                "download_url": build_share_url("files.download_own", file_id=record.id),
                "preview_url": build_share_url("files.preview_file", file_id=record.id) if record.is_previewable else None,
            })
        rooms_out.append({
            "id": room.id,
            "name": room.name,
            "role": m.role,
            "file_count": len(files_out),
            "files": files_out,
        })
    return jsonify({"rooms": rooms_out})


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