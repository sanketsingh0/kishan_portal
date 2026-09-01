"""
KisanProcure application configuration.

All secrets are read from environment variables (see .env.example).
Never commit `.env` and never hard-code keys or tokens in source code.
"""

import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _default_dev_database_uri() -> str:
    """SQLite database used automatically for local development.

    SQLAlchemy requires forward slashes in file URLs on Windows.
    """
    instance_dir = os.path.join(BASE_DIR, "instance")
    os.makedirs(instance_dir, exist_ok=True)
    db_path = os.path.join(instance_dir, "kisanprocure.db").replace("\\", "/")
    return f"sqlite:///{db_path}"


class Config:
    """Base configuration shared by all environments."""

    APP_VERSION = "0.1.0"

    # Environment name (used by the app factory, health check, etc.)
    ENV = "development"

    # Dev-only fallback; production requires a strong value from the environment.
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Keep these small - Refresh the connection before reuse (important for
    # hosted PostgreSQL such as Supabase where idle connections get dropped).
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }

    # --- Supabase (Auth); used once the authentication module is implemented ---
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    # --- JWT (verification of Supabase-issued tokens) ---
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXP = int(os.getenv("JWT_EXP", "3600"))

    # --- Realtime (Flask-SocketIO) ---
    # threading works on the built-in dev server (uses simple-websocket).
    SOCKETIO_ASYNC_MODE = os.getenv("SOCKETIO_ASYNC_MODE", "threading")
    CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")


class DevelopmentConfig(Config):
    ENV = "development"
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", _default_dev_database_uri())


class TestingConfig(Config):
    ENV = "testing"
    TESTING = True
    DEBUG = False
    # In-memory database: isolated per test (see tests/conftest.py).
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class ProductionConfig(Config):
    ENV = "production"
    DEBUG = False
    TESTING = False
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")


config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}