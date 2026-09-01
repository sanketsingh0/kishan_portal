"""
Centralised Flask extension instances.

Keeping the extension objects here (instead of inside __init__.py) avoids
circular imports between the application factory, future models, services
and routes.
"""

from apscheduler.schedulers.background import BackgroundScheduler
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO()

# Background job scheduler (APScheduler v3).
# Used later for slot reminders, expired-slot handling and notifications.
# Daemon threads do not block process exit.
scheduler = BackgroundScheduler(daemon=True)