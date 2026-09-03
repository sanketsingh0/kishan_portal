"""Payment status tracking model.

Represents payment status and reference information associated 1:1 with a Booking.
NOTE: Status tracking only. No live payment gateway or online transactions.
"""

from datetime import date
from app.extensions import db
from app.models.common import TimestampMixin


class PaymentStatus:
    """Allowed payment statuses."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PAID = "PAID"
    FAILED = "FAILED"

    choices = (PENDING, PROCESSING, PAID, FAILED)


class Payment(TimestampMixin, db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(
        db.Integer,
        db.ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    payment_status = db.Column(
        db.String(20),
        nullable=False,
        default=PaymentStatus.PENDING,
        index=True,
    )
    amount = db.Column(db.Numeric(12, 2), nullable=True)
    payment_reference = db.Column(db.String(100), nullable=True)
    payment_date = db.Column(db.Date, nullable=True)
    remarks = db.Column(db.String(255), nullable=True)

    # Relationships
    booking = db.relationship(
        "Booking",
        backref=db.backref("payment", uselist=False, cascade="all, delete-orphan"),
    )

    def __repr__(self) -> str:
        return f"<Payment id={self.id} booking_id={self.booking_id} status={self.payment_status!r}>"
