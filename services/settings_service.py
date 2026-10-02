from flask import current_app

from models import Setting, db

KEY_DEFAULT_MAX_UPLOAD = "default_max_upload_mb"
MIN_UPLOAD_MB = 1
MAX_UPLOAD_MB_CEILING = 102400  # 100 GB — sufit sensownej wartości w formularzu


def get_default_max_upload_mb() -> int:
    """Domyślny limit pliku dla wszystkich (z bazy; fallback: config, czyli 500 MB)."""
    fallback = current_app.config.get("DEFAULT_MAX_UPLOAD_MB", 500)
    row = db.session.get(Setting, KEY_DEFAULT_MAX_UPLOAD)
    if not row:
        return fallback
    try:
        value = int(row.value)
    except (TypeError, ValueError):
        return fallback
    return value if value >= MIN_UPLOAD_MB else fallback


def set_default_max_upload_mb(mb: int) -> None:
    row = db.session.get(Setting, KEY_DEFAULT_MAX_UPLOAD)
    if row:
        row.value = str(mb)
    else:
        db.session.add(Setting(key=KEY_DEFAULT_MAX_UPLOAD, value=str(mb)))
    db.session.commit()


def effective_max_upload_mb(user=None) -> int:
    """Limit dla konkretnego usera: jego override, a jeśli brak — domyślny."""
    override = getattr(user, "max_upload_mb", None) if user is not None else None
    if override and override >= MIN_UPLOAD_MB:
        return override
    return get_default_max_upload_mb()


def effective_max_upload_bytes(user=None) -> int:
    return effective_max_upload_mb(user) * 1024 * 1024
