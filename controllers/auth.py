from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from services import AuthService

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("files.dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = AuthService.login(username, password)
        if user:
            next_url = request.args.get("next") or url_for("files.dashboard")
            return redirect(next_url)
        flash("Błędna nazwa użytkownika lub hasło.", "danger")
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    AuthService.logout()
    return redirect(url_for("auth.login"))


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    from flask import current_app
    if not current_app.config.get("ALLOW_REGISTRATION", True):
        flash("Rejestracja jest wyłączona. Skontaktuj się z administratorem.", "info")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not username or not email or not password:
            flash("Wypełnij wszystkie pola.", "danger")
        elif password != confirm:
            flash("Hasła nie są identyczne.", "danger")
        else:
            user, error = AuthService.register(username, email, password)
            if error:
                flash(error, "danger")
            else:
                flash("Konto zostało utworzone!", "success")
                return redirect(url_for("files.dashboard"))

    return render_template("register.html")