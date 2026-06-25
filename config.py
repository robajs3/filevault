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