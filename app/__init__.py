"""
KisanProcure application factory.

Creates a configured Flask application:

    from app import create_app
    app = create_app()                     # development (default)
    app = create_app("testing")
    app = create_app("production")
"""

import os

from dotenv import load_dotenv
from flask import Flask

from config import config_map, demo_seed_on_start_enabled
from app.extensions import db, migrate, scheduler, socketio
from app.cli import register_cli

# Imported for its side effect: registers all models on db.metadata so that
# Alembic/Flask-Migrate and db.create_all() can see them.
import app.models  # noqa: F401,E402

# Idempotent: no-op if run.py already loaded .env before importing this package.
load_dotenv()


def create_app(config_name: str | None = None) -> Flask:
    if config_name is None:
        config_name = (os.getenv("FLASK_ENV") or "development").lower()

    if config_name not in config_map:
        raise ValueError(
            f"Unknown configuration '{config_name}'. "
            f"Choose from: {', '.join(config_map)}"
        )

    app = Flask(__name__)
    app.config.from_object(config_map[config_name])

    # Runtime evaluation of DEMO_SEED_ON_START (the class attribute is computed
    # at config-module import time, so a value set right before create_app()
    # would otherwise be missed). Cleaned boolean lives in app.config.
    app.config["DEMO_SEED_ON_START"] = demo_seed_on_start_enabled()

    if app.config.get("ENV") == "production":
        _validate_production_config(app)

    os.makedirs(app.instance_path, exist_ok=True)

    # --- Extensions ----------------------------------------------------------
    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(
        app,
        async_mode=app.config.get("SOCKETIO_ASYNC_MODE", "threading"),
        cors_allowed_origins=app.config.get("CORS_ALLOWED_ORIGINS", "*"),
    )

    from app.queue.events import init_queue_events
    init_queue_events(socketio)

        # --- Blueprints ------------------------------------------------------------
    from app.routes.health import health_bp
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.farmers import farmers_bp
    from app.routes.centres import centres_bp
    from app.routes.crops import crops_bp
    from app.routes.slots import slots_bp
    from app.routes.bookings import bookings_bp
    from app.routes.queue import queue_bp
    from app.routes.procurement import procurement_bp
    from app.routes.payment import payment_bp
    from app.routes.delays import delays_bp
    from app.routes.notifications import notifications_bp
    from app.routes.admin import admin_bp
    from app.routes.staff import staff_bp
    from app.routes.public import public_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(farmers_bp)
    app.register_blueprint(centres_bp)
    app.register_blueprint(crops_bp)
    app.register_blueprint(slots_bp)
    app.register_blueprint(bookings_bp)
    app.register_blueprint(queue_bp)
    app.register_blueprint(procurement_bp)
    app.register_blueprint(payment_bp)
    app.register_blueprint(delays_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(public_bp)

    # --- Security Headers & Response Controls ------------------------------
    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        from flask import request
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return response

    # --- CLI commands (flask seed-demo, ...) -----------------------------------
    register_cli(app)

    # --- Demo seed on startup (OPT-IN) ------------------------------------------
    # When DEMO_SEED_ON_START=true, run the SAME idempotent non-destructive
    # seeder as `flask seed-demo-full` automatically at startup (after the DB
    # and app are initialized). This covers platforms without a Shell (e.g. the
    # current Render plan). Default is false — never auto-enabled in production.
    if app.config.get("DEMO_SEED_ON_START"):
        _seed_demo_on_startup(app)

    # --- Scheduling -------------------------------------------------------------
    # Never start background threads while running the test-suite.
    if not app.config.get("TESTING") and not scheduler.running:
        scheduler.start()

    return app


def _seed_demo_on_startup(app: Flask) -> None:
    """Run the existing full SIH demo seed at app startup (opt-in only).

    Reuses the exact implementation behind ``flask seed-demo-full``
    (``app.services.full_seed.seed_demo_full``) — no seed logic is duplicated
    here. The seeder is idempotent and non-destructive, so this is safe on
    every boot and never removes or modifies user data.
    """
    from app.services.full_seed import seed_demo_full

    with app.app_context():
        db.create_all()
        stats = seed_demo_full()

    app.logger.info(
        "DEMO_SEED_ON_START: full demo seed applied "
        "(centres new=%s, crops new=%s, staff new=%s, farmers new=%s, "
        "slots new=%s, bookings new=%s, delays new=%s, "
        "procurements new=%s, payments new=%s)",
        stats["centres"]["new"],
        stats["crops"]["new"],
        stats["staff"]["new"],
        stats["farmers"]["new"],
        stats["slots"]["new"],
        stats["bookings"]["new"],
        stats["delays"]["new"],
        stats["procurements"]["new"],
        stats["payments"]["new"],
    )


def _validate_production_config(app: Flask) -> None:
    """Fail fast at boot when a production deployment is misconfigured."""
    required = {
        "DATABASE_URL": app.config.get("SQLALCHEMY_DATABASE_URI"),
        "SECRET_KEY": app.config.get("SECRET_KEY"),
    }
    missing = [
        name
        for name, value in required.items()
        if not value or value == "dev-only-change-me"
    ]
    if missing:
        raise RuntimeError(
            "Production configuration is incomplete. "
            f"Set the following environment variables: {', '.join(missing)}"
        )

    uri = app.config.get("SQLALCHEMY_DATABASE_URI") or ""
    if not uri.startswith("postgres"):
        raise RuntimeError(
            "Production DATABASE_URL must point to PostgreSQL "
            "(e.g. postgresql+psycopg://...). Got a non-PostgreSQL URL. "
            "Use FLASK_ENV=development for the local SQLite database."
        )
