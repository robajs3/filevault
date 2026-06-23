from flask import Blueprint, render_template, redirect, url_for, flash, request, g
from controllers.decorators import login_required
from models import db
from models.user import User

profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/profile")
@login_required
def profile_view():
    from models.file_record import FileRecord
    from models.room import RoomMembership

    file_count = FileRecord.query.filter_by(user_id=g.user.id).count()
    room_count = RoomMembership.query.filter_by(user_id=g.user.id).count()

    used_mb = g.user.used_storage_mb
    limit_mb = g.user.storage_limit_mb
    used_pct = min(round(used_mb / limit_mb * 100, 1), 100) if limit_mb else 0

    return render_template(
        "profile.html",
        user=g.user,
        file_count=file_count,
        room_count=room_count,
        used_mb=used_mb,
        limit_mb=limit_mb,
        used_pct=used_pct,
    )


@profile_bp.route("/profile/change-password", methods=["POST"])
@login_required
def change_password():
    current = request.form.get("current_password", "")
    new_pw  = request.form.get("new_password", "")
    confirm = request.form.get("confirm_password", "")

    if not g.user.check_password(current):
        flash("Aktualne haslo jest nieprawidlowe.", "danger")
        return redirect(url_for("profile.profile_view"))

    if len(new_pw) < 8:
        flash("Nowe haslo musi miec co najmniej 8 znakow.", "danger")
        return redirect(url_for("profile.profile_view"))

    if new_pw != confirm:
        flash("Hasla sie nie zgadzaja.", "danger")
        return redirect(url_for("profile.profile_view"))

    g.user.set_password(new_pw)
    db.session.commit()
    flash("Haslo zostalo zmienione.", "success")
    return redirect(url_for("profile.profile_view"))


@profile_bp.route("/profile/change-email", methods=["POST"])
@login_required
def change_email():
    new_email = request.form.get("email", "").strip().lower()
    current_pw = request.form.get("password", "")

    if not g.user.check_password(current_pw):
        flash("Nieprawidlowe haslo.", "danger")
        return redirect(url_for("profile.profile_view"))

    if not new_email or "@" not in new_email:
        flash("Podaj prawidlowy adres e-mail.", "danger")
        return redirect(url_for("profile.profile_view"))

    exists = User.query.filter(User.email == new_email, User.id != g.user.id).first()
    if exists:
        flash("Ten adres e-mail jest juz zajety.", "danger")
        return redirect(url_for("profile.profile_view"))

    g.user.email = new_email
    db.session.commit()
    flash("Adres e-mail zostal zmieniony.", "success")
    return redirect(url_for("profile.profile_view"))