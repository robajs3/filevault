from datetime import datetime
from .db import db


class AppLink(db.Model):
    """Pozycja w panelu nawigacyjnym (launcherze) — aplikacja/link, którą
    admin może włączyć/wyłączyć, oznaczyć jako 'w konserwacji', edytować
    lub usunąć z poziomu panelu admina."""

    __tablename__ = "app_links"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.String(255))
    url = db.Column(db.String(255), nullable=False)
    icon = db.Column(db.String(30), default="app", nullable=False)
    color = db.Column(db.String(20), default="blue", nullable=False)
    is_enabled = db.Column(db.Boolean, default=True, nullable=False)
    is_maintenance = db.Column(db.Boolean, default=False, nullable=False)
    sort_order = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    ICONS = ["app", "vault", "calendar", "gameplan", "book", "server", "film", "planner"]
    COLORS = ["blue", "coral", "green", "purple", "pink", "teal", "indigo", "gray"]
