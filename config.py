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


def demo_seed_on_start_enabled() -> bool:
    """Return True when ``DEMO_SEED_ON_START`` is set to a truthy value.

    When enabled, the application automatically runs the SAME idempotent,
    non-destructive seeder behind ``flask seed-demo-full`` during startup,
    after the database and app are initialized. This is useful on platforms
    without a Shell (e.g. the current Render plan), where running the Flask
    CLI command manually is not possible.

    ``DEMO_SEED_ON_START`` is parsed at application-factory time so it is
    safe to change it right before creating the app (which is also what the
    test-suite relies on). Default: OFF.
    """
    return os.getenv("DEMO_SEED_ON_START", "false").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


class Config:
    """Base configuration shared by all environments."""

    APP_VERSION = "0.1.0"

    # Environment name (used by the app factory, health check, etc.)
    ENV = "development"

    # Dev-only fallback; production requires a strong value from the environment.
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Pool options that are SAFE for ALL pool types (StaticPool for SQLite,
    # QueuePool for PostgreSQL).  QueuePool-specific options (pool_size,
    # max_overflow, pool_recycle) are set in ProductionConfig below.
    #
    # - pool_pre_ping: verify each connection before reuse (Supabase drops
    #   idle connections; this prevents "server closed the connection" errors).
    # - pool_reset_on_return: "rollback" ensures connections are cleanly reset
    #   when returned from ANY thread, preventing the "cannot notify on an
    #   un-acquired lock" RuntimeError that occurs when a connection is
    #   returned from a different thread than the one that checked it out.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_reset_on_return": "rollback",
    }

    # --- Supabase (Auth) ------------------------------------------------------
    # Canonical names are preferred; legacy aliases (
    # SUPABASE_PUBLISHABLE_KEY / SUPABASE_SECRET_KEY) are also supported so
    # existing `.env` files keep working without changes.
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_ANON_KEY = (
        os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("SUPABASE_PUBLISHABLE_KEY")
    )
    SUPABASE_SERVICE_ROLE_KEY = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SECRET_KEY")
    )
    SUPABASE_JWT_AUDIENCE = os.getenv("SUPABASE_JWT_AUDIENCE", "") or SUPABASE_ANON_KEY

    # --- JWT (verification of Supabase-issued tokens) ---
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXP = int(os.getenv("JWT_EXP", "3600"))

    # --- Realtime (Flask-SocketIO) ---
    # `threading` is the only supported async mode: it works on the built-in
    # dev server and under gunicorn's default sync workers (no eventlet /
    # gevent required). Left as an env knob for forward compatibility.
    SOCKETIO_ASYNC_MODE = os.getenv("SOCKETIO_ASYNC_MODE", "threading")
    CORS_ALLOWED_ORIGINS = os.getenv("CORS_ALLOWED_ORIGINS", "*").split(",")

    # --- Demo seed on startup (OPT-IN) ---------------------------------------
    # When true, the app runs the existing idempotent `flask seed-demo-full`
    # seeder automatically at startup (after the DB is ready). This is a
    # fallback for platforms without a Shell (e.g. the current Render plan).
    # Disabled by default and never auto-enabled in normal production.
    # NOTE: create_app() re-evaluates the environment at runtime and stores
    # the parsed boolean in app.config, so this class attribute is primarily
    # documentation + the default for anything that reads the class directly.
    DEMO_SEED_ON_START = demo_seed_on_start_enabled()


class DevelopmentConfig(Config):
    ENV = "development"
    DEBUG = True
    # Treat an empty DATABASE_URL as unset so the documented local workflow
    # ("leave DATABASE_URL blank to use SQLite") works even after copying
    # .env.example -> .env (which sets an empty placeholder).
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or _default_dev_database_uri()


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

    # QueuePool-specific options for PostgreSQL production.
    # These are NOT valid for SQLite's StaticPool (used in dev/test), so they
    # are set here rather than in the base Config.
    #
    # - pool_size / max_overflow: sized for a single gthread worker with
    #   multiple threads (HTTP + SocketIO background threads + APScheduler).
    # - pool_recycle: recycle connections before Supabase's idle timeout.
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_reset_on_return": "rollback",
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 300,
    }


config_map = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}