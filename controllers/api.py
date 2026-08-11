import secrets
from functools import wraps
from flask import Blueprint, jsonify, g, request
from models import db, FileRecord, Folder, User
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


# ---------- istniejące endpointy (bez zmian) ----------
@api_bp.route("/files")
@login_required
def api_files():
    files = FileRecord.query.filter_by(user_id=g.user.id).all()
    return jsonify([{
        "id": f.id,
        "name": f.original_name,
        "size": f.size_bytes,
        "size_human": f.size_human,
        "folder_id": f.folder_id,
        "share_url": f.share_url,
        "share_active": f.is_share_active,
        "has_thumbnail": f.has_thumbnail,
        "created_at": f.created_at.isoformat(),
    } for f in files])


@api_bp.route("/folders")
@login_required
def api_folders():
    folders = Folder.query.filter_by(user_id=g.user.id).order_by(Folder.name).all()
    return jsonify([{
        "id": f.id,
        "name": f.name,
        "parent_id": f.parent_id,
        "full_path": f.full_path,
        "file_count": f.file_count,
        "created_at": f.created_at.isoformat(),
    } for f in folders])