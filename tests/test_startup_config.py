"""Startup / production configuration tests (Issue A regression suite).

Production uses gunicorn's `gthread` worker class (single multi-threaded
worker) with Flask-SocketIO in `threading` async mode:

    gunicorn -c gunicorn.conf.py run:app

Therefore the application must NOT depend on eventlet (or gevent): no
monkey-patching at import time, no eventlet imports, and the Socket.IO
/queue namespace must remain fully functional in threading mode.

Additionally, the SQLAlchemy engine pool must be configured for safe
multi-threaded use so that connections can be returned from any thread
without triggering `RuntimeError: cannot notify on an un-acquired lock`
in `sqlalchemy/util/queue.py`.
"""

import sys
import threading as stdlib_threading
from config import Config, ProductionConfig


def _engine_options_for(cls):
    """Return the SQLALCHEMY_ENGINE_OPTIONS dict for a config class."""
    return getattr(cls, "SQLALCHEMY_ENGINE_OPTIONS", {})


def _engine_options(app):
    """Return the SQLAlchemy engine options dict for the given app."""
    return app.config.get("SQLALCHEMY_ENGINE_OPTIONS", {})


def test_base_engine_pool_reset_on_return():
    """`pool_reset_on_return` must be set in base Config for safe threading.

    Without a reset-on-return strategy, a connection returned from a thread
    other than the one that checked it out can leave the pool's internal
    `threading.Condition` in a state where `notify()` fails with
    `RuntimeError: cannot notify on an un-acquired lock`.
    """
    opts = _engine_options_for(Config)
    assert opts.get("pool_reset_on_return") == "rollback", (
        "SQLALCHEMY_ENGINE_OPTIONS['pool_reset_on_return'] must be 'rollback' "
        "so connections are cleanly reset regardless of which thread returns them"
    )


def test_base_engine_pool_pre_ping():
    """`pool_pre_ping` must be enabled in base Config.

    Supabase drops idle connections after a timeout.  Without pre-ping,
    pooled connections are reused after the server has closed them,
    producing `server closed the connection unexpectedly` errors.
    """
    opts = _engine_options_for(Config)
    assert opts.get("pool_pre_ping") is True, (
        "SQLALCHEMY_ENGINE_OPTIONS['pool_pre_ping'] must be True "
        "for Supabase PostgreSQL"
    )


def test_production_engine_pool_sized_for_threading():
    """Production pool must be sized to serve multiple threads concurrently.

    A single gthread worker runs 4+ threads (HTTP + SocketIO + APScheduler).
    The pool must allow enough connections so threads do not deadlock waiting
    for a free connection.
    """
    opts = _engine_options_for(ProductionConfig)
    pool_size = opts.get("pool_size", 0)
    max_overflow = opts.get("max_overflow", 0)
    assert pool_size >= 5, (
        f"pool_size must be >= 5 for threaded workers, got {pool_size}"
    )
    assert max_overflow >= 5, (
        f"max_overflow must be >= 5 for threaded workers, got {max_overflow}"
    )
    # Total available connections = pool_size + max_overflow
    assert (pool_size + max_overflow) >= 10, (
        f"pool_size + max_overflow must be >= 10, got {pool_size + max_overflow}"
    )


def test_production_engine_pool_recycle():
    """Production connections must be recycled before Supabase's idle timeout.

    Supabase closes idle connections after a period (typically ~10 min in the
    free tier).  pool_recycle forces SQLAlchemy to discard and replace
    connections before that timeout, preventing stale-connection errors.
    """
    opts = _engine_options_for(ProductionConfig)
    recycle = opts.get("pool_recycle", 0)
    assert recycle > 0, (
        f"SQLALCHEMY_ENGINE_OPTIONS['pool_recycle'] must be set, got {recycle}"
    )
    assert recycle <= 600, (
        f"pool_recycle should be <= 600 s (10 min) to beat Supabase idle "
        f"timeout, got {recycle}"
    )


def test_production_engine_pool_reset_on_return():
    """Production config must also set pool_reset_on_return."""
    opts = _engine_options_for(ProductionConfig)
    assert opts.get("pool_reset_on_return") == "rollback", (
        "ProductionConfig.SQLALCHEMY_ENGINE_OPTIONS['pool_reset_on_return'] "
        "must be 'rollback'"
    )


def test_production_engine_pool_pre_ping():
    """Production config must also enable pool_pre_ping."""
    opts = _engine_options_for(ProductionConfig)
    assert opts.get("pool_pre_ping") is True, (
        "ProductionConfig.SQLALCHEMY_ENGINE_OPTIONS['pool_pre_ping'] "
        "must be True"
    )


def test_production_pool_options_not_in_base_config():
    """QueuePool-specific options must NOT be in base Config.

    The base Config uses SQLite (StaticPool) in development and testing,
    which does not accept pool_size / max_overflow / pool_recycle.
    """
    base_opts = _engine_options_for(Config)
    assert "pool_size" not in base_opts, (
        "pool_size must not be in base Config (StaticPool rejects it)"
    )
    assert "max_overflow" not in base_opts, (
        "max_overflow must not be in base Config (StaticPool rejects it)"
    )
    assert "pool_recycle" not in base_opts, (
        "pool_recycle must not be in base Config (StaticPool rejects it)"
    )


def test_gunicorn_config_file_exists():
    """The gunicorn.conf.py file must exist for production deployment."""
    import os

    assert os.path.exists("gunicorn.conf.py"), (
        "gunicorn.conf.py must exist at the project root for production"
    )


def test_gunicorn_config_uses_gthread_worker():
    """gunicorn.conf.py must use the gthread worker class."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("gunicorn_conf", "gunicorn.conf.py")
    conf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conf)

    assert getattr(conf, "worker_class", None) == "gthread", (
        f"gunicorn.conf.py must set worker_class='gthread', "
        f"got {getattr(conf, 'worker_class', None)!r}"
    )


def test_gunicorn_config_single_worker():
    """gunicorn.conf.py must use a single worker for Socket.IO correctness.

    Multiple workers require an external message queue (Redis) for Socket.IO
    cross-worker messaging.  The app does not use one, so a single worker
    keeps Socket.IO room broadcasts working.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("gunicorn_conf", "gunicorn.conf.py")
    conf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conf)

    assert getattr(conf, "workers", None) == 1, (
        f"gunicorn.conf.py must set workers=1, got {getattr(conf, 'workers', None)!r}"
    )


def test_gunicorn_config_post_fork_hook():
    """gunicorn.conf.py must define a post_fork hook to dispose the pool.

    The post_fork hook disposes the inherited SQLAlchemy engine pool so the
    worker creates a fresh pool, avoiding the 'cannot notify on an un-acquired
    lock' RuntimeError from sharing forked threading primitives.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location("gunicorn_conf", "gunicorn.conf.py")
    conf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(conf)

    assert callable(getattr(conf, "post_fork", None)), (
        "gunicorn.conf.py must define a callable post_fork(server, worker) hook"
    )


def test_run_module_exposes_app_object_for_gunicorn():
    """`run:app` must be importable without starting a server (gunicorn entry)."""
    import run  # noqa: F401  (executes module top level: dotenv + create_app)

    from flask import Flask

    assert isinstance(run.app, Flask)


def test_eventlet_is_not_imported_after_run_module_load():
    """run.py must not import eventlet (no monkey-patching in the codebase)."""
    import run  # noqa: F401

    assert "eventlet" not in sys.modules, (
        "eventlet must not be imported by the application startup path"
    )


def test_stdlib_threading_is_not_monkey_patched():
    """Neither eventlet nor gevent may be loaded by the startup path.

    eventlet.monkey_patch() replaces stdlib threading/socket primitives with
    green versions (the source of the production "RLock was not greened"
    crashes). Loading run.py must leave the stdlib untouched.
    """
    import run  # noqa: F401

    for mod in ("eventlet", "eventlet.greenlet", "eventlet.green.threading", "gevent"):
        assert mod not in sys.modules, (
            f"{mod} must not be loaded by the application startup path"
        )
    # The stdlib threading module must be the real one, not eventlet's green shim.
    assert stdlib_threading.__name__ == "threading"
    assert not stdlib_threading.__file__.lower().startswith("eventlet")


def test_socketio_async_mode_is_threading(app):
    """Flask-SocketIO must run in threading mode (the only supported mode)."""
    from app.extensions import socketio

    assert app.config["SOCKETIO_ASYNC_MODE"] == "threading"
    assert socketio.async_mode == "threading"


def test_queue_namespace_connectable_in_threading_mode(app):
    """The /queue Socket.IO namespace stays functional in threading mode."""
    from app.extensions import socketio

    client = socketio.test_client(app, namespace="/queue")
    assert client.is_connected(namespace="/queue")
    client.disconnect(namespace="/queue")


def test_gunicorn_is_installed_for_production_workers():
    """gunicorn (gthread workers) is the production server; it must be available."""
    import gunicorn

    assert hasattr(gunicorn, "__version__")


def test_base_sqlalchemy_engine_options_are_dict():
    """Base Config SQLALCHEMY_ENGINE_OPTIONS must be a dict."""
    opts = _engine_options_for(Config)
    assert isinstance(opts, dict), (
        f"Config.SQLALCHEMY_ENGINE_OPTIONS must be a dict, got {type(opts).__name__}"
    )


def test_production_sqlalchemy_engine_options_are_dict():
    """ProductionConfig SQLALCHEMY_ENGINE_OPTIONS must be a dict."""
    opts = _engine_options_for(ProductionConfig)
    assert isinstance(opts, dict), (
        f"ProductionConfig.SQLALCHEMY_ENGINE_OPTIONS must be a dict, "
        f"got {type(opts).__name__}"
    )