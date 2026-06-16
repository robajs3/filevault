from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, g
from models import Folder, FileRecord, db
from services import FolderService
from .decorators import login_required

folders_bp = Blueprint("folders", __name__)


def _get_user_folder(folder_id: int) -> Folder:
    folder = db.session.get(Folder, folder_id)
    if not folder or folder.user_id != g.user.id:
        abort(404)
    return folder


@folders_bp.route("/folder/create", methods=["POST"])
@login_required
def create_folder():
    name = request.form.get("name", "").strip()
    parent_id = request.form.get("parent_id", "").strip()

    parent_folder = None
    if parent_id and parent_id.isdigit():
        parent_folder = Folder.query.filter_by(id=int(parent_id), user_id=g.user.id).first()
        if not parent_folder:
            flash("Folder nadrzędny nie istnieje.", "danger")
            return redirect(url_for("files.dashboard"))

    folder, error = FolderService.create(
        user_id=g.user.id,
        name=name,
        parent_id=parent_folder.id if parent_folder else None,
    )
    if error:
        flash(error, "warning" if "już istnieje" in error else "danger")
    else:
        flash(f"Folder '{name}' został utworzony.", "success")

    if parent_folder:
        return redirect(url_for("folders.folder_view", folder_id=parent_folder.id))
    return redirect(url_for("files.dashboard"))


@folders_bp.route("/folder/<int:folder_id>")
@login_required
def folder_view(folder_id):
    folder = _get_user_folder(folder_id)
    subfolders = Folder.query.filter_by(user_id=g.user.id, parent_id=folder_id).order_by(Folder.name).all()
    files = FileRecord.query.filter_by(user_id=g.user.id, folder_id=folder_id).order_by(FileRecord.created_at.desc()).all()
    all_folders = Folder.query.filter_by(user_id=g.user.id).order_by(Folder.name).all()

    breadcrumbs = []
    node = folder
    while node:
        breadcrumbs.insert(0, node)
        node = db.session.get(Folder, node.parent_id) if node.parent_id else None

    return render_template(
        "dashboard.html",
        files=files,
        folders=subfolders,
        all_folders=all_folders,
        current_folder=folder,
        breadcrumbs=breadcrumbs,
        user=g.user,
    )


@folders_bp.route("/folder/<int:folder_id>/rename", methods=["POST"])
@login_required
def rename_folder(folder_id):
    folder = _get_user_folder(folder_id)
    ok, error = FolderService.rename(folder, request.form.get("name", "").strip())
    flash(error if error else "Folder został przemianowany.", "warning" if error else "success")
    if folder.parent_id:
        return redirect(url_for("folders.folder_view", folder_id=folder.parent_id))
    return redirect(url_for("files.dashboard"))


@folders_bp.route("/folder/<int:folder_id>/delete", methods=["POST"])
@login_required
def delete_folder(folder_id):
    folder = _get_user_folder(folder_id)
    parent_id = folder.parent_id
    name = folder.name
    FolderService.delete(folder)
    flash(f"Folder '{name}' i jego zawartość zostały usunięte.", "success")
    if parent_id:
        return redirect(url_for("folders.folder_view", folder_id=parent_id))
    return redirect(url_for("files.dashboard"))


@folders_bp.route("/folder/<int:folder_id>/move", methods=["POST"])
@login_required
def move_folder(folder_id):
    folder = _get_user_folder(folder_id)
    target_id = request.form.get("parent_id", "").strip()
    new_parent_id = int(target_id) if target_id and target_id.isdigit() else None

    ok, error = FolderService.move(folder, new_parent_id)
    if error:
        flash(error, "danger")
    else:
        flash("Folder przeniesiony.", "success")
    return redirect(url_for("folders.folder_view", folder_id=folder_id))