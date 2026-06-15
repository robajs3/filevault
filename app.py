import os
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from dotenv import load_dotenv
load_dotenv()

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, send_file, abort, jsonify, g
)
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "postgresql://filetransfer:filetransfer@localhost/filetransfer"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = os.environ.get("UPLOAD_FOLDER", "uploads")
app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_MB", "500")) * 1024 * 1024
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

ALLOWED_EXTENSIONS = set(os.environ.get("ALLOWED_EXTENSIONS", "").split(",")) if os.environ.get("ALLOWED_EXTENSIONS") else None

db = SQLAlchemy(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per hour", "50 per minute"],
    storage_uri=os.environ.get("REDIS_URL", "memory://"),
)

# ─── Models ───────────────────────────────────────────────────────────────────

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.utcnow())
    storage_limit_mb = db.Column(db.Integer, default=2048)
    files = db.relationship("FileRecord", backref="owner", lazy="dynamic", cascade="all, delete-orphan")
    folders = db.relationship("Folder", backref="owner", lazy="dynamic", cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def used_storage_mb(self):
        total = db.session.query(db.func.sum(FileRecord.size_bytes)).filter_by(user_id=self.id).scalar() or 0
        return round(total / (1024 * 1024), 2)


class Folder(db.Model):
    __tablename__ = "folders"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("folders.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Self-referential relationship for nested folders
    children = db.relationship("Folder", backref=db.backref("parent", remote_side=[id]),
                               lazy="dynamic", cascade="all, delete-orphan")
    files = db.relationship("FileRecord", backref="folder", lazy="dynamic")

    @property
    def full_path(self):
        """Returns the full path string like 'root/sub/subsub'."""
        parts = [self.name]
        node = self
        while node.parent_id:
            node = db.session.get(Folder, node.parent_id)
            parts.insert(0, node.name)
        return " / ".join(parts)

    @property
    def file_count(self):
        return self.files.count()

    @property
    def total_size_bytes(self):
        return db.session.query(db.func.sum(FileRecord.size_bytes)).filter_by(folder_id=self.id).scalar() or 0


class FileRecord(db.Model):
    __tablename__ = "files"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    folder_id = db.Column(db.Integer, db.ForeignKey("folders.id"), nullable=True)  # NEW
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

    @property
    def share_url(self):
        if self.share_token:
            return url_for("download_shared", token=self.share_token, _external=True)
        return None

    @property
    def is_share_active(self):
        if not self.share_token:
            return False
        if self.share_expires_at and self.share_expires_at < datetime.now(timezone.utc):
            return False
        if self.download_limit and self.download_count >= self.download_limit:
            return False
        return True

    @property
    def size_human(self):
        b = self.size_bytes
        for unit in ("B", "KB", "MB", "GB"):
            if b < 1024:
                return f"{b:.1f} {unit}"
            b /= 1024
        return f"{b:.1f} TB"


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(80), nullable=False)
    detail = db.Column(db.Text)
    ip = db.Column(db.String(45))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def log_action(action, detail=None, user_id=None):
    entry = AuditLog(
        user_id=user_id or session.get("user_id"),
        action=action,
        detail=detail,
        ip=request.remote_addr,
    )
    db.session.add(entry)
    db.session.commit()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Zaloguj się, aby kontynuować.", "warning")
            return redirect(url_for("login", next=request.path))
        g.user = db.session.get(User, session["user_id"])
        if not g.user or not g.user.is_active:
            session.clear()
            flash("Konto nieaktywne.", "danger")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            abort(403)
        g.user = db.session.get(User, session["user_id"])
        if not g.user or not g.user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename):
    if ALLOWED_EXTENSIONS is None:
        return True
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in ALLOWED_EXTENSIONS


def get_user_folder(folder_id):
    """Get a folder that belongs to the current user, or 404."""
    folder = db.session.get(Folder, folder_id)
    if not folder or folder.user_id != g.user.id:
        abort(404)
    return folder


def collect_descendant_ids(folder_id):
    """Recursively collect all descendant folder IDs (for delete protection)."""
    ids = []
    children = Folder.query.filter_by(parent_id=folder_id).all()
    for child in children:
        ids.append(child.id)
        ids.extend(collect_descendant_ids(child.id))
    return ids


# ─── Auth routes ──────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("100 per minute")
def login():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and user.is_active and user.check_password(password):
            session.permanent = True
            app.permanent_session_lifetime = timedelta(days=7)
            session["user_id"] = user.id
            log_action("login", user_id=user.id)
            next_url = request.args.get("next") or url_for("dashboard")
            return redirect(next_url)
        flash("Błędna nazwa użytkownika lub hasło.", "danger")
        log_action("login_failed", detail=username)
    return render_template("login.html")


@app.route("/logout")
def logout():
    log_action("logout")
    session.clear()
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("50 per hour")
def register():
    if not os.environ.get("ALLOW_REGISTRATION", "true").lower() == "true":
        flash("Rejestracja jest wyłączona. Skontaktuj się z administratorem.", "info")
        return redirect(url_for("login"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if not username or not email or not password:
            flash("Wypełnij wszystkie pola.", "danger")
        elif len(password) < 8:
            flash("Hasło musi mieć co najmniej 8 znaków.", "danger")
        elif password != confirm:
            flash("Hasła nie są identyczne.", "danger")
        elif User.query.filter_by(username=username).first():
            flash("Nazwa użytkownika jest zajęta.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("Email jest już zarejestrowany.", "danger")
        else:
            user = User(username=username, email=email)
            user.set_password(password)
            if not User.query.first():
                user.is_admin = True
            db.session.add(user)
            db.session.commit()
            session["user_id"] = user.id
            log_action("register", user_id=user.id)
            flash("Konto zostało utworzone!", "success")
            return redirect(url_for("dashboard"))
    return render_template("register.html")


# ─── Dashboard & File management ──────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    # Show root-level folders and files (no folder assigned)
    folders = Folder.query.filter_by(user_id=g.user.id, parent_id=None).order_by(Folder.name).all()
    files = FileRecord.query.filter_by(user_id=g.user.id, folder_id=None).order_by(FileRecord.created_at.desc()).all()
    all_folders = Folder.query.filter_by(user_id=g.user.id).order_by(Folder.name).all()
    return render_template("dashboard.html", files=files, folders=folders,
                           all_folders=all_folders, current_folder=None, user=g.user)


@app.route("/upload", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def upload():
    if "file" not in request.files:
        flash("Brak pliku.", "danger")
        return redirect(url_for("dashboard"))

    # Optional: upload into a specific folder
    folder_id = request.form.get("folder_id", "").strip()
    target_folder = None
    if folder_id and folder_id.isdigit():
        target_folder = Folder.query.filter_by(id=int(folder_id), user_id=g.user.id).first()

    files = request.files.getlist("file")
    uploaded = 0
    for f in files:
        if not f.filename:
            continue
        if not allowed_file(f.filename):
            flash(f"Niedozwolony typ pliku: {f.filename}", "warning")
            continue
        original_name = secure_filename(f.filename)
        ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
        stored_name = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
        path = os.path.join(app.config["UPLOAD_FOLDER"], stored_name)
        f.save(path)
        size = os.path.getsize(path)
        if g.user.used_storage_mb + size / (1024 * 1024) > g.user.storage_limit_mb:
            os.remove(path)
            flash("Przekroczono limit miejsca na dysku.", "danger")
            break
        record = FileRecord(
            user_id=g.user.id,
            folder_id=target_folder.id if target_folder else None,
            original_name=original_name,
            stored_name=stored_name,
            size_bytes=size,
            mime_type=f.content_type,
        )
        db.session.add(record)
        db.session.commit()
        log_action("upload", detail=original_name)
        uploaded += 1
    if uploaded:
        flash(f"Przesłano {uploaded} plik(ów).", "success")

    if target_folder:
        return redirect(url_for("folder_view", folder_id=target_folder.id))
    return redirect(url_for("dashboard"))


@app.route("/file/<int:file_id>/download")
@login_required
def download_own(file_id):
    record = FileRecord.query.filter_by(id=file_id, user_id=g.user.id).first_or_404()
    path = os.path.join(app.config["UPLOAD_FOLDER"], record.stored_name)
    if not os.path.exists(path):
        abort(404)
    log_action("download_own", detail=record.original_name)
    return send_file(path, download_name=record.original_name, as_attachment=True)


@app.route("/file/<int:file_id>/delete", methods=["POST"])
@login_required
def delete_file(file_id):
    record = FileRecord.query.filter_by(id=file_id, user_id=g.user.id).first_or_404()
    folder_id = record.folder_id
    path = os.path.join(app.config["UPLOAD_FOLDER"], record.stored_name)
    if os.path.exists(path):
        os.remove(path)
    log_action("delete", detail=record.original_name)
    db.session.delete(record)
    db.session.commit()
    flash("Plik usunięty.", "success")
    if folder_id:
        return redirect(url_for("folder_view", folder_id=folder_id))
    return redirect(url_for("dashboard"))


@app.route("/file/<int:file_id>/move", methods=["POST"])
@login_required
def move_file(file_id):
    """Move a file to a different folder (or root if folder_id is empty)."""
    record = FileRecord.query.filter_by(id=file_id, user_id=g.user.id).first_or_404()
    old_folder_id = record.folder_id
    target_id = request.form.get("folder_id", "").strip()

    if target_id and target_id.isdigit():
        target_folder = Folder.query.filter_by(id=int(target_id), user_id=g.user.id).first()
        if not target_folder:
            flash("Folder nie istnieje.", "danger")
            return redirect(url_for("dashboard"))
        record.folder_id = target_folder.id
        flash(f"Plik przeniesiony do '{target_folder.name}'.", "success")
        log_action("move_file", detail=f"{record.original_name} -> folder {target_folder.id}")
    else:
        record.folder_id = None
        flash("Plik przeniesiony do katalogu głównego.", "success")
        log_action("move_file", detail=f"{record.original_name} -> root")

    db.session.commit()

    # Redirect back to where the user came from
    redirect_to = request.form.get("redirect_to", "")
    if redirect_to and redirect_to.isdigit():
        return redirect(url_for("folder_view", folder_id=int(redirect_to)))
    return redirect(url_for("dashboard"))


@app.route("/file/<int:file_id>/share", methods=["POST"])
@login_required
def share_file(file_id):
    record = FileRecord.query.filter_by(id=file_id, user_id=g.user.id).first_or_404()
    expires_hours = int(request.form.get("expires_hours", 24))
    password = request.form.get("share_password", "").strip()
    download_limit = request.form.get("download_limit", "").strip()

    record.share_token = secrets.token_urlsafe(32)
    record.share_expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    record.share_password_hash = generate_password_hash(password) if password else None
    record.download_limit = int(download_limit) if download_limit.isdigit() else None
    record.download_count = 0
    db.session.commit()
    log_action("share_created", detail=record.original_name)
    flash(f"Link do udostępniania: {record.share_url}", "success")

    if record.folder_id:
        return redirect(url_for("folder_view", folder_id=record.folder_id))
    return redirect(url_for("dashboard"))


@app.route("/file/<int:file_id>/unshare", methods=["POST"])
@login_required
def unshare_file(file_id):
    record = FileRecord.query.filter_by(id=file_id, user_id=g.user.id).first_or_404()
    folder_id = record.folder_id
    record.share_token = None
    record.share_expires_at = None
    record.share_password_hash = None
    record.download_limit = None
    db.session.commit()
    flash("Udostępnianie wyłączone.", "info")
    if folder_id:
        return redirect(url_for("folder_view", folder_id=folder_id))
    return redirect(url_for("dashboard"))


# ─── Folder routes ─────────────────────────────────────────────────────────────

@app.route("/folder/create", methods=["POST"])
@login_required
def create_folder():
    name = request.form.get("name", "").strip()
    parent_id = request.form.get("parent_id", "").strip()

    if not name:
        flash("Podaj nazwę folderu.", "danger")
        return redirect(url_for("dashboard"))
    if len(name) > 255:
        flash("Nazwa folderu jest za długa.", "danger")
        return redirect(url_for("dashboard"))

    parent_folder = None
    if parent_id and parent_id.isdigit():
        parent_folder = Folder.query.filter_by(id=int(parent_id), user_id=g.user.id).first()
        if not parent_folder:
            flash("Folder nadrzędny nie istnieje.", "danger")
            return redirect(url_for("dashboard"))

    # Prevent duplicate names within the same parent
    existing = Folder.query.filter_by(
        user_id=g.user.id,
        name=name,
        parent_id=parent_folder.id if parent_folder else None
    ).first()
    if existing:
        flash("Folder o tej nazwie już istnieje w tym miejscu.", "warning")
    else:
        folder = Folder(
            user_id=g.user.id,
            name=name,
            parent_id=parent_folder.id if parent_folder else None,
        )
        db.session.add(folder)
        db.session.commit()
        log_action("folder_created", detail=name)
        flash(f"Folder '{name}' zostal utworzony.", "success")

    if parent_folder:
        return redirect(url_for("folder_view", folder_id=parent_folder.id))
    return redirect(url_for("dashboard"))


@app.route("/folder/<int:folder_id>")
@login_required
def folder_view(folder_id):
    folder = get_user_folder(folder_id)
    subfolders = Folder.query.filter_by(user_id=g.user.id, parent_id=folder_id).order_by(Folder.name).all()
    files = FileRecord.query.filter_by(user_id=g.user.id, folder_id=folder_id).order_by(FileRecord.created_at.desc()).all()
    all_folders = Folder.query.filter_by(user_id=g.user.id).order_by(Folder.name).all()

    # Build breadcrumb trail
    breadcrumbs = []
    node = folder
    while node:
        breadcrumbs.insert(0, node)
        node = db.session.get(Folder, node.parent_id) if node.parent_id else None

    return render_template(
        "dashboard.html",
        files=files,
        folders=subfolders,
        all_folders=all_folders,
        current_folder=folder,
        breadcrumbs=breadcrumbs,
        user=g.user,
    )


@app.route("/folder/<int:folder_id>/rename", methods=["POST"])
@login_required
def rename_folder(folder_id):
    folder = get_user_folder(folder_id)
    new_name = request.form.get("name", "").strip()
    if not new_name:
        flash("Podaj nową nazwę folderu.", "danger")
        return redirect(url_for("folder_view", folder_id=folder_id))

    # Check for duplicate in the same parent
    existing = Folder.query.filter(
        Folder.user_id == g.user.id,
        Folder.name == new_name,
        Folder.parent_id == folder.parent_id,
        Folder.id != folder.id,
    ).first()
    if existing:
        flash("Folder o tej nazwie już istnieje w tym miejscu.", "warning")
    else:
        log_action("folder_renamed", detail=f"{folder.name} -> {new_name}")
        folder.name = new_name
        db.session.commit()
        flash("Folder został przemianowany.", "success")

    parent_id = folder.parent_id
    if parent_id:
        return redirect(url_for("folder_view", folder_id=parent_id))
    return redirect(url_for("dashboard"))


@app.route("/folder/<int:folder_id>/delete", methods=["POST"])
@login_required
def delete_folder(folder_id):
    folder = get_user_folder(folder_id)
    parent_id = folder.parent_id

    # Collect all descendant folder IDs to delete their files too
    all_folder_ids = [folder_id] + collect_descendant_ids(folder_id)

    # Delete physical files for all files in these folders
    for fid in all_folder_ids:
        records = FileRecord.query.filter_by(folder_id=fid).all()
        for record in records:
            path = os.path.join(app.config["UPLOAD_FOLDER"], record.stored_name)
            if os.path.exists(path):
                os.remove(path)

    log_action("folder_deleted", detail=folder.name)
    db.session.delete(folder)  # cascade will delete subfolders; files need manual cleanup above
    db.session.commit()
    flash(f"Folder '{folder.name}' i jego zawartosc zostaly usuniete.", "success")

    if parent_id:
        return redirect(url_for("folder_view", folder_id=parent_id))
    return redirect(url_for("dashboard"))


@app.route("/folder/<int:folder_id>/move", methods=["POST"])
@login_required
def move_folder(folder_id):
    """Move a folder to a different parent (or to root)."""
    folder = get_user_folder(folder_id)
    target_id = request.form.get("parent_id", "").strip()

    if target_id and target_id.isdigit():
        new_parent_id = int(target_id)
        # Prevent moving a folder into itself or its own descendants
        if new_parent_id == folder_id or new_parent_id in collect_descendant_ids(folder_id):
            flash("Nie można przenieść folderu do samego siebie ani jego podfolderów.", "danger")
            return redirect(url_for("folder_view", folder_id=folder_id))
        new_parent = Folder.query.filter_by(id=new_parent_id, user_id=g.user.id).first()
        if not new_parent:
            flash("Folder docelowy nie istnieje.", "danger")
            return redirect(url_for("folder_view", folder_id=folder_id))
        folder.parent_id = new_parent_id
        flash(f"Folder przeniesiony do '{new_parent.name}'.", "success")
        log_action("folder_moved", detail=f"{folder.name} -> {new_parent.name}")
    else:
        folder.parent_id = None
        flash("Folder przeniesiony do katalogu głównego.", "success")
        log_action("folder_moved", detail=f"{folder.name} -> root")

    db.session.commit()
    return redirect(url_for("folder_view", folder_id=folder_id))


# ─── Public share download ─────────────────────────────────────────────────────

@app.route("/s/<token>", methods=["GET", "POST"])
@limiter.limit("30 per hour")
def download_shared(token):
    record = FileRecord.query.filter_by(share_token=token).first_or_404()
    if not record.is_share_active:
        abort(410)

    if record.share_password_hash:
        if request.method == "POST":
            pwd = request.form.get("password", "")
            if not check_password_hash(record.share_password_hash, pwd):
                flash("Błędne hasło.", "danger")
                return render_template("share_password.html", token=token, file=record)
        else:
            return render_template("share_password.html", token=token, file=record)

    path = os.path.join(app.config["UPLOAD_FOLDER"], record.stored_name)
    if not os.path.exists(path):
        abort(404)

    record.download_count += 1
    db.session.commit()
    log_action("shared_download", detail=record.original_name, user_id=record.user_id)
    return send_file(path, download_name=record.original_name, as_attachment=True)


# ─── Admin panel ──────────────────────────────────────────────────────────────

@app.route("/admin")
@admin_required
def admin_panel():
    users = User.query.order_by(User.created_at.desc()).all()
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    total_files = FileRecord.query.count()
    total_size = db.session.query(db.func.sum(FileRecord.size_bytes)).scalar() or 0
    return render_template("admin.html", users=users, logs=logs,
                           total_files=total_files, total_size=total_size, user=g.user)


@app.route("/admin/user/<int:user_id>/toggle", methods=["POST"])
@admin_required
def admin_toggle_user(user_id):
    u = db.session.get(User, user_id)
    if not u:
        abort(404)
    u.is_active = not u.is_active
    db.session.commit()
    flash(f"Użytkownik {u.username}: {'aktywny' if u.is_active else 'zablokowany'}.", "info")
    return redirect(url_for("admin_panel"))


@app.route("/admin/user/<int:user_id>/storage", methods=["POST"])
@admin_required
def admin_set_storage(user_id):
    u = db.session.get(User, user_id)
    if not u:
        abort(404)
    limit = request.form.get("limit_mb", "2048")
    u.storage_limit_mb = int(limit)
    db.session.commit()
    flash(f"Limit miejsca dla {u.username} ustawiony na {limit} MB.", "success")
    return redirect(url_for("admin_panel"))


# ─── API ──────────────────────────────────────────────────────────────────────

@app.route("/api/files")
@login_required
def api_files():
    files = FileRecord.query.filter_by(user_id=g.user.id).all()
    return jsonify([{
        "id": f.id,
        "name": f.original_name,
        "size": f.size_bytes,
        "size_human": f.size_human,
        "folder_id": f.folder_id,
        "share_url": f.share_url,
        "share_active": f.is_share_active,
        "created_at": f.created_at.isoformat(),
    } for f in files])


@app.route("/api/folders")
@login_required
def api_folders():
    folders = Folder.query.filter_by(user_id=g.user.id).order_by(Folder.name).all()
    return jsonify([{
        "id": f.id,
        "name": f.name,
        "parent_id": f.parent_id,
        "full_path": f.full_path,
        "file_count": f.file_count,
        "created_at": f.created_at.isoformat(),
    } for f in folders])


# ─── Error handlers ───────────────────────────────────────────────────────────

@app.errorhandler(413)
def too_large(e):
    flash(f"Plik jest za duży. Maksymalny rozmiar to {app.config['MAX_CONTENT_LENGTH'] // (1024*1024)} MB.", "danger")
    return redirect(url_for("dashboard"))

@app.errorhandler(429)
def ratelimit_handler(e):
    return render_template("error.html", code=429,
                           message="Zbyt wiele żądań. Spróbuj ponownie za chwilę."), 429

@app.errorhandler(410)
def gone(e):
    return render_template("error.html", code=410,
                           message="Ten link wygasł lub przekroczono limit pobrań."), 410


# ─── Init ─────────────────────────────────────────────────────────────────────

def init_db():
    with app.app_context():
        db.create_all()
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)