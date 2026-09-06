"""Startup / production configuration tests (Issue A regression suite).

Production uses gunicorn's DEFAULT SYNC workers with Flask-SocketIO in
`threading` async mode:

    gunicorn -w 2 -b 0.0.0.0:$PORT run:app

Therefore the application must NOT depend on eventlet (or gevent): no
monkey-patching at import time, no eventlet imports, and the Socket.IO
/queue namespace must remain fully functional in threading mode.
"""

import sys
import threading as stdlib_threading


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
    """gunicorn (sync workers) is the production server; it must be available."""
    import gunicorn

    assert hasattr(gunicorn, "__version__")