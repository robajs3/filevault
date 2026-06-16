from datetime import datetime, timezone
from flask import url_for
from .db import db

PREVIEWABLE_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"}
PREVIEWABLE_VIDEO_EXTENSIONS = {"mp4", "webm", "ogg", "mov"}
PREVIEWABLE_AUDIO_EXTENSIONS = {"mp3", "wav"}
PREVIEWABLE_PDF_EXTENSIONS = {"pdf"}
PREVIEW_MIME_MAP = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
    "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp",
    "svg": "image/svg+xml", "mp4": "video/mp4", "webm": "video/webm",
    "ogg": "video/ogg", "mov": "video/quicktime", "pdf": "application/pdf",
    "mp3": "audio/mpeg", "wav": "audio/wav",
}

class FileRecord(db.Model):
    __tablename__ = "files"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey("folders.id"), nullable=True)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), unique=True, nullable=False)
    size_bytes = db.Column(db.BigInteger, nullable=False)
    mime_type = db.Column(db.String(120))
    share_token = db.Column(db.String(64), unique=True, nullable=True)
    share_expires_at = db.Column(db.DateTime, nullable=True)
    share_password_hash = db.Column(db.String(255), nullable=True)
    download_count = db.Column(db.Integer, default=0)
    download_limit = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_private = db.Column(db.Boolean, default=True)
    has_thumbnail = db.Column(db.Boolean, default=False)

    @property
    def share_url(self) -> str | None:
        if self.share_token:
            return url_for("share.download_shared", token=self.share_token, _external=True)
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
        if self.download_limit and self.download_count >= self.download_limit:
            return False
        return True

    @property
    def size_human(self) -> str:
        b = self.size_bytes
        for unit in ("B", "KB", "MB", "GB"):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"

    @property
    def extension(self) -> str:
        return self.original_name.rsplit(".", 1)[-1].lower() if "." in self.original_name else ""

    @property
    def preview_type(self) -> str | None:
        ext = self.extension
        if ext in PREVIEWABLE_IMAGE_EXTENSIONS:
            return "image"
        if ext in PREVIEWABLE_VIDEO_EXTENSIONS:
            return "video"
        if ext in PREVIEWABLE_AUDIO_EXTENSIONS:
            return "audio"
        if ext in PREVIEWABLE_PDF_EXTENSIONS:
            return "pdf"
        return None

    @property
    def is_previewable(self) -> bool:
        return self.preview_type is not None