import io
import os
import zipfile
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, abort, session, current_app
from werkzeug.security import check_password_hash
from models import FileRecord, Folder, db
from services.audit_service import log_action

share_bp = Blueprint("share", __name__)


@share_bp.route("/s/<token>", methods=["GET", "POST"])
def download_shared(token):
    record = FileRecord.query.filter_by(share_token=token).first_or_404()
    if not record.is_share_active:
        abort(410)

    if record.share_password_hash:
        if request.method == "POST":
            pwd = request.form.get("password", "")
            if not check_password_hash(record.share_password_hash, pwd):
                flash("Błędne hasło.", "danger")
                return render_template("share_password.html", token=token, file=record)
        else:
            return render_template("share_password.html", token=token, file=record)

    from flask import current_app
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], record.stored_name)
    if not os.path.exists(path):
        abort(404)

    record.download_count += 1
    db.session.commit()
    log_action("shared_download", detail=record.original_name, user_id=record.user_id)
    return send_file(path, download_name=record.original_name, as_attachment=True)

# ── Widok publiczny folderu ────────────────────────────────────────────────────

@share_bp.route("/sf/<token>", methods=["GET", "POST"])
def shared_folder(token):
    folder = Folder.query.filter_by(share_token=token).first_or_404()
    if not folder.is_share_active:
        abort(410)

    # Sprawdzenie hasła
    session_key = f"folder_auth_{token}"
    if folder.share_password_hash:
        if not session.get(session_key):
            if request.method == "POST":
                pwd = request.form.get("password", "")
                if not check_password_hash(folder.share_password_hash, pwd):
                    flash("Błędne hasło.", "danger")
                    return render_template("shared_folder_password.html", token=token, folder=folder)
                session[session_key] = True
            else:
                return render_template("shared_folder_password.html", token=token, folder=folder)

    files = FileRecord.query.filter_by(folder_id=folder.id).order_by(FileRecord.original_name).all()
    return render_template("shared_folder.html", folder=folder, files=files, token=token)


@share_bp.route("/sf/<token>/download", methods=["POST"])
def shared_folder_download(token):
    folder = Folder.query.filter_by(share_token=token).first_or_404()
    if not folder.is_share_active:
        abort(410)

    # Weryfikacja hasła (sesja)
    session_key = f"folder_auth_{token}"
    if folder.share_password_hash and not session.get(session_key):
        abort(403)

    # Które pliki pobrać
    selected_ids = request.form.getlist("file_ids")
    all_files = FileRecord.query.filter_by(folder_id=folder.id).all()

    if selected_ids:
        ids = {int(i) for i in selected_ids if i.isdigit()}
        files_to_pack = [f for f in all_files if f.id in ids]
    else:
        files_to_pack = all_files

    if not files_to_pack:
        abort(400)

    upload_folder = current_app.config["UPLOAD_FOLDER"]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for record in files_to_pack:
            path = os.path.join(upload_folder, record.stored_name)
            if os.path.exists(path):
                zf.write(path, arcname=record.original_name)
    buf.seek(0)

    log_action("shared_folder_download", detail=folder.name, user_id=folder.user_id)
    safe_name = "".join(c if c.isalnum() or c in ("-", "_", " ") else "_" for c in folder.name)
    return send_file(
        buf,
        download_name=f"{safe_name}.zip",
        as_attachment=True,
        mimetype="application/zip",
    )