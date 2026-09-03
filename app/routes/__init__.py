"""API route blueprints package.

    /api/auth          -> authentication (Supabase)
    /api/farmers       -> farmer module
    /api/crops         -> crop catalogue
    /api/centres       -> procurement centres
    /api/slots         -> slot management
    /api/bookings      -> booking + token generation
    /api/queue         -> queue + realtime updates
    /api/procurement   -> procurement workflow
    /api/payments      -> payment status tracking
    /api/notifications -> notification engine
    /api/push          -> push subscriptions
    /api/admin         -> administration + analytics
"""

from app.routes.health import health_bp
from app.routes.main import main_bp
from app.routes.auth import auth_bp
from app.routes.farmers import farmers_bp
from app.routes.centres import centres_bp
from app.routes.crops import crops_bp
from app.routes.slots import slots_bp

__all__ = ["health_bp", "main_bp", "auth_bp", "farmers_bp", "centres_bp", "crops_bp", "slots_bp"]