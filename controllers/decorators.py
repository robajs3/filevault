from functools import wraps
from flask import session, redirect, url_for, flash, abort, g, request
from models import User
from services.auth_service import AuthService, REMEMBER_COOKIE_NAME


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            # Try auto-login from remember-me cookie
            token = request.cookies.get(REMEMBER_COOKIE_NAME)
            if token:
                user = AuthService.login_from_cookie(token)
                if user:
                    g.user = user
                    return f(*args, **kwargs)
            flash("Zaloguj się, aby kontynuować.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        g.user = User.query.get(session["user_id"])
        if not g.user or not g.user.is_active:
            session.clear()
            flash("Konto nieaktywne.", "danger")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            abort(403)
        g.user = User.query.get(session["user_id"])
        if not g.user or not g.user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated