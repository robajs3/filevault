import os
import secrets
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", secrets.token_hex(32))
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://filetransfer:filetransfer@192.168.1.150:5432/filetransfer"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads")
    )
    THUMBNAIL_FOLDER = os.environ.get(
        "THUMBNAIL_FOLDER",
        os.path.join(
            os.environ.get("UPLOAD_FOLDER", os.path.join(BASE_DIR, "uploads")),
            "_thumbs"
        ),
    )

    MAX_CONTENT_LENGTH = int(os.environ.get("MAX_UPLOAD_MB", "500")) * 1024 * 1024
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    ALLOWED_EXTENSIONS = (
        set(os.environ.get("ALLOWED_EXTENSIONS", "").split(","))
        if os.environ.get("ALLOWED_EXTENSIONS")
        else None
    )
    ALLOW_REGISTRATION = os.environ.get("ALLOW_REGISTRATION", "true").lower() == "true"
    REDIS_URL = os.environ.get("REDIS_URL", "memory://")

    # Publiczny adres (schemat+host[:port]), pod którym FileVault jest widoczny
    # z zewnątrz. UŻYWANY DO BUDOWANIA share_url dla plików/folderów/pokoi.
    #
    # Bez tego, share_url jest budowany przez Flaskowe url_for(_external=True),
    # które bierze host z NAGŁÓWKA HOST BIEŻĄCEGO ŻĄDANIA. To działa poprawnie,
    # gdy request przychodzi wprost z przeglądarki (poprawny publiczny host) —
    # ale gdy Koloseum woła FileVault po wewnętrznej sieci kontenerowej
    # (FILEVAULT_INTERNAL_URL, patrz Koloseum), to żądanie ma Host ustawiony
    # na adres wewnętrzny (np. host.docker.internal:8000), i TEN adres
    # zostaje zaszyty w zwróconym share_url — link kompletnie bezużyteczny
    # dla studenta poza siecią kontenerów.
    #
    # Ustaw na realny publiczny adres, np.:
    #   PUBLIC_URL=https://robajs-serwer-dell.tail0ffa98.ts.net
    PUBLIC_URL = (os.environ.get("PUBLIC_URL", "").rstrip("/") or None)

    # Originy (schemat+host[:port]), którym wolno osadzać publiczne strony
    # udostępniania (/filevault/sf/<token>, /filevault/s/<token>) we własnej
    # ramce <iframe> — patrz nagłówki w app.py. Domyślnie NIKT nie może
    # osadzać żadnej strony FileVault (ochrona przed clickjackingiem).
    # Żeby Koloseum mogło pokazywać "Podgląd folderu" w iframe, ustaw tu
    # jego publiczny adres, np.:
    #   FRAME_ALLOWED_ORIGINS=https://koloseum.przyklad.pl
    # Można podać kilka adresów oddzielonych przecinkiem (np. dev + prod).
    FRAME_ALLOWED_ORIGINS = [
        o.strip() for o in os.environ.get("FRAME_ALLOWED_ORIGINS", "").split(",") if o.strip()
    ]

    THUMBNAIL_SIZE = (320, 320)
    THUMBNAILABLE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "bmp"}
    PREVIEWABLE_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "svg"}
    PREVIEWABLE_VIDEO_EXTENSIONS = {"mp4", "webm", "ogg", "mov"}
    PREVIEWABLE_PDF_EXTENSIONS = {"pdf"}
    PREVIEW_MIME_MAP = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp",
        "svg": "image/svg+xml", "mp4": "video/mp4", "webm": "video/webm",
        "ogg": "video/ogg", "mov": "video/quicktime", "pdf": "application/pdf",
    }