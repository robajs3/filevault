from flask import Blueprint, jsonify, g
from models import FileRecord, Folder
from .decorators import login_required

api_bp = Blueprint("api", __name__)


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
