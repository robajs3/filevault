from datetime import timedelta
from flask import session, make_response
from models import User, db
from .audit_service import log_action

REMEMBER_COOKIE_NAME = "filevault_remember"
REMEMBER_COOKIE_DAYS = 9999


class AuthService:
    @staticmethod
    def login(username: str, password: str, remember: bool = False):
        """Verify credentials and populate the session. Returns (user, response) or (None, None)."""
        user = User.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(password):
            session.permanent = True
            session.permanent_session_lifetime = timedelta(days=7)  # type: ignore[assignment]
            session["user_id"] = user.id
            log_action("login", user_id=user.id)

            if remember:
                token = user.generate_remember_token()
                db.session.commit()
                return user, token
            return user, None
        log_action("login_failed", detail=username)
        return None, None

    @staticmethod
    def logout() -> None:
        user_id = session.get("user_id")
        if user_id:
            user = User.query.get(user_id)
            if user:
                user.revoke_remember_token()
                db.session.commit()
        log_action("logout")
        session.clear()

    @staticmethod
    def login_from_cookie(token: str):
        """Auto-login user from remember-me cookie. Returns user or None."""
        if not token:
            return None
        user = User.query.filter_by(remember_token=token).first()
        if user and user.is_active:
            session.permanent = True
            session.permanent_session_lifetime = timedelta(days=7)  # type: ignore[assignment]
            session["user_id"] = user.id
            return user
        return None

    @staticmethod
    def register(username: str, email: str, password: str) -> tuple[User | None, str | None]:
        """Create a new user. Returns (user, error_message)."""
        if len(password) < 8:
            return None, "Hasło musi mieć co najmniej 8 znaków."
        if User.query.filter_by(username=username).first():
            return None, "Nazwa użytkownika jest zajęta."
        if User.query.filter_by(email=email).first():
            return None, "Email jest już zarejestrowany."

        user = User(username=username, email=email)
        user.set_password(password)
        if not User.query.first():
            user.is_admin = True  # first user becomes admin
        db.session.add(user)
        db.session.commit()
        session["user_id"] = user.id
        log_action("register", user_id=user.id)
        return user, None