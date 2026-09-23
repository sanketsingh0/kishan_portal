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
    smart_queue_passes - secure digital mandi entry passes (SIH 26032)
"""

from app.models.common import TimestampMixin, UserRole, utcnow
from app.models.user import User
from app.models.farmer import Farmer
from app.models.staff import Staff
from app.models.centre import Centre
from app.models.crop import Crop
from app.models.slot import Slot, SlotStatus
from app.models.booking import Booking, BookingStatus
from app.models.booking_carry_forward import BookingCarryForward, CarryForwardReason
from app.models.smart_queue_pass import SmartQueuePass, SmartQueuePassStatus
from app.models.procurement import Procurement, ProcurementStatus
from app.models.payment import Payment, PaymentStatus
from app.models.delay import Delay, DelayStatus
from app.models.notification import Notification, NotificationType, PushSubscription
from app.models.audit_log import AuditLog

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
    "BookingCarryForward",
    "CarryForwardReason",
    "SmartQueuePass",
    "SmartQueuePassStatus",
    "Procurement",
    "ProcurementStatus",
    "Payment",
    "PaymentStatus",
    "Delay",
    "DelayStatus",
    "Notification",
    "NotificationType",
    "PushSubscription",
    "AuditLog",
]