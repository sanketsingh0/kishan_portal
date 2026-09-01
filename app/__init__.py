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

    # --- Blueprints ------------------------------------------------------------
    from app.routes.health import health_bp
    from app.routes.main import main_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(main_bp)

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