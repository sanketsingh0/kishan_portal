"""Smoke tests for the configuration system."""

import importlib

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


def test_supabase_legacy_key_names_supported(monkeypatch):
    """Legacy SUPABASE_PUBLISHABLE_KEY / SUPABASE_SECRET_KEY names work."""
    import config as config_module

    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "legacy-anon-key")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "legacy-service-role-key")
    monkeypatch.delenv("SUPABASE_ANON_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    importlib.reload(config_module)

    assert config_module.Config.SUPABASE_ANON_KEY == "legacy-anon-key"
    assert config_module.Config.SUPABASE_SERVICE_ROLE_KEY == "legacy-service-role-key"
    assert config_module.Config.SUPABASE_URL == "https://project.supabase.co"


def test_supabase_canonical_key_names_take_precedence(monkeypatch):
    """Canonical names win when both naming schemes are present."""
    import config as config_module

    monkeypatch.setenv("SUPABASE_URL", "https://project.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "canonical-anon-key")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "legacy-anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "canonical-service-key")
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "legacy-service-key")

    importlib.reload(config_module)

    assert config_module.Config.SUPABASE_ANON_KEY == "canonical-anon-key"
    assert config_module.Config.SUPABASE_SERVICE_ROLE_KEY == "canonical-service-key"