import secrets
from datetime import datetime, timedelta, timezone
from .db import db


# Role w pokoju
ROLE_OWNER  = "owner"
ROLE_ADMIN  = "admin"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"

ROLE_RANK = {ROLE_OWNER: 3, ROLE_ADMIN: 2, ROLE_EDITOR: 1, ROLE_VIEWER: 0}


class Room(db.Model):
    __tablename__ = "rooms"

    id          = db.Column(db.Integer, primary_key=True)
    owner_id    = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name        = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(500), nullable=True)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    memberships  = db.relationship("RoomMembership", backref="room",
                                   cascade="all, delete-orphan", lazy="dynamic")
    invite_codes = db.relationship("RoomInviteCode", backref="room",
                                   cascade="all, delete-orphan", lazy="dynamic")
    files        = db.relationship("RoomFile", backref="room",
                                   cascade="all, delete-orphan", lazy="dynamic")
    folders      = db.relationship("RoomFolder", backref="room",
                                   cascade="all, delete-orphan", lazy="dynamic")

    @property
    def member_count(self) -> int:
        return self.memberships.count()

    @property
    def file_count(self) -> int:
        return self.files.count()


class RoomMembership(db.Model):
    __tablename__ = "room_memberships"

    id        = db.Column(db.Integer, primary_key=True)
    room_id   = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False)
    user_id   = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    role      = db.Column(db.String(20), nullable=False, default=ROLE_VIEWER)
    joined_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint("room_id", "user_id"),)

    user = db.relationship("User", backref="room_memberships")

    @property
    def role_rank(self) -> int:
        return ROLE_RANK.get(self.role, 0)

    def can_upload(self) -> bool:
        return self.role in (ROLE_OWNER, ROLE_ADMIN, ROLE_EDITOR)

    def can_delete_any(self) -> bool:
        return self.role in (ROLE_OWNER, ROLE_ADMIN)

    def can_manage_roles(self) -> bool:
        return self.role in (ROLE_OWNER, ROLE_ADMIN)

    def can_generate_invite(self) -> bool:
        return self.role in (ROLE_OWNER, ROLE_ADMIN)

    def can_manage_folders(self) -> bool:
        return self.role in (ROLE_OWNER, ROLE_ADMIN, ROLE_EDITOR)

    def can_kick(self, target: "RoomMembership") -> bool:
        if self.role == ROLE_OWNER:
            return target.role != ROLE_OWNER
        if self.role == ROLE_ADMIN:
            return target.role in (ROLE_EDITOR, ROLE_VIEWER)
        return False


class RoomInviteCode(db.Model):
    __tablename__ = "room_invite_codes"

    id            = db.Column(db.Integer, primary_key=True)
    room_id       = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    code          = db.Column(db.String(12), unique=True, nullable=False)
    role          = db.Column(db.String(20), nullable=False, default=ROLE_VIEWER)
    expires_at    = db.Column(db.DateTime, nullable=True)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    created_by = db.relationship("User", backref="created_invite_codes")

    @staticmethod
    def generate_code() -> str:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        return "".join(secrets.choice(alphabet) for _ in range(8))

    @property
    def is_valid(self) -> bool:
        if self.expires_at is None:
            return True
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp > datetime.now(timezone.utc)

    @property
    def expires_label(self) -> str:
        if self.expires_at is None:
            return "Nie wygasa"
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        delta = exp - datetime.now(timezone.utc)
        if delta.total_seconds() < 0:
            return "Wygasl"
        hours = int(delta.total_seconds() // 3600)
        if hours < 1:
            return "< 1 godz."
        if hours < 48:
            return f"{hours} godz."
        return f"{hours // 24} dni"


class RoomFolder(db.Model):
    """Podfolder wewnatrz pokoju - drzewo niezalezne od prywatnych folderow uzytkownika."""
    __tablename__ = "room_folders"

    id            = db.Column(db.Integer, primary_key=True)
    room_id       = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False)
    parent_id     = db.Column(db.Integer, db.ForeignKey("room_folders.id"), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name          = db.Column(db.String(255), nullable=False)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    children = db.relationship(
        "RoomFolder",
        backref=db.backref("parent", remote_side=[id]),
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    files      = db.relationship("RoomFile", backref="room_folder", lazy="dynamic")
    created_by = db.relationship("User", backref="created_room_folders")

    @property
    def full_path(self) -> str:
        parts = [self.name]
        node = self
        while node.parent_id:
            node = db.session.get(RoomFolder, node.parent_id)
            parts.insert(0, node.name)
        return " / ".join(parts)

    @property
    def file_count(self) -> int:
        return self.files.count()


class RoomFile(db.Model):
    """Plik przeslany do pokoju - wskazuje na istniejacy FileRecord wlasciciela."""
    __tablename__ = "room_files"

    id             = db.Column(db.Integer, primary_key=True)
    room_id        = db.Column(db.Integer, db.ForeignKey("rooms.id"), nullable=False)
    folder_id      = db.Column(db.Integer, db.ForeignKey("room_folders.id"), nullable=True)
    file_record_id = db.Column(db.Integer, db.ForeignKey("files.id"), nullable=False)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    uploaded_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    file_record = db.relationship("FileRecord", backref="room_entries")
    uploaded_by = db.relationship("User", backref="room_uploads")