import os
import secrets
from datetime import datetime, timezone, timedelta
from flask import current_app
from werkzeug.security import generate_password_hash
from models import Folder, FileRecord, db
from .audit_service import log_action


def collect_descendant_ids(folder_id: int) -> list[int]:
    """Recursively collect all descendant folder IDs."""
    ids: list[int] = []
    children = Folder.query.filter_by(parent_id=folder_id).all()
    for child in children:
        ids.append(child.id)
        ids.extend(collect_descendant_ids(child.id))
    return ids


class FolderService:
    @staticmethod
    def create(user_id: int, name: str, parent_id: int | None = None) -> tuple[Folder | None, str | None]:
        if not name:
            return None, "Podaj nazwę folderu."
        if len(name) > 255:
            return None, "Nazwa folderu jest za długa."
        existing = Folder.query.filter_by(user_id=user_id, name=name, parent_id=parent_id).first()
        if existing:
            return None, "Folder o tej nazwie już istnieje w tym miejscu."
        folder = Folder(user_id=user_id, name=name, parent_id=parent_id)
        db.session.add(folder)
        db.session.commit()
        log_action("folder_created", detail=name)
        return folder, None

    @staticmethod
    def rename(folder: Folder, new_name: str) -> tuple[bool, str | None]:
        if not new_name:
            return False, "Podaj nową nazwę folderu."
        existing = Folder.query.filter(
            Folder.user_id == folder.user_id,
            Folder.name == new_name,
            Folder.parent_id == folder.parent_id,
            Folder.id != folder.id,
        ).first()
        if existing:
            return False, "Folder o tej nazwie już istnieje w tym miejscu."
        log_action("folder_renamed", detail=f"{folder.name} -> {new_name}")
        folder.name = new_name
        db.session.commit()
        return True, None

    @staticmethod
    def delete(folder: Folder) -> None:
        upload_folder = current_app.config["UPLOAD_FOLDER"]
        thumb_folder = current_app.config["THUMBNAIL_FOLDER"]
        all_ids = [folder.id] + collect_descendant_ids(folder.id)
        for fid in all_ids:
            for record in FileRecord.query.filter_by(folder_id=fid).all():
                path = os.path.join(upload_folder, record.stored_name)
                if os.path.exists(path):
                    os.remove(path)
                if record.has_thumbnail:
                    thumb_path = os.path.join(thumb_folder, record.stored_name + ".webp")
                    if os.path.exists(thumb_path):
                        os.remove(thumb_path)
        log_action("folder_deleted", detail=folder.name)
        db.session.delete(folder)
        db.session.commit()

    @staticmethod
    def create_share(folder: Folder, expires_hours: int, password: str = "") -> None:
        folder.share_token = secrets.token_urlsafe(32)
        folder.share_expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
        folder.share_password_hash = generate_password_hash(password) if password else None
        db.session.commit()
        log_action("folder_share_created", detail=folder.name)

    @staticmethod
    def revoke_share(folder: Folder) -> None:
        folder.share_token = None
        folder.share_expires_at = None
        folder.share_password_hash = None
        db.session.commit()
        log_action("folder_share_revoked", detail=folder.name)

    @staticmethod
    def move(folder: Folder, new_parent_id: int | None) -> tuple[bool, str | None]:
        if new_parent_id is not None:
            if new_parent_id == folder.id or new_parent_id in collect_descendant_ids(folder.id):
                return False, "Nie można przenieść folderu do samego siebie ani jego podfolderów."
            new_parent = Folder.query.filter_by(id=new_parent_id, user_id=folder.user_id).first()
            if not new_parent:
                return False, "Folder docelowy nie istnieje."
            dest_name = new_parent.name
        else:
            dest_name = "root"
        folder.parent_id = new_parent_id
        db.session.commit()
        log_action("folder_moved", detail=f"{folder.name} -> {dest_name}")
        return True, None