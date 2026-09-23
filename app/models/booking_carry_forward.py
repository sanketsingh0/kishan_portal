"""Booking carry-forward / reschedule record.

One row links an original (source-day) booking that was explicitly carried
forward by staff to the new next-day booking created for the same farmer and
centre.  The row is the audit/history spine for the "Staff-Controlled
Next-Day Carry-Forward" feature: the original booking keeps its own token,
date and QR pass, the new booking gets a fresh token and QR pass, and this
table ties the two together.
"""

from app.extensions import db
from app.models.common import TimestampMixin


class CarryForwardReason:
    """Staff-selected reason recorded for every carry-forward."""

    CENTRE_CLOSED = "Centre closed"
    PROCUREMENT_DELAYED = "Procurement delayed"
    INSUFFICIENT_PROCESSING_TIME = "Insufficient processing time"
    OPERATIONAL_ISSUE = "Operational issue"
    OTHER = "Other"

    choices = (
        CENTRE_CLOSED,
        PROCUREMENT_DELAYED,
        INSUFFICIENT_PROCESSING_TIME,
        OPERATIONAL_ISSUE,
        OTHER,
    )


class BookingCarryForward(TimestampMixin, db.Model):
    """Audit record linking an original booking to its next-day replacement."""

    __tablename__ = "booking_carry_forwards"
    __table_args__ = (
        # One original booking may only ever be carried forward once.
        db.UniqueConstraint("original_booking_id", name="uq_carry_forward_original_booking"),
        db.Index("idx_carry_forward_original", "original_booking_id"),
        db.Index("idx_carry_forward_new", "new_booking_id"),
        db.Index("idx_carry_forward_centre", "centre_id"),
        db.Index("idx_carry_forward_original_date", "original_procurement_date"),
        db.Index("idx_carry_forward_new_date", "new_procurement_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    original_booking_id = db.Column(
        db.Integer,
        db.ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    new_booking_id = db.Column(
        db.Integer,
        db.ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    farmer_id = db.Column(
        db.Integer,
        db.ForeignKey("farmers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    centre_id = db.Column(
        db.Integer,
        db.ForeignKey("centres.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_procurement_date = db.Column(db.Date, nullable=False)
    new_procurement_date = db.Column(db.Date, nullable=False)
    reason = db.Column(db.String(100), nullable=False, default=CarryForwardReason.OTHER)
    carried_forward_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships (read-only helpers; cascade stays on Booking side)
    original_booking = db.relationship(
        "Booking", foreign_keys=[original_booking_id]
    )
    new_booking = db.relationship("Booking", foreign_keys=[new_booking_id])
    farmer = db.relationship("Farmer")
    centre = db.relationship("Centre")
    carried_by_user = db.relationship("User", foreign_keys=[carried_forward_by])

    def to_dict(self) -> dict:
        """Serialize the carry-forward record."""
        return {
            "id": self.id,
            "original_booking_id": self.original_booking_id,
            "new_booking_id": self.new_booking_id,
            "farmer_id": self.farmer_id,
            "centre_id": self.centre_id,
            "original_procurement_date": self.original_procurement_date.isoformat()
            if self.original_procurement_date
            else None,
            "new_procurement_date": self.new_procurement_date.isoformat()
            if self.new_procurement_date
            else None,
            "reason": self.reason,
            "carried_forward_by": self.carried_forward_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<BookingCarryForward id={self.id} "
            f"original={self.original_booking_id} new={self.new_booking_id}>"
        )
