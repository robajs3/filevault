from datetime import datetime, timezone
from .db import db


class Folder(db.Model):
    __tablename__ = "folders"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("folders.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

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