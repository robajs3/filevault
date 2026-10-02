from .db import db


class Setting(db.Model):
    """Proste ustawienia globalne (klucz -> wartość), edytowane z panelu admina."""
    __tablename__ = "settings"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(255), nullable=False)
