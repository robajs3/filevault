import os
import secrets
import sso_client
from datetime import date
from flask import Flask, render_template, redirect, session, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import Config
from models import db, AppLink, User
from controllers import auth_bp, files_bp, folders_bp, share_bp, admin_bp, api_bp, rooms_bp, profile_bp

PREFIX = "/filevault"


def _create_filevault_user(hub_username: str):
    """Zakłada w FileVault nowe lokalne konto dla usera z LoginHub, który
    jeszcze nie miał tu żadnego konta (wywoływane przez
    sso_client.resolve_or_create_local_user przy pierwszej wizycie).
    Hasło jest losowe i nieznane nikomu — logowanie idzie wyłącznie przez SSO.
    get-or-create po username, żeby nie tworzyć duplikatu przy ewentualnym
    powtórnym wywołaniu (np. gdy zgłoszenie do Huba nie doszło za pierwszym razem).
    """
    existing = User.query.filter_by(username=hub_username).first()
    if existing:
        return existing.id, existing.username

    username = hub_username
    suffix = 1
    while User.query.filter_by(username=username).first():
        suffix += 1
        username = f"{hub_username}{suffix}"

    # email jest w FileVault wymagany i unikalny, a Hub go nie zna —
    # generujemy placeholder, user może go później zmienić w profilu.
    email = f"{username}@sso.local"
    while User.query.filter_by(email=email).first():
        suffix += 1
        email = f"{hub_username}{suffix}@sso.local"

    user = User(username=username, email=email)
    user.set_password(secrets.token_urlsafe(24))
    db.session.add(user)
    db.session.commit()
    return user.id, user.username

def create_app(config_class=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Extensions
    db.init_app(app)
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["200 per hour", "50 per minute"],
        storage_uri=app.config["REDIS_URL"],
    )

    # Apply rate limits to specific blueprints/routes
    limiter.limit("100 per minute")(auth_bp)
    limiter.limit("50 per hour")(auth_bp)
    limiter.limit("30 per hour")(share_bp)

    # Miniaturki i podgląd pliku to statyczne serwowanie — wyłączamy limiter,
    # żeby dashboard z wieloma plikami nie wyczerpywał puli requestów.
    from controllers.files import thumbnail, preview_file, download_own
    limiter.exempt(thumbnail)
    limiter.exempt(preview_file)
    limiter.exempt(download_own)

    # Pozostałe operacje na plikach (upload, share, delete, rename, move) — limit
    limiter.limit("60 per hour")(files_bp)

    # Blueprints z prefixem
    app.register_blueprint(auth_bp,    url_prefix=PREFIX)
    app.register_blueprint(files_bp,   url_prefix=PREFIX)
    app.register_blueprint(folders_bp, url_prefix=PREFIX)
    app.register_blueprint(share_bp,   url_prefix=PREFIX)
    app.register_blueprint(admin_bp,   url_prefix=PREFIX + "/admin")
    app.register_blueprint(api_bp,     url_prefix=PREFIX + "/api")
    app.register_blueprint(rooms_bp,   url_prefix=PREFIX)
    app.register_blueprint(profile_bp, url_prefix=PREFIX)

    @app.route("/")
    def index():
        apps = AppLink.query.filter_by(is_enabled=True).order_by(AppLink.sort_order, AppLink.name).all()
        return render_template("launcher.html", apps=apps)

    # Misc routes
    @app.route(PREFIX + "/privacy")
    def privacy():
        return render_template("privacy.html", now=date.today().strftime("%d.%m.%Y"))

    # Error handlers
    @app.errorhandler(413)
    def too_large(e):
        from flask import flash, redirect, url_for
        flash(
            f"Plik jest za duży. Maksymalny rozmiar to "
            f"{app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB.",
            "danger",
        )
        return redirect(url_for("files.dashboard"))

    @app.errorhandler(429)
    def ratelimit_handler(e):
        return render_template("error.html", code=429,
                               message="Zbyt wiele żądań. Spróbuj ponownie za chwilę."), 429

    @app.errorhandler(410)
    def gone(e):
        return render_template("error.html", code=410,
                               message="Ten link wygasł lub przekroczono limit pobrań."), 410

    @app.before_request
    def _sso_autologin():
        if session.get("user_id"):
            return
        local_id = sso_client.resolve_or_create_local_user(
            app_slug="filevault", create_user=_create_filevault_user
        )
        if local_id:
            session.permanent = True
            session["user_id"] = local_id

    # ── Ochrona przed clickjackingiem + świadomy wyjątek dla Koloseum ──────
    # Domyślnie ŻADNA strona FileVault nie może być osadzona w <iframe> na
    # obcej stronie (to był dotąd brak — żaden nagłówek w ogóle nie był
    # ustawiany, więc każda strona, łącznie z prywatnym dashboardem, mogła
    # zostać wrobiona w iframe na dowolnej stronie trzeciej). Jedyny
    # świadomy wyjątek to publiczna strona udostępnionego folderu
    # (share.shared_folder — /sf/<token>), którą Koloseum chce pokazywać
    # w podglądzie inline. Tam pozwalamy na framing wyłącznie z originów
    # wymienionych w FRAME_ALLOWED_ORIGINS (patrz config.py).
    EMBEDDABLE_ENDPOINTS = {"share.shared_folder", "share.shared_room", "share.shared_room_folder"}

    @app.after_request
    def _set_frame_headers(response):
        if request.endpoint in EMBEDDABLE_ENDPOINTS and app.config["FRAME_ALLOWED_ORIGINS"]:
            allowed = " ".join(app.config["FRAME_ALLOWED_ORIGINS"])
            # CSP frame-ancestors > X-Frame-Options (wspierane przez wszystkie
            # nowoczesne przeglądarki) — dlatego dla tej trasy w ogóle nie
            # ustawiamy X-Frame-Options, żeby go nie zostawić jako sprzeczny,
            # bardziej restrykcyjny fallback dla starszych przeglądarek.
            response.headers["Content-Security-Policy"] = f"frame-ancestors 'self' {allowed}"
        else:
            response.headers["X-Frame-Options"] = "DENY"
            response.headers.setdefault("Content-Security-Policy", "frame-ancestors 'none'")
        return response

    return app

def init_db(app: Flask) -> None:
    with app.app_context():
        db.create_all()
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        os.makedirs(app.config["THUMBNAIL_FOLDER"], exist_ok=True)


if __name__ == "__main__":
    application = create_app()
    init_db(application)
    application.run(host="0.0.0.0", port=5000, debug=False)
