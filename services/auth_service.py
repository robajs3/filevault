from datetime import timedelta
from flask import session
from models import User, db
from .audit_service import log_action


class AuthService:
    @staticmethod
    def login(username: str, password: str) -> User | None:
        """Verify credentials and populate the session. Returns the user or None."""
        user = User.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(password):
            session.permanent = True
            session.permanent_session_lifetime = timedelta(days=7)  # type: ignore[assignment]
            session["user_id"] = user.id
            log_action("login", user_id=user.id)
            return user
        log_action("login_failed", detail=username)
        return None

    @staticmethod
    def logout() -> None:
        log_action("logout")
        session.clear()

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