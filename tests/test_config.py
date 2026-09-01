"""Smoke tests for the configuration system."""

from app import create_app


def test_create_app_defaults_to_development():
    app = create_app()
    assert app.config["ENV"] == "development"
    assert app.config["APP_VERSION"] == "0.1.0"


def test_testing_config_uses_isolated_in_memory_database():
    app = create_app("testing")
    assert app.config["TESTING"] is True
    assert app.config["ENV"] == "testing"
    assert app.config["SQLALCHEMY_DATABASE_URI"] == "sqlite:///:memory:"


def test_unknown_config_is_rejected():
    try:
        create_app("not-a-real-config")
    except ValueError as exc:
        assert "Unknown configuration" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unknown config name")