from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, g
from models import User, FileRecord, AuditLog, AppLink, db
from .decorators import admin_required
from services.settings_service import (
    get_default_max_upload_mb, set_default_max_upload_mb,
    MIN_UPLOAD_MB, MAX_UPLOAD_MB_CEILING,
)

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/")
@admin_required
def admin_panel():
    users = User.query.order_by(User.created_at.desc()).all()
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    total_files = FileRecord.query.count()
    total_size = db.session.query(db.func.sum(FileRecord.size_bytes)).scalar() or 0
    apps = AppLink.query.order_by(AppLink.sort_order, AppLink.name).all()
    return render_template("admin.html", users=users, logs=logs,
                           total_files=total_files, total_size=total_size,
                           apps=apps, app_icons=AppLink.ICONS, app_colors=AppLink.COLORS,
                           default_max_upload_mb=get_default_max_upload_mb(),
                           user=g.user)


@admin_bp.route("/user/<int:user_id>/toggle", methods=["POST"])
@admin_required
def toggle_user(user_id):
    u = db.session.get(User, user_id)
    if not u:
        abort(404)
    u.is_active = not u.is_active
    db.session.commit()
    flash(f"Użytkownik {u.username}: {'aktywny' if u.is_active else 'zablokowany'}.", "info")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/user/<int:user_id>/storage", methods=["POST"])
@admin_required
def set_storage(user_id):
    u = db.session.get(User, user_id)
    if not u:
        abort(404)
    limit = request.form.get("limit_mb", "2048")
    u.storage_limit_mb = int(limit)
    db.session.commit()
    flash(f"Limit miejsca dla {u.username} ustawiony na {limit} MB.", "success")
    return redirect(url_for("admin.admin_panel"))


# ═══════════════ Limit rozmiaru pojedynczego pliku ═══════════════

def _parse_upload_mb(raw: str):
    """Zwraca int w dozwolonym zakresie albo None, gdy wartość jest niepoprawna."""
    raw = (raw or "").strip()
    if not raw.isdigit():
        return None
    mb = int(raw)
    return mb if MIN_UPLOAD_MB <= mb <= MAX_UPLOAD_MB_CEILING else None


@admin_bp.route("/settings/max-upload", methods=["POST"])
@admin_required
def set_default_max_upload():
    mb = _parse_upload_mb(request.form.get("max_upload_mb"))
    if mb is None:
        flash(f"Podaj liczbę całkowitą MB od {MIN_UPLOAD_MB} do {MAX_UPLOAD_MB_CEILING}.", "danger")
    else:
        set_default_max_upload_mb(mb)
        flash(f"Domyślny maksymalny rozmiar pliku ustawiony na {mb} MB.", "success")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/user/<int:user_id>/max-upload", methods=["POST"])
@admin_required
def set_user_max_upload(user_id):
    u = db.session.get(User, user_id)
    if not u:
        abort(404)
    raw = request.form.get("max_upload_mb", "").strip()
    if raw == "":
        u.max_upload_mb = None
        db.session.commit()
        flash(f"{u.username}: używa domyślnego limitu pliku ({get_default_max_upload_mb()} MB).", "info")
    else:
        mb = _parse_upload_mb(raw)
        if mb is None:
            flash(f"Podaj liczbę całkowitą MB od {MIN_UPLOAD_MB} do {MAX_UPLOAD_MB_CEILING} "
                  f"(puste pole = limit domyślny).", "danger")
        else:
            u.max_upload_mb = mb
            db.session.commit()
            flash(f"Maksymalny rozmiar pliku dla {u.username} ustawiony na {mb} MB.", "success")
    return redirect(url_for("admin.admin_panel"))


# ═══════════════ Zarządzanie aplikacjami (launcher) ═══════════════

@admin_bp.route("/apps/create", methods=["POST"])
@admin_required
def create_app_link():
    slug = request.form.get("slug", "").strip().lower()
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    description = request.form.get("description", "").strip()
    icon = request.form.get("icon", "app")
    color = request.form.get("color", "blue")
    sort_order = request.form.get("sort_order", "0")

    if not slug or not name:
        flash("Podaj przynajmniej slug i nazwę aplikacji.", "danger")
        return redirect(url_for("admin.admin_panel"))

    if AppLink.query.filter_by(slug=slug).first():
        flash(f"Aplikacja o slugu „{slug}” już istnieje.", "danger")
        return redirect(url_for("admin.admin_panel"))

    if icon not in AppLink.ICONS:
        icon = "app"
    if color not in AppLink.COLORS:
        color = "blue"

    app_link = AppLink(
        slug=slug, name=name, url=url, description=description or None,
        icon=icon, color=color,
        sort_order=int(sort_order) if sort_order.lstrip("-").isdigit() else 0,
    )
    db.session.add(app_link)
    db.session.commit()
    flash(f"Dodano aplikację „{name}” do launchera.", "success")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/apps/<int:app_id>/update", methods=["POST"])
@admin_required
def update_app_link(app_id):
    app_link = db.session.get(AppLink, app_id)
    if not app_link:
        abort(404)

    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    description = request.form.get("description", "").strip()
    icon = request.form.get("icon", app_link.icon)
    color = request.form.get("color", app_link.color)
    sort_order = request.form.get("sort_order", str(app_link.sort_order))

    if name:
        app_link.name = name
    app_link.url = url
    app_link.description = description or None
    if icon in AppLink.ICONS:
        app_link.icon = icon
    if color in AppLink.COLORS:
        app_link.color = color
    if sort_order.lstrip("-").isdigit():
        app_link.sort_order = int(sort_order)

    db.session.commit()
    flash(f"Zaktualizowano aplikację „{app_link.name}”.", "success")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/apps/<int:app_id>/toggle-enabled", methods=["POST"])
@admin_required
def toggle_app_enabled(app_id):
    app_link = db.session.get(AppLink, app_id)
    if not app_link:
        abort(404)
    app_link.is_enabled = not app_link.is_enabled
    db.session.commit()
    flash(
        f"Aplikacja „{app_link.name}”: {'widoczna' if app_link.is_enabled else 'ukryta'} w launcherze.",
        "info",
    )
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/apps/<int:app_id>/toggle-maintenance", methods=["POST"])
@admin_required
def toggle_app_maintenance(app_id):
    app_link = db.session.get(AppLink, app_id)
    if not app_link:
        abort(404)
    app_link.is_maintenance = not app_link.is_maintenance
    db.session.commit()
    flash(
        f"Aplikacja „{app_link.name}”: "
        f"{'oznaczona jako niedostępna (konserwacja)' if app_link.is_maintenance else 'znów dostępna'}.",
        "info",
    )
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/apps/<int:app_id>/delete", methods=["POST"])
@admin_required
def delete_app_link(app_id):
    app_link = db.session.get(AppLink, app_id)
    if not app_link:
        abort(404)
    name = app_link.name
    db.session.delete(app_link)
    db.session.commit()
    flash(f"Usunięto aplikację „{name}” z launchera.", "info")
    return redirect(url_for("admin.admin_panel"))
