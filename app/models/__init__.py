"""Database models package.

Models:
    users        - accounts (role: FARMER/STAFF/ADMIN), mirrors Supabase Auth
    farmers      - farmer profiles, one-to-one with users
    staff        - centre staff profiles, one-to-one with users
    centres      - procurement centres
    crops        - procurable crop catalogue
    slots        - procurement slots
    bookings     - farmer slot bookings and procurement tokens
    procurements - procurement status and quantity tracking
    payments     - payment status and reference tracking
"""

from app.models.common import TimestampMixin, UserRole, utcnow
from app.models.user import User
from app.models.farmer import Farmer
from app.models.staff import Staff
from app.models.centre import Centre
from app.models.crop import Crop
from app.models.slot import Slot, SlotStatus
from app.models.booking import Booking, BookingStatus
from app.models.procurement import Procurement, ProcurementStatus
from app.models.payment import Payment, PaymentStatus

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
    "Procurement",
    "ProcurementStatus",
    "Payment",
    "PaymentStatus",
]