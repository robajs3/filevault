from datetime import datetime, timezone
from flask import url_for
from .db import db


class Folder(db.Model):
    __tablename__ = "folders"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("folders.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Udostępnianie folderu
    share_token = db.Column(db.String(64), unique=True, nullable=True)
    share_expires_at = db.Column(db.DateTime, nullable=True)
    share_password_hash = db.Column(db.String(255), nullable=True)

    children = db.relationship(
        "Folder",
        backref=db.backref("parent", remote_side=[id]),
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    files = db.relationship("FileRecord", backref="folder", lazy="dynamic")

    @property
    def full_path(self) -> str:
        parts = [self.name]
        node = self
        while node.parent_id:
            node = db.session.get(Folder, node.parent_id)
            parts.insert(0, node.name)
        return " / ".join(parts)

    @property
    def file_count(self) -> int:
        return self.files.count()

    @property
    def total_size_bytes(self) -> int:
        from .file_record import FileRecord
        return (
            db.session.query(db.func.sum(FileRecord.size_bytes))
            .filter_by(folder_id=self.id)
            .scalar()
            or 0
        )

    @property
    def share_url(self) -> str | None:
        if self.share_token:
            return url_for("share.shared_folder", token=self.share_token, _external=True)
        return None

    @property
    def is_share_active(self) -> bool:
        if not self.share_token:
            return False
        if self.share_expires_at:
            expires = self.share_expires_at
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if expires < datetime.now(timezone.utc):
                return False
        return True