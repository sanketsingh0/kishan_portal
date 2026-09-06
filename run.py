"""
KisanProcure entry point.

Loads environment variables from .env (if present), builds the Flask app
and runs the development server.

Production (Render) starts the same `app` object with gunicorn's default
SYNC workers (`gunicorn -w 2 -b 0.0.0.0:$PORT run:app`) while Flask-SocketIO
runs in `threading` async mode, so no eventlet/gevent monkey-patching is
required anywhere in the codebase.

Usage:
    python run.py
    flask --app run.py run
    gunicorn -w 2 -b 0.0.0.0:5000 run:app   # production
"""

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