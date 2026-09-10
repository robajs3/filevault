from flask import Blueprint, render_template, request, redirect, url_for, flash, session, make_response
from services import AuthService
import sso_client
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
    response = make_response(redirect(sso_client.login_url("/filevault/")))
    response.delete_cookie(REMEMBER_COOKIE_NAME)
    sso_client.clear_sso_cookie(response)
    AuthService.logout()
    return response

@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    # Konta zakłada teraz LoginHub (jedno konto do wszystkich appek) — appka
    # przekierowuje na jego rejestrację zamiast pokazywać własny, osobny
    # formularz, żeby nie powstawały konta "tylko lokalne" bez SSO.
    from urllib.parse import quote
    next_url = request.args.get("next") or url_for("files.dashboard")
    return redirect(f"/auth/register?next={quote(next_url)}")
