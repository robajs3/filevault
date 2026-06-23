import os
import uuid
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from PIL import Image, UnidentifiedImageError

from models import FileRecord, db
from .audit_service import log_action


def _allowed_file(filename: str) -> bool:
    allowed = current_app.config.get("ALLOWED_EXTENSIONS")
    if allowed is None:
        return True
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in allowed


def _generate_thumbnail(source_path: str, stored_name: str) -> bool:
    thumbnailable = current_app.config["THUMBNAILABLE_EXTENSIONS"]
    ext = stored_name.rsplit(".", 1)[-1].lower() if "." in stored_name else ""
    if ext not in thumbnailable:
        return False
    try:
        thumb_folder = current_app.config["THUMBNAIL_FOLDER"]
        os.makedirs(thumb_folder, exist_ok=True)
        size = current_app.config["THUMBNAIL_SIZE"]
        with Image.open(source_path) as img:
            img = img.convert("RGB") if img.mode in ("P", "RGBA", "CMYK") else img
            img.thumbnail(size)
            thumb_path = os.path.join(thumb_folder, stored_name + ".webp")
            img.save(thumb_path, "WEBP", quality=80)
        return True
    except (UnidentifiedImageError, OSError, ValueError):
        return False


class FileService:
    @staticmethod
    def save_upload(file: FileStorage, user, folder_id: int | None = None) -> tuple[FileRecord | None, str | None]:
        """Persist an uploaded file. Returns (record, error_message)."""
        if not file.filename:
            return None, "Brak nazwy pliku."
        if not _allowed_file(file.filename):
            return None, f"Niedozwolony typ pliku: {file.filename}"

        original_name = secure_filename(file.filename)
        ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
        stored_name = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
        upload_folder = current_app.config["UPLOAD_FOLDER"]
        path = os.path.join(upload_folder, stored_name)
        file.save(path)
        size = os.path.getsize(path)

        if user.used_storage_mb + size / (1024 * 1024) > user.storage_limit_mb:
            os.remove(path)
            return None, "Przekroczono limit miejsca na dysku."

        thumb_ok = _generate_thumbnail(path, stored_name)
        record = FileRecord(
            user_id=user.id,
            folder_id=folder_id,
            original_name=original_name,
            stored_name=stored_name,
            size_bytes=size,
            mime_type=file.content_type,
            has_thumbnail=thumb_ok,
        )
        db.session.add(record)
        db.session.commit()
        log_action("upload", detail=original_name)
        return record, None

    @staticmethod
    def delete(record: FileRecord) -> None:
        upload_folder = current_app.config["UPLOAD_FOLDER"]
        thumb_folder = current_app.config["THUMBNAIL_FOLDER"]
        path = os.path.join(upload_folder, record.stored_name)
        if os.path.exists(path):
            os.remove(path)
        if record.has_thumbnail:
            thumb_path = os.path.join(thumb_folder, record.stored_name + ".webp")
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
        log_action("delete", detail=record.original_name)
        db.session.delete(record)
        db.session.commit()

    @staticmethod
    def rename(record: FileRecord, new_name: str) -> tuple[bool, str | None]:
        if not new_name:
            return False, "Podaj nową nazwę pliku."
        if len(new_name) > 255:
            return False, "Nazwa pliku jest za długa."
        new_name = secure_filename(new_name)
        old_ext = record.original_name.rsplit(".", 1)[-1].lower() if "." in record.original_name else ""
        new_ext = new_name.rsplit(".", 1)[-1].lower() if "." in new_name else ""
        if old_ext and new_ext != old_ext:
            new_name = f"{new_name}.{old_ext}"
        log_action("rename_file", detail=f"{record.original_name} -> {new_name}")
        record.original_name = new_name
        db.session.commit()
        return True, None

    @staticmethod
    def move(record: FileRecord, target_folder) -> None:
        record.folder_id = target_folder.id if target_folder else None
        db.session.commit()
        dest = target_folder.name if target_folder else "root"
        log_action("move_file", detail=f"{record.original_name} -> {dest}")

    @staticmethod
    def create_share(record: FileRecord, expires_hours: int, password: str = "", download_limit: str = "") -> None:
        record.share_token = secrets.token_urlsafe(32)
        record.share_expires_at = None if expires_hours == 0 else datetime.now(timezone.utc) + timedelta(hours=expires_hours)
        record.share_password_hash = generate_password_hash(password) if password else None
        record.download_limit = int(download_limit) if download_limit.isdigit() else None
        record.download_count = 0
        db.session.commit()
        log_action("share_created", detail=record.original_name)

    @staticmethod
    def revoke_share(record: FileRecord) -> None:
        record.share_token = None
        record.share_expires_at = None
        record.share_password_hash = None
        record.download_limit = None
        db.session.commit()

    @staticmethod
    def physical_path(record: FileRecord) -> str:
        return os.path.join(current_app.config["UPLOAD_FOLDER"], record.stored_name)

    @staticmethod
    def thumbnail_path(record: FileRecord) -> str:
        return os.path.join(current_app.config["THUMBNAIL_FOLDER"], record.stored_name + ".webp")