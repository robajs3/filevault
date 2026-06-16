from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, g
from models import User, FileRecord, AuditLog, db
from .decorators import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/")
@admin_required
def admin_panel():
    users = User.query.order_by(User.created_at.desc()).all()
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    total_files = FileRecord.query.count()
    total_size = db.session.query(db.func.sum(FileRecord.size_bytes)).scalar() or 0
    return render_template("admin.html", users=users, logs=logs,
                           total_files=total_files, total_size=total_size, user=g.user)


@admin_bp.route("/user/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user(user_id):
    u = db.session.get(User, user_id)
    if not u:
        abort(404)
    u.is_active = not u.is_active
    db.session.commit()
    flash(f"Użytkownik {u.username}: {'aktywny' if u.is_active else 'zablokowany'}.", "info")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/user/<int:user_id>/storage", methods=["POST"])
@admin_required
def set_storage(user_id):
    u = db.session.get(User, user_id)
    if not u:
        abort(404)
    limit = request.form.get("limit_mb", "2048")
    u.storage_limit_mb = int(limit)
    db.session.commit()
    flash(f"Limit miejsca dla {u.username} ustawiony na {limit} MB.", "success")
    return redirect(url_for("admin.admin_panel"))