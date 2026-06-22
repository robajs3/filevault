import os
from datetime import date
from flask import Flask, render_template, redirect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import Config
from models import db
from controllers import auth_bp, files_bp, folders_bp, share_bp, admin_bp, api_bp

PREFIX = "/filevault"

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
    limiter.limit("30 per hour")(files_bp)
    limiter.limit("30 per hour")(share_bp)

    # Blueprints z prefixem
    app.register_blueprint(auth_bp,    url_prefix=PREFIX)
    app.register_blueprint(files_bp,   url_prefix=PREFIX)
    app.register_blueprint(folders_bp, url_prefix=PREFIX)
    app.register_blueprint(share_bp,   url_prefix=PREFIX)
    app.register_blueprint(admin_bp,   url_prefix=PREFIX + "/admin")
    app.register_blueprint(api_bp,     url_prefix=PREFIX + "/api")

    # Redirect z / na /filevault/
    @app.route("/")
    def index():
        return redirect(PREFIX + "/")

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
