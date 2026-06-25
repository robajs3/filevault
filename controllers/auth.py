from flask import Blueprint, render_template, request, redirect, url_for, flash, session, make_response
from services import AuthService
from services.auth_service import REMEMBER_COOKIE_NAME, REMEMBER_COOKIE_DAYS

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("files.dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"
        user, remember_token = AuthService.login(username, password, remember=remember)
        if user:
            next_url = request.args.get("next") or url_for("files.dashboard")
            response = make_response(redirect(next_url))
            if remember and remember_token:
                response.set_cookie(
                    REMEMBER_COOKIE_NAME,
                    remember_token,
                    max_age=60 * 60 * 24 * REMEMBER_COOKIE_DAYS,
                    httponly=True,
                    samesite="Lax",
                    secure=request.is_secure,
                )
            else:
                response.delete_cookie(REMEMBER_COOKIE_NAME)
            return response
        flash("Błędna nazwa użytkownika lub hasło.", "danger")
    return render_template("login.html", remember_days=REMEMBER_COOKIE_DAYS)


@auth_bp.route("/logout")
def logout():
    response = make_response(redirect(url_for("auth.login")))
    response.delete_cookie(REMEMBER_COOKIE_NAME)
    AuthService.logout()
    return response


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