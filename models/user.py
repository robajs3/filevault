from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from .db import db
import secrets


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.utcnow())
    storage_limit_mb = db.Column(db.Integer, default=2048)

    files = db.relationship(
        "FileRecord",
        backref="owner",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    folders = db.relationship(
        "Folder",
        backref="owner",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    api_token = db.Column(db.String(64), unique=True, nullable=True, index=True)
    remember_token = db.Column(db.String(64), unique=True, nullable=True, index=True)

    def generate_remember_token(self) -> str:
        self.remember_token = secrets.token_hex(32)
        return self.remember_token

    def revoke_remember_token(self) -> None:
        self.remember_token = None

    def generate_api_token(self):
        self.api_token = secrets.token_hex(32)
        return self.api_token

    def revoke_api_token(self):
        self.api_token = None

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def used_storage_mb(self) -> float:
        from .file_record import FileRecord
        total = (
            db.session.query(db.func.sum(FileRecord.size_bytes))
            .filter_by(user_id=self.id)
            .scalar()
            or 0
        )
        return round(float(total) / (1024 * 1024), 2)