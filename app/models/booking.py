"""Booking model.

Represents a farmer's procurement slot booking.
"""

from datetime import datetime
from sqlalchemy import text

from app.extensions import db
from app.models.common import TimestampMixin, utcnow


class BookingStatus:
    """Allowed booking statuses."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"

    choices = (PENDING, CONFIRMED, CANCELLED, COMPLETED, NO_SHOW)
    active_statuses = (PENDING, CONFIRMED)


class Booking(TimestampMixin, db.Model):
    __tablename__ = "bookings"
    __table_args__ = (
        db.Index("idx_booking_farmer_slot_status", "farmer_id", "slot_id", "status"),
        db.Index(
            "uq_active_booking_farmer_slot",
            "farmer_id",
            "slot_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'CONFIRMED')"),
            sqlite_where=text("status IN ('PENDING', 'CONFIRMED')"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey("farmers.id", ondelete="CASCADE"), nullable=False, index=True)
    slot_id = db.Column(db.Integer, db.ForeignKey("slots.id", ondelete="CASCADE"), nullable=False, index=True)
    booking_date = db.Column(db.DateTime, nullable=False, default=utcnow)
    status = db.Column(db.String(20), nullable=False, default=BookingStatus.CONFIRMED, index=True)

    # Procurement Token fields
    token_number = db.Column(db.String(20), nullable=True, index=True)
    token_generated_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Relationships
    farmer = db.relationship("Farmer", backref=db.backref("bookings", lazy="select", cascade="all, delete-orphan"))
    slot = db.relationship("Slot", backref=db.backref("bookings", lazy="select", cascade="all, delete-orphan"))

    def __repr__(self) -> str:
        return f"<Booking id={self.id} farmer_id={self.farmer_id} slot_id={self.slot_id} status={self.status!r}>"
