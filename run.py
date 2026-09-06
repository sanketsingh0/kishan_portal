"""
KisanProcure entry point.

Loads environment variables from .env (if present), builds the Flask app
and runs the development server.

Production (Render) starts the same `app` object with gunicorn's `gthread`
worker class (single multi-threaded worker) while Flask-SocketIO runs in
`threading` async mode.  No eventlet/gevent monkey-patching is required.

The accompanying `gunicorn.conf.py` sets workers=1, threads=4 and registers
a `post_fork` hook that disposes the inherited SQLAlchemy engine pool so
each worker creates its own fresh pool (avoids the "cannot notify on an
un-acquired lock" RuntimeError in sqlalchemy/util/queue.py).

Usage:
    python run.py
    flask --app run.py run
    gunicorn -c gunicorn.conf.py run:app      # production (recommended)
    gunicorn -w 1 --threads 4 -b 0.0.0.0:5000 run:app  # production (alt)
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