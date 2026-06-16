import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, abort, g
from models import FileRecord, Folder, db
from services import FileService
from .decorators import login_required
from models.file_record import PREVIEW_MIME_MAP

files_bp = Blueprint("files", __name__)


@files_bp.route("/")
@login_required
def dashboard():
    folders = Folder.query.filter_by(user_id=g.user.id, parent_id=None).order_by(Folder.name).all()
    files = FileRecord.query.filter_by(user_id=g.user.id, folder_id=None).order_by(FileRecord.created_at.desc()).all()
    all_folders = Folder.query.filter_by(user_id=g.user.id).order_by(Folder.name).all()
    return render_template("dashboard.html", files=files, folders=folders,
                           all_folders=all_folders, current_folder=None, user=g.user)


@files_bp.route("/upload", methods=["POST"])
@login_required
def upload():
    if "file" not in request.files:
        flash("Brak pliku.", "danger")
        return redirect(url_for("files.dashboard"))

    folder_id = request.form.get("folder_id", "").strip()
    target_folder = None
    if folder_id and folder_id.isdigit():
        target_folder = Folder.query.filter_by(id=int(folder_id), user_id=g.user.id).first()

    uploaded = 0
    for f in request.files.getlist("file"):
        record, error = FileService.save_upload(f, g.user, target_folder.id if target_folder else None)
        if error:
            flash(error, "warning" if "typ" in error else "danger")
            if "limit" in error:
                break
        else:
            uploaded += 1

    if uploaded:
        flash(f"Przesłano {uploaded} plik(ów).", "success")

    if target_folder:
        return redirect(url_for("folders.folder_view", folder_id=target_folder.id))
    return redirect(url_for("files.dashboard"))


@files_bp.route("/file/<int:file_id>/download")
@login_required
def download_own(file_id):
    record = FileRecord.query.filter_by(id=file_id, user_id=g.user.id).first_or_404()
    path = FileService.physical_path(record)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, download_name=record.original_name, as_attachment=True)


@files_bp.route("/file/<int:file_id>/thumbnail")
@login_required
def thumbnail(file_id):
    record = FileRecord.query.filter_by(id=file_id, user_id=g.user.id).first_or_404()
    if not record.has_thumbnail:
        abort(404)
    path = FileService.thumbnail_path(record)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="image/webp")


@files_bp.route("/file/<int:file_id>/preview")
@login_required
def preview_file(file_id):
    record = FileRecord.query.filter_by(id=file_id, user_id=g.user.id).first_or_404()
    if not record.is_previewable:
        abort(404)
    path = FileService.physical_path(record)
    if not os.path.exists(path):
        abort(404)
    mime = PREVIEW_MIME_MAP.get(record.extension, record.mime_type or "application/octet-stream")
    return send_file(path, mimetype=mime, as_attachment=False, conditional=True)


@files_bp.route("/file/<int:file_id>/delete", methods=["POST"])
@login_required
def delete_file(file_id):
    record = FileRecord.query.filter_by(id=file_id, user_id=g.user.id).first_or_404()
    folder_id = record.folder_id
    FileService.delete(record)
    flash("Plik usunięty.", "success")
    if folder_id:
        return redirect(url_for("folders.folder_view", folder_id=folder_id))
    return redirect(url_for("files.dashboard"))


@files_bp.route("/file/<int:file_id>/rename", methods=["POST"])
@login_required
def rename_file(file_id):
    record = FileRecord.query.filter_by(id=file_id, user_id=g.user.id).first_or_404()
    ok, error = FileService.rename(record, request.form.get("name", "").strip())
    flash(error if error else "Nazwa pliku została zmieniona.", "danger" if error else "success")
    if record.folder_id:
        return redirect(url_for("folders.folder_view", folder_id=record.folder_id))
    return redirect(url_for("files.dashboard"))


@files_bp.route("/file/<int:file_id>/move", methods=["POST"])
@login_required
def move_file(file_id):
    record = FileRecord.query.filter_by(id=file_id, user_id=g.user.id).first_or_404()
    target_id = request.form.get("folder_id", "").strip()

    if target_id and target_id.isdigit():
        target_folder = Folder.query.filter_by(id=int(target_id), user_id=g.user.id).first()
        if not target_folder:
            flash("Folder nie istnieje.", "danger")
            return redirect(url_for("files.dashboard"))
        FileService.move(record, target_folder)
        flash(f"Plik przeniesiony do '{target_folder.name}'.", "success")
    else:
        FileService.move(record, None)
        flash("Plik przeniesiony do katalogu głównego.", "success")

    redirect_to = request.form.get("redirect_to", "")
    if redirect_to and redirect_to.isdigit():
        return redirect(url_for("folders.folder_view", folder_id=int(redirect_to)))
    return redirect(url_for("files.dashboard"))


@files_bp.route("/file/<int:file_id>/share", methods=["POST"])
@login_required
def share_file(file_id):
    record = FileRecord.query.filter_by(id=file_id, user_id=g.user.id).first_or_404()
    FileService.create_share(
        record,
        expires_hours=int(request.form.get("expires_hours", 24)),
        password=request.form.get("share_password", "").strip(),
        download_limit=request.form.get("download_limit", "").strip(),
    )
    flash(f"Link do udostępniania: {record.share_url}", "success")
    if record.folder_id:
        return redirect(url_for("folders.folder_view", folder_id=record.folder_id))
    return redirect(url_for("files.dashboard"))


@files_bp.route("/file/<int:file_id>/unshare", methods=["POST"])
@login_required
def unshare_file(file_id):
    record = FileRecord.query.filter_by(id=file_id, user_id=g.user.id).first_or_404()
    folder_id = record.folder_id
    FileService.revoke_share(record)
    flash("Udostępnianie wyłączone.", "info")
    if folder_id:
        return redirect(url_for("folders.folder_view", folder_id=folder_id))
    return redirect(url_for("files.dashboard"))