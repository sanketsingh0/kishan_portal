"""Health check endpoint.

Exposes a lightweight status probe used for deployments, uptime monitors
and a quick sanity check that the app boots correctly.
"""

from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from app.extensions import db

health_bp = Blueprint("health", __name__, url_prefix="/api/health")


@health_bp.get("")
@health_bp.get("/")
def health():
    """Return service status. Never returns 500 on a healthy-but-empty DB."""
    db_status = "ok"
    db_error = None
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - defensive probe
        db_status = "error"
        db_error = str(exc)

    return jsonify(
        status="ok",
        service="KisanProcure API",
        version=current_app.config.get("APP_VERSION"),
        environment=current_app.config.get("ENV", "development"),
        database=db_status,
        database_error=db_error,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )