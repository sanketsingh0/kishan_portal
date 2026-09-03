"""
Unit and Integration test suite for Task 15 — Security & Production Configuration.

Tests security headers, API no-store cache control headers, error response sanitization,
and production configuration fail-fast validation rules.
"""

import pytest
from app import create_app, _validate_production_config


def test_security_headers_present(client):
    """Verify HTTP responses include standard security headers."""
    res = client.get("/api/health")
    assert res.status_code == 200

    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert res.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


def test_api_no_store_cache_control(client):
    """Verify API endpoints append Cache-Control: no-store header to protect private data."""
    res = client.get("/api/health")
    assert res.status_code == 200
    cache_header = res.headers.get("Cache-Control", "")
    assert "no-store" in cache_header
    assert "no-cache" in cache_header


def test_error_response_no_traceback_exposure(client):
    """Verify 404 and 400 errors return sanitized responses without raw tracebacks."""
    res = client.get("/api/non-existent-endpoint-xyz")
    assert res.status_code == 404
    body = res.data.decode("utf-8")
    assert "Traceback" not in body
    assert "sqlalchemy" not in body.lower()
    assert "secret" not in body.lower()


def test_production_config_validation_failures(app):
    """Verify production boot fails fast when required env variables are missing or insecure."""
    # 1. Missing secret key
    with app.app_context():
        app.config["ENV"] = "production"
        app.config["SECRET_KEY"] = "dev-only-change-me"
        app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql+psycopg://user:pass@localhost/db"

        with pytest.raises(RuntimeError) as exc_info:
            _validate_production_config(app)
        assert "Production configuration is incomplete" in str(exc_info.value)

    # 2. SQLite in production
    with app.app_context():
        app.config["ENV"] = "production"
        app.config["SECRET_KEY"] = "super-secret-prod-key-123!"
        app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///dev.db"

        with pytest.raises(RuntimeError) as exc_info:
            _validate_production_config(app)
        assert "must point to PostgreSQL" in str(exc_info.value)
