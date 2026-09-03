"""Procurement tracking model.

Represents procurement details and status associated 1:1 with a Booking.
"""

from datetime import date
from app.extensions import db
from app.models.common import TimestampMixin


class ProcurementStatus:
    """Allowed procurement statuses."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"

    choices = (PENDING, IN_PROGRESS, COMPLETED, REJECTED)


class Procurement(TimestampMixin, db.Model):
    __tablename__ = "procurements"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(
        db.Integer,
        db.ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    procurement_status = db.Column(
        db.String(20),
        nullable=False,
        default=ProcurementStatus.PENDING,
        index=True,
    )
    quantity = db.Column(db.Float, nullable=True)
    unit = db.Column(db.String(20), nullable=True, default="quintal")
    procurement_date = db.Column(db.Date, nullable=True)
    remarks = db.Column(db.String(255), nullable=True)

    # Relationships
    booking = db.relationship(
        "Booking",
        backref=db.backref("procurement", uselist=False, cascade="all, delete-orphan"),
    )

    def __repr__(self) -> str:
        return f"<Procurement id={self.id} booking_id={self.booking_id} status={self.procurement_status!r}>"
