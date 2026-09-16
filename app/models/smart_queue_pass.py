"""Smart Queue Pass model (SIH 26032 - secure digital mandi entry pass).

The pass is the 1:1 companion of a Booking. It stores only a cryptographically
secure, non-sequential ``secure_pass_id`` that is safe to expose as a QR payload:
it embeds no farmer, booking, phone, bank or authentication information.

Lifecycle: ACTIVE -> VERIFIED (staff entry verification) or ACTIVE -> CANCELLED
(booking cancelled).

Stage 1 is the backend foundation only - QR image generation, PDF export and the
scanner UI belong to Stage 2.
"""

from app.extensions import db
from app.models.common import TimestampMixin


class SmartQueuePassStatus:
    """Allowed Smart Queue Pass statuses."""

    ACTIVE = "ACTIVE"
    VERIFIED = "VERIFIED"
    CANCELLED = "CANCELLED"

    choices = (ACTIVE, VERIFIED, CANCELLED)


class SmartQueuePass(TimestampMixin, db.Model):
    """Secure digital entry pass, one per booking."""

    __tablename__ = "smart_queue_passes"
    __table_args__ = (
        # One pass per booking.
        db.UniqueConstraint("booking_id", name="uq_smart_queue_pass_booking_id"),
        # The QR-safe identifier must be globally unique.
        db.UniqueConstraint("secure_pass_id", name="uq_smart_queue_pass_secure_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(
        db.Integer,
        db.ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    secure_pass_id = db.Column(db.String(80), nullable=False)
    status = db.Column(
        db.String(20),
        nullable=False,
        default=SmartQueuePassStatus.ACTIVE,
        index=True,
    )

    # Entry verification (filled in by STAFF/ADMIN at the mandi gate)
    verified_at = db.Column(db.DateTime(timezone=True), nullable=True)
    verified_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    verification_centre_id = db.Column(
        db.Integer,
        db.ForeignKey("centres.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    booking = db.relationship(
        "Booking",
        backref=db.backref("smart_queue_pass", uselist=False, cascade="all, delete-orphan"),
    )
    verified_by_user = db.relationship("User", foreign_keys=[verified_by])
    verification_centre = db.relationship("Centre", foreign_keys=[verification_centre_id])

    def to_dict(self) -> dict:
        """Serialize the pass.

        The pass intentionally holds no personal or sensitive data, so nothing
        needs to be redacted here. Phone numbers, bank details, IFSC and tokens
        are never stored on (or derived from) a Smart Queue Pass.
        """
        return {
            "id": self.id,
            "booking_id": self.booking_id,
            "pass_id": self.secure_pass_id,
            "status": self.status,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "verified_by": self.verified_by,
            "verification_centre_id": self.verification_centre_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<SmartQueuePass id={self.id} booking_id={self.booking_id} "
            f"status={self.status!r}>"
        )
