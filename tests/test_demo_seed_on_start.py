"""Tests for the OPT-IN ``DEMO_SEED_ON_START`` startup seeder.

Requirement: on platforms without a Shell (e.g. the current Render plan) the
``flask seed-demo-full`` CLI command cannot be run manually, so the same
idempotent seeder must be runnable automatically at application startup.

These tests prove:
- default (unset / ``false``) does NOT seed on startup,
- ``DEMO_SEED_ON_START=true`` triggers the EXISTING ``seed_demo_full``
  implementation during startup (verified both by dataset presence and by a
  spy on the real function — no seed logic is duplicated),
- repeated startup runs do not duplicate data (idempotent / non-destructive).
"""

import config as config_module
from sqlalchemy import create_engine

import app.models  # noqa: F401  (registers every model on db.metadata)
from app import create_app
from app.extensions import db
from app.models import Booking, Centre, Crop, Farmer, Slot, Staff, User


def _file_db_uri(tmp_path):
    """Return a temp-file SQLite URI (persistent across app instances)."""
    return "sqlite:///" + (tmp_path / "seed_on_start.db").as_posix()


def _prepare_file_db(uri):
    """Create the full schema in a temp-file DB (stand-in for migrations)."""
    engine = create_engine(uri)
    try:
        db.metadata.create_all(engine)
    finally:
        engine.dispose()


def _make_startup_app(monkeypatch, tmp_path, flag):
    """Point TestingConfig at a fresh file DB and build the app once."""
    uri = _file_db_uri(tmp_path)
    _prepare_file_db(uri)
    monkeypatch.setattr(config_module.TestingConfig, "SQLALCHEMY_DATABASE_URI", uri)
    monkeypatch.setenv("DEMO_SEED_ON_START", flag)
    return create_app("testing"), uri


def test_default_false_does_not_seed(monkeypatch, tmp_path):
    app, uri = _make_startup_app(monkeypatch, tmp_path, "false")

    assert app.config["DEMO_SEED_ON_START"] is False
    with app.app_context():
        db.create_all()
        assert User.query.count() == 0
        assert Centre.query.count() == 0
        assert Crop.query.count() == 0
        assert Slot.query.count() == 0
        assert Booking.query.count() == 0


def test_unset_var_defaults_to_false_and_does_not_seed(monkeypatch, tmp_path):
    uri = _file_db_uri(tmp_path)
    _prepare_file_db(uri)
    monkeypatch.setattr(config_module.TestingConfig, "SQLALCHEMY_DATABASE_URI", uri)
    monkeypatch.delenv("DEMO_SEED_ON_START", raising=False)

    app = create_app("testing")

    assert app.config["DEMO_SEED_ON_START"] is False
    with app.app_context():
        db.create_all()
        assert Centre.query.count() == 0
        assert User.query.count() == 0


def test_true_triggers_existing_full_seed_on_startup(monkeypatch, tmp_path):
    app, _ = _make_startup_app(monkeypatch, tmp_path, "true")

    assert app.config["DEMO_SEED_ON_START"] is True
    with app.app_context():
        # Exactly the dataset that `flask seed-demo-full` creates.
        assert Centre.query.count() == 2
        assert Crop.query.count() == 6
        assert Staff.query.count() == 2
        assert Farmer.query.count() == 5
        assert User.query.count() == 7  # 2 staff users + 5 farmer users
        assert Slot.query.count() == 5
        assert Booking.query.count() == 5


def test_true_invokes_the_existing_seed_demo_full_function(monkeypatch, tmp_path):
    """Prove the startup hook calls the real `seed_demo_full` (no duplication)."""
    uri = _file_db_uri(tmp_path)
    _prepare_file_db(uri)
    monkeypatch.setattr(config_module.TestingConfig, "SQLALCHEMY_DATABASE_URI", uri)
    monkeypatch.setenv("DEMO_SEED_ON_START", "true")

    import app.services.full_seed as full_seed_module

    original_seed = full_seed_module.seed_demo_full
    calls = []

    def _spy():
        calls.append(True)
        return original_seed()

    monkeypatch.setattr(full_seed_module, "seed_demo_full", _spy)

    create_app("testing")

    assert calls == [True]


def test_repeated_startup_does_not_duplicate_data(monkeypatch, tmp_path):
    uri = _file_db_uri(tmp_path)
    _prepare_file_db(uri)
    monkeypatch.setattr(config_module.TestingConfig, "SQLALCHEMY_DATABASE_URI", uri)
    monkeypatch.setenv("DEMO_SEED_ON_START", "true")

    create_app("testing")  # first startup seeds
    counts_after_first = None
    with create_app("testing").app_context():  # second startup must not duplicate
        counts_after_first = {
            "users": User.query.count(),
            "centres": Centre.query.count(),
            "crops": Crop.query.count(),
            "slots": Slot.query.count(),
            "bookings": Booking.query.count(),
        }

    with create_app("testing").app_context():  # third startup: still identical
        counts_after_third = {
            "users": User.query.count(),
            "centres": Centre.query.count(),
            "crops": Crop.query.count(),
            "slots": Slot.query.count(),
            "bookings": Booking.query.count(),
        }

    assert counts_after_first == {
        "users": 7,
        "centres": 2,
        "crops": 6,
        "slots": 5,
        "bookings": 5,
    }
    assert counts_after_third == counts_after_first


def test_truthy_env_values_enable_and_falsy_disable(monkeypatch, tmp_path):
    for truthy in ("1", "yes", "on", "TRUE"):
        uri = _file_db_uri(tmp_path)
        _prepare_file_db(uri)
        monkeypatch.setattr(
            config_module.TestingConfig, "SQLALCHEMY_DATABASE_URI", uri
        )
        monkeypatch.setenv("DEMO_SEED_ON_START", truthy)
        app = create_app("testing")
        assert app.config["DEMO_SEED_ON_START"] is True, truthy

    for falsy in ("0", "no", "off", "FALSE", ""):
        monkeypatch.setenv("DEMO_SEED_ON_START", falsy)
        app = create_app("testing")
        assert app.config["DEMO_SEED_ON_START"] is False, falsy