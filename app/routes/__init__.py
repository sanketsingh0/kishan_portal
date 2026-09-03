"""API route blueprints package.

    /api/auth          -> authentication (Supabase)
    /api/farmers       -> farmer module
    /api/crops         -> crop catalogue
    /api/centres       -> procurement centres
    /api/slots         -> slot management
    /api/bookings      -> booking + token generation
    /api/queue         -> queue + realtime updates
    /api/procurement   -> procurement status workflow
    /api/payment       -> payment status tracking
"""

from app.routes.health import health_bp
from app.routes.main import main_bp
from app.routes.auth import auth_bp
from app.routes.farmers import farmers_bp
from app.routes.centres import centres_bp
from app.routes.crops import crops_bp
from app.routes.slots import slots_bp
from app.routes.bookings import bookings_bp
from app.routes.queue import queue_bp
from app.routes.procurement import procurement_bp
from app.routes.payment import payment_bp
from app.routes.delays import delays_bp
from app.routes.notifications import notifications_bp
from app.routes.admin import admin_bp

__all__ = [
    "health_bp",
    "main_bp",
    "auth_bp",
    "farmers_bp",
    "centres_bp",
    "crops_bp",
    "slots_bp",
    "bookings_bp",
    "queue_bp",
    "procurement_bp",
    "payment_bp",
    "delays_bp",
    "notifications_bp",
    "admin_bp",
]