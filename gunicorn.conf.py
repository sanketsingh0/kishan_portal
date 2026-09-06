# Gunicorn configuration for KisanProcure production deployment.
#
# Uses the gthread worker class (multi-threaded sync workers) with
# Flask-SocketIO in `threading` async mode.
#
# Rationale for workers=1:
#   Flask-SocketIO in threading mode does not share state between workers.
#   Without a message queue (Redis/RabbitML), SocketIO events emitted by one
#   worker cannot reach clients connected to another worker. A single
#   gthread worker with multiple threads handles both HTTP and WebSocket
#   connections correctly while keeping all local state (rooms, queues)
#   in one process.
#
# Rationale for post_fork:
#   After fork() each worker inherits the master's SQLAlchemy engine pool.
#   That pool's internal threading.Lock/Condition objects are not safe to
#   share across the fork boundary. post_fork disposes the inherited pool so
#   the worker creates its own fresh engine on first use.

import os

# Server socket
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:" + os.environ.get("PORT", "5000"))

# Worker processes: single gthread worker (see rationale above)
workers = 1
threads = 4
worker_class = "gthread"

# Request handling
worker_connections = 1000
timeout = 120
graceful_timeout = 30
keepalive = 5

# Preload app to share memory between threads (safe: engine is disposed post-fork)
preload_app = False

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"

# Server mechanics
max_requests = 1000
max_requests_jitter = 50


def post_fork(server, worker):
    """Dispose of the inherited SQLAlchemy engine after fork().

    Each Gunicorn worker is forked from the master process, which imported
    `run` and thus created the Flask app and (lazily) the SQLAlchemy engine
    pool.  Threading primitives inherited across fork() are not safe: the
    pool's internal Condition/Lock objects may hold state from the master's
    threads that no longer exist.

    Disposing the engine closes all pooled connections and resets the pool,
    so the worker creates a fresh engine (and fresh connections) on first
    database access.
    """
    try:
        from run import app
        from app.extensions import db

        with app.app_context():
            db.engine.dispose()
        server.log.info(
            "worker %s: disposed inherited SQLAlchemy engine pool", worker.pid
        )
    except Exception as exc:  # noqa: BLE001 — startup must not fail
        server.log.error(
            "worker %s: failed to dispose SQLAlchemy engine: %s",
            worker.pid,
            exc,
        )