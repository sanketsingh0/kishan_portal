"""
KisanProcure entry point.

Loads environment variables from .env (if present), builds the Flask app
and runs the development server.

Usage:
    python run.py
    flask --app run.py run
"""

# --- Eventlet monkey-patching -------------------------------------------------
# MUST execute before any other import (Flask, Werkzeug, SQLAlchemy, Pydantic,
# etc.). When running under gunicorn's eventlet worker
# (`gunicorn -k eventlet -w 1 "run:app"`), gunicorn imports this module to
# obtain `app`. Patching here guarantees the standard-library sockets,
# threading and SSL modules are replaced with eventlet's cooperative
# versions before any dependency references them. This prevents the
# "RLock(s) were not greened" / "Working outside of context" errors.
import eventlet
eventlet.monkey_patch()

import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402  (dotenv must load before app imports)
from app.extensions import socketio

app = create_app()


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)