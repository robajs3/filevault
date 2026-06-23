from datetime import datetime, timedelta, timezone
from flask import current_app

from models import db, FileRecord
from models.room import Room, RoomMembership, RoomInviteCode, RoomFolder, RoomFile
from models.room import ROLE_OWNER, ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER, ROLE_RANK
from services.file_service import FileService
from services.audit_service import log_action


VALID_ROLES = (ROLE_ADMIN, ROLE_EDITOR, ROLE_VIEWER)
EXPIRES_OPTIONS = {
    "1":   1,
    "6":   6,
    "24":  24,
    "72":  72,
    "168": 168,
    "0":   None,   # nie wygasa
}


class RoomService:

    # ── Pokoje ────────────────────────────────────────────────────────────

    @staticmethod
    def create(owner, name: str, description: str = "") -> tuple[Room | None, str | None]:
        name = name.strip()
        if not name:
            return None, "Podaj nazwę pokoju."
        if len(name) > 120:
            return None, "Nazwa pokoju jest za długa (max 120 znaków)."

        room = Room(owner_id=owner.id, name=name, description=description.strip())
        db.session.add(room)
        db.session.flush()   # nadaj room.id przed dodaniem membership

        membership = RoomMembership(room_id=room.id, user_id=owner.id, role=ROLE_OWNER)
        db.session.add(membership)
        db.session.commit()
        log_action("room_create", detail=name)
        return room, None

    @staticmethod
    def delete(room: Room, actor) -> tuple[bool, str | None]:
        membership = RoomService.get_membership(room, actor)
        if not membership or membership.role != ROLE_OWNER:
            return False, "Tylko właściciel może usunąć pokój."
        log_action("room_delete", detail=room.name)
        db.session.delete(room)
        db.session.commit()
        return True, None

    @staticmethod
    def rename(room: Room, actor, new_name: str) -> tuple[bool, str | None]:
        membership = RoomService.get_membership(room, actor)
        if not membership or membership.role != ROLE_OWNER:
            return False, "Tylko właściciel może zmienić nazwę pokoju."
        new_name = new_name.strip()
        if not new_name:
            return False, "Podaj nową nazwę."
        room.name = new_name[:120]
        db.session.commit()
        return True, None

    # ── Membership ────────────────────────────────────────────────────────

    @staticmethod
    def get_membership(room: Room, user) -> RoomMembership | None:
        return RoomMembership.query.filter_by(room_id=room.id, user_id=user.id).first()

    @staticmethod
    def set_role(room: Room, actor, target_user_id: int, new_role: str) -> tuple[bool, str | None]:
        if new_role not in VALID_ROLES:
            return False, "Nieprawidłowa rola."

        actor_m = RoomService.get_membership(room, actor)
        if not actor_m or not actor_m.can_manage_roles():
            return False, "Nie masz uprawnień do zarządzania rolami."

        target_m = RoomMembership.query.filter_by(room_id=room.id, user_id=target_user_id).first()
        if not target_m:
            return False, "Użytkownik nie jest członkiem pokoju."
        if target_m.role == ROLE_OWNER:
            return False, "Nie można zmienić roli właściciela."
        if actor_m.role == ROLE_ADMIN and ROLE_RANK[new_role] >= ROLE_RANK[ROLE_ADMIN]:
            return False, "Admin może nadawać tylko rolę Edytora lub Przeglądającego."

        target_m.role = new_role
        db.session.commit()
        return True, None

    @staticmethod
    def kick(room: Room, actor, target_user_id: int) -> tuple[bool, str | None]:
        actor_m = RoomService.get_membership(room, actor)
        if not actor_m:
            return False, "Nie jesteś członkiem pokoju."

        target_m = RoomMembership.query.filter_by(room_id=room.id, user_id=target_user_id).first()
        if not target_m:
            return False, "Użytkownik nie jest członkiem pokoju."
        if not actor_m.can_kick(target_m):
            return False, "Nie masz uprawnień do usunięcia tego użytkownika."

        db.session.delete(target_m)
        db.session.commit()
        return True, None

    @staticmethod
    def leave(room: Room, user) -> tuple[bool, str | None]:
        membership = RoomService.get_membership(room, user)
        if not membership:
            return False, "Nie jesteś członkiem tego pokoju."
        if membership.role == ROLE_OWNER:
            return False, "Właściciel nie może opuścić pokoju. Najpierw usuń pokój lub przekaż własność."
        db.session.delete(membership)
        db.session.commit()
        return True, None

    # ── Kody zaproszenia ──────────────────────────────────────────────────

    @staticmethod
    def create_invite(room: Room, actor, role: str, expires_hours: str) -> tuple[RoomInviteCode | None, str | None]:
        membership = RoomService.get_membership(room, actor)
        if not membership or not membership.can_generate_invite():
            return None, "Nie masz uprawnień do generowania kodów zaproszenia."
        if role not in VALID_ROLES:
            return None, "Nieprawidłowa rola."

        hours = EXPIRES_OPTIONS.get(str(expires_hours))
        expires_at = None
        if hours is not None:
            expires_at = datetime.now(timezone.utc) + timedelta(hours=hours)

        code = RoomInviteCode(
            room_id=room.id,
            created_by_id=actor.id,
            code=RoomInviteCode.generate_code(),
            role=role,
            expires_at=expires_at,
        )
        db.session.add(code)
        db.session.commit()
        return code, None

    @staticmethod
    def revoke_invite(invite: RoomInviteCode, actor) -> tuple[bool, str | None]:
        membership = RoomService.get_membership(invite.room, actor)
        if not membership or not membership.can_generate_invite():
            return False, "Nie masz uprawnień."
        db.session.delete(invite)
        db.session.commit()
        return True, None

    @staticmethod
    def join_by_code(user, code_str: str) -> tuple[Room | None, str | None]:
        code_str = code_str.strip().upper()
        invite = RoomInviteCode.query.filter_by(code=code_str).first()
        if not invite:
            return None, "Kod zaproszenia nie istnieje."
        if not invite.is_valid:
            return None, "Kod zaproszenia wygasł."

        existing = RoomMembership.query.filter_by(room_id=invite.room_id, user_id=user.id).first()
        if existing:
            return invite.room, None   # już jest — po prostu wróć do pokoju

        membership = RoomMembership(room_id=invite.room_id, user_id=user.id, role=invite.role)
        db.session.add(membership)
        db.session.commit()
        log_action("room_join", detail=invite.room.name)
        return invite.room, None

    # ── Pliki w pokoju ────────────────────────────────────────────────────

    @staticmethod
    def add_file(room: Room, file_record: FileRecord, actor) -> tuple[RoomFile | None, str | None]:
        membership = RoomService.get_membership(room, actor)
        if not membership or not membership.can_upload():
            return None, "Nie masz uprawnień do przesyłania plików w tym pokoju."
        if file_record.user_id != actor.id:
            return None, "Możesz udostępniać tylko swoje pliki."

        existing = RoomFile.query.filter_by(room_id=room.id, file_record_id=file_record.id).first()
        if existing:
            return existing, None

        entry = RoomFile(room_id=room.id, file_record_id=file_record.id, uploaded_by_id=actor.id)
        db.session.add(entry)
        db.session.commit()
        return entry, None

    @staticmethod
    def remove_file(room: Room, room_file: RoomFile, actor) -> tuple[bool, str | None]:
        membership = RoomService.get_membership(room, actor)
        if not membership:
            return False, "Nie jesteś członkiem pokoju."
        is_uploader = room_file.uploaded_by_id == actor.id
        if not is_uploader and not membership.can_delete_any():
            return False, "Nie masz uprawnień do usunięcia tego pliku."
        db.session.delete(room_file)
        db.session.commit()
        return True, None

    # ── Podfoldery w pokoju ───────────────────────────────────────────────

    @staticmethod
    def create_folder(room, actor, name: str, parent_id=None):
        membership = RoomService.get_membership(room, actor)
        if not membership or not membership.can_manage_folders():
            return None, "Nie masz uprawnien do tworzenia folderow."
        name = name.strip()
        if not name:
            return None, "Podaj nazwe folderu."
        if len(name) > 255:
            return None, "Nazwa folderu jest za dluga."

        # Waliduj parent
        if parent_id:
            parent = RoomFolder.query.filter_by(id=parent_id, room_id=room.id).first()
            if not parent:
                return None, "Folder nadrzedny nie istnieje."

        exists = RoomFolder.query.filter_by(
            room_id=room.id, parent_id=parent_id, name=name
        ).first()
        if exists:
            return None, f"Folder '{name}' juz istnieje w tym miejscu."

        folder = RoomFolder(
            room_id=room.id,
            parent_id=parent_id,
            created_by_id=actor.id,
            name=name,
        )
        db.session.add(folder)
        db.session.commit()
        return folder, None

    @staticmethod
    def delete_folder(room, actor, folder):
        membership = RoomService.get_membership(room, actor)
        if not membership or not membership.can_delete_any():
            if folder.created_by_id != actor.id:
                return False, "Nie masz uprawnien do usuniecia tego folderu."
        db.session.delete(folder)
        db.session.commit()
        return True, None

    @staticmethod
    def rename_folder(room, actor, folder, new_name: str):
        membership = RoomService.get_membership(room, actor)
        if not membership or not membership.can_manage_folders():
            return False, "Nie masz uprawnien."
        new_name = new_name.strip()
        if not new_name:
            return False, "Podaj nowa nazwe."
        folder.name = new_name[:255]
        db.session.commit()
        return True, None

    @staticmethod
    def add_file(room, file_record, actor, folder_id=None):
        membership = RoomService.get_membership(room, actor)
        if not membership or not membership.can_upload():
            return None, "Nie masz uprawnien do przesylania plikow w tym pokoju."
        if file_record.user_id != actor.id:
            return None, "Mozesz udostepniac tylko swoje pliki."

        # Waliduj folder
        if folder_id:
            rf = RoomFolder.query.filter_by(id=folder_id, room_id=room.id).first()
            if not rf:
                return None, "Folder nie istnieje."

        existing = RoomFile.query.filter_by(
            room_id=room.id, file_record_id=file_record.id, folder_id=folder_id
        ).first()
        if existing:
            return existing, None

        entry = RoomFile(
            room_id=room.id,
            folder_id=folder_id,
            file_record_id=file_record.id,
            uploaded_by_id=actor.id,
        )
        db.session.add(entry)
        db.session.commit()
        return entry, None