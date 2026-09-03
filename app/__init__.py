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

from config import config_map
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

    app.register_blueprint(health_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(farmers_bp)
    app.register_blueprint(centres_bp)
    app.register_blueprint(crops_bp)
    app.register_blueprint(slots_bp)
    app.register_blueprint(bookings_bp)
    app.register_blueprint(queue_bp)

    # --- CLI commands (flask seed-demo, ...) -----------------------------------
    register_cli(app)

    # --- Scheduling -------------------------------------------------------------
    # Never start background threads while running the test-suite.
    if not app.config.get("TESTING") and not scheduler.running:
        scheduler.start()

    return app


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
