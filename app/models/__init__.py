"""Database models package.

Phase 1 models only (no slots/bookings/queue/notifications yet):

    users    - accounts (role: FARMER/STAFF/ADMIN), mirrors Supabase Auth
    farmers  - farmer profiles, one-to-one with users
    staff    - centre staff profiles, one-to-one with users
    centres  - procurement centres
    crops    - procurable crop catalogue

Importing this package registers all models on `db.metadata`, which is what
Flask-Migrate (autogenerate), `db.create_all()` and Alembic use.
"""

from app.models.common import TimestampMixin, UserRole, utcnow
from app.models.user import User
from app.models.farmer import Farmer
from app.models.staff import Staff
from app.models.centre import Centre
from app.models.crop import Crop
from app.models.slot import Slot, SlotStatus
from app.models.booking import Booking, BookingStatus

__all__ = [
    "TimestampMixin",
    "UserRole",
    "User",
    "Farmer",
    "Staff",
    "Centre",
    "Crop",
    "Slot",
    "SlotStatus",
    "Booking",
    "BookingStatus",
]