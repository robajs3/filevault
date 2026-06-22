import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, abort
from werkzeug.security import check_password_hash
from models import FileRecord, db
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