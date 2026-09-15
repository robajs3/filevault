import io
import os
import zipfile
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, abort, session, current_app
from werkzeug.security import check_password_hash
from models import FileRecord, Folder, db
from models.room import Room, RoomFolder, RoomFile
from models.file_record import PREVIEW_MIME_MAP
from services.audit_service import log_action

share_bp = Blueprint("share", __name__)


def _send_shared_file(record: FileRecord, log_detail: str):
    """Wspólna logika wysyłki pojedynczego pliku ze wszystkich publicznych
    widoków udostępniania (plik/folder prywatny, root pokoju, folder pokoju)."""
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], record.stored_name)
    if not os.path.exists(path):
        abort(404)
    record.download_count += 1
    db.session.commit()
    log_action("shared_file_download", detail=log_detail, user_id=record.user_id)
    return send_file(path, download_name=record.original_name, as_attachment=True)


def _preview_shared_file(record: FileRecord):
    """Serwuje plik inline (bez wymuszania pobrania, bez liczenia do
    download_count) — do podglądu obrazów/PDF/wideo/audio w przeglądarce."""
    if not record.is_previewable:
        abort(404)
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], record.stored_name)
    if not os.path.exists(path):
        abort(404)
    mime = PREVIEW_MIME_MAP.get(record.extension, record.mime_type or "application/octet-stream")
    return send_file(path, mimetype=mime, as_attachment=False, conditional=True)


def _zip_files(files, archive_name: str, log_action_name: str, log_detail: str, log_user_id):
    """Wspólna logika pakowania wybranych plików w ZIP dla widoków folderowych."""
    if not files:
        abort(400)
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for record in files:
            path = os.path.join(upload_folder, record.stored_name)
            if os.path.exists(path):
                zf.write(path, arcname=record.original_name)
    buf.seek(0)
    log_action(log_action_name, detail=log_detail, user_id=log_user_id)
    safe_name = "".join(c if c.isalnum() or c in ("-", "_", " ") else "_" for c in archive_name)
    return send_file(buf, download_name=f"{safe_name}.zip", as_attachment=True, mimetype="application/zip")


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

    session_key = f"folder_auth_{token}"
    if folder.share_password_hash and not session.get(session_key):
        abort(403)

    selected_ids = request.form.getlist("file_ids")
    all_files = FileRecord.query.filter_by(folder_id=folder.id).all()
    files_to_pack = (
        [f for f in all_files if f.id in {int(i) for i in selected_ids if i.isdigit()}]
        if selected_ids else all_files
    )
    return _zip_files(files_to_pack, folder.name, "shared_folder_download", folder.name, folder.user_id)


@share_bp.route("/sf/<token>/file/<int:file_id>")
def shared_folder_file(token, file_id):
    """Pobranie pojedynczego pliku z udostępnionego folderu (prywatnego),
    bez konieczności zaznaczania go i pobierania całego ZIP-a."""
    folder = Folder.query.filter_by(share_token=token).first_or_404()
    if not folder.is_share_active:
        abort(410)
    session_key = f"folder_auth_{token}"
    if folder.share_password_hash and not session.get(session_key):
        abort(403)
    record = FileRecord.query.filter_by(id=file_id, folder_id=folder.id).first_or_404()
    return _send_shared_file(record, f"{folder.name} / {record.original_name}")


@share_bp.route("/sf/<token>/file/<int:file_id>/preview")
def shared_folder_file_preview(token, file_id):
    folder = Folder.query.filter_by(share_token=token).first_or_404()
    if not folder.is_share_active:
        abort(410)
    session_key = f"folder_auth_{token}"
    if folder.share_password_hash and not session.get(session_key):
        abort(403)
    record = FileRecord.query.filter_by(id=file_id, folder_id=folder.id).first_or_404()
    return _preview_shared_file(record)


# ── Widok publiczny GŁÓWNEGO FOLDERU POKOJU (root pokoju) ──────────────────────

@share_bp.route("/sr/<token>", methods=["GET", "POST"])
def shared_room(token):
    room = Room.query.filter_by(share_token=token).first_or_404()
    if not room.is_share_active:
        abort(410)

    session_key = f"room_auth_{token}"
    if room.share_password_hash:
        if not session.get(session_key):
            if request.method == "POST":
                pwd = request.form.get("password", "")
                if not check_password_hash(room.share_password_hash, pwd):
                    flash("Błędne hasło.", "danger")
                    return render_template("shared_folder_password.html", token=token, folder=room)
                session[session_key] = True
            else:
                return render_template("shared_folder_password.html", token=token, folder=room)

    room_files = (
        RoomFile.query.filter_by(room_id=room.id, folder_id=None)
        .order_by(RoomFile.uploaded_at.desc())
        .all()
    )
    files = [rf.file_record for rf in room_files if rf.file_record]
    return render_template(
        "shared_folder.html", folder=room, files=files, token=token,
        download_endpoint="share.shared_room_download",
        file_download_endpoint="share.shared_room_file",
    )


@share_bp.route("/sr/<token>/download", methods=["POST"])
def shared_room_download(token):
    room = Room.query.filter_by(share_token=token).first_or_404()
    if not room.is_share_active:
        abort(410)
    session_key = f"room_auth_{token}"
    if room.share_password_hash and not session.get(session_key):
        abort(403)

    selected_ids = request.form.getlist("file_ids")
    room_files = RoomFile.query.filter_by(room_id=room.id, folder_id=None).all()
    all_files = [rf.file_record for rf in room_files if rf.file_record]
    files_to_pack = (
        [f for f in all_files if f.id in {int(i) for i in selected_ids if i.isdigit()}]
        if selected_ids else all_files
    )
    return _zip_files(files_to_pack, room.name, "shared_room_download", room.name, room.owner_id)


@share_bp.route("/sr/<token>/file/<int:file_id>")
def shared_room_file(token, file_id):
    room = Room.query.filter_by(share_token=token).first_or_404()
    if not room.is_share_active:
        abort(410)
    session_key = f"room_auth_{token}"
    if room.share_password_hash and not session.get(session_key):
        abort(403)
    room_file = RoomFile.query.filter_by(room_id=room.id, folder_id=None, file_record_id=file_id).first_or_404()
    record = room_file.file_record
    if not record:
        abort(404)
    return _send_shared_file(record, f"{room.name} / {record.original_name}")


@share_bp.route("/sr/<token>/file/<int:file_id>/preview")
def shared_room_file_preview(token, file_id):
    room = Room.query.filter_by(share_token=token).first_or_404()
    if not room.is_share_active:
        abort(410)
    session_key = f"room_auth_{token}"
    if room.share_password_hash and not session.get(session_key):
        abort(403)
    room_file = RoomFile.query.filter_by(room_id=room.id, folder_id=None, file_record_id=file_id).first_or_404()
    record = room_file.file_record
    if not record:
        abort(404)
    return _preview_shared_file(record)


# ── Widok publiczny PODFOLDERU POKOJU ───────────────────────────────────────────

@share_bp.route("/srf/<token>", methods=["GET", "POST"])
def shared_room_folder(token):
    folder = RoomFolder.query.filter_by(share_token=token).first_or_404()
    if not folder.is_share_active:
        abort(410)

    session_key = f"room_folder_auth_{token}"
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

    room_files = (
        RoomFile.query.filter_by(room_id=folder.room_id, folder_id=folder.id)
        .order_by(RoomFile.uploaded_at.desc())
        .all()
    )
    files = [rf.file_record for rf in room_files if rf.file_record]
    return render_template(
        "shared_folder.html", folder=folder, files=files, token=token,
        download_endpoint="share.shared_room_folder_download",
        file_download_endpoint="share.shared_room_folder_file",
    )


@share_bp.route("/srf/<token>/download", methods=["POST"])
def shared_room_folder_download(token):
    folder = RoomFolder.query.filter_by(share_token=token).first_or_404()
    if not folder.is_share_active:
        abort(410)
    session_key = f"room_folder_auth_{token}"
    if folder.share_password_hash and not session.get(session_key):
        abort(403)

    selected_ids = request.form.getlist("file_ids")
    room_files = RoomFile.query.filter_by(room_id=folder.room_id, folder_id=folder.id).all()
    all_files = [rf.file_record for rf in room_files if rf.file_record]
    files_to_pack = (
        [f for f in all_files if f.id in {int(i) for i in selected_ids if i.isdigit()}]
        if selected_ids else all_files
    )
    return _zip_files(files_to_pack, folder.name, "shared_room_folder_download", f"{folder.room.name} / {folder.name}", folder.created_by_id)


@share_bp.route("/srf/<token>/file/<int:file_id>")
def shared_room_folder_file(token, file_id):
    folder = RoomFolder.query.filter_by(share_token=token).first_or_404()
    if not folder.is_share_active:
        abort(410)
    session_key = f"room_folder_auth_{token}"
    if folder.share_password_hash and not session.get(session_key):
        abort(403)
    room_file = RoomFile.query.filter_by(room_id=folder.room_id, folder_id=folder.id, file_record_id=file_id).first_or_404()
    record = room_file.file_record
    if not record:
        abort(404)
    return _send_shared_file(record, f"{folder.room.name} / {folder.name} / {record.original_name}")


@share_bp.route("/srf/<token>/file/<int:file_id>/preview")
def shared_room_folder_file_preview(token, file_id):
    folder = RoomFolder.query.filter_by(share_token=token).first_or_404()
    if not folder.is_share_active:
        abort(410)
    session_key = f"room_folder_auth_{token}"
    if folder.share_password_hash and not session.get(session_key):
        abort(403)
    room_file = RoomFile.query.filter_by(room_id=folder.room_id, folder_id=folder.id, file_record_id=file_id).first_or_404()
    record = room_file.file_record
    if not record:
        abort(404)
    return _preview_shared_file(record)