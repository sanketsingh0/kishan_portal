"""Delay model.

Represents a procurement delay recorded for a centre (and optionally a slot)
on a given date, used by the queue estimation engine to adjust expected waiting times.
"""

from app.extensions import db
from app.models.common import TimestampMixin


class DelayStatus:
    """Allowed delay statuses."""

    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"

    choices = (ACTIVE, RESOLVED, CANCELLED)


class Delay(TimestampMixin, db.Model):
    __tablename__ = "delays"

    id = db.Column(db.Integer, primary_key=True)
    centre_id = db.Column(db.Integer, db.ForeignKey("centres.id", ondelete="CASCADE"), nullable=False, index=True)
    slot_id = db.Column(db.Integer, db.ForeignKey("slots.id", ondelete="CASCADE"), nullable=True, index=True)
    delay_date = db.Column(db.Date, nullable=False, index=True)
    delay_minutes = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(500), nullable=True)
    status = db.Column(db.String(20), nullable=False, default=DelayStatus.ACTIVE, index=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Relationships
    centre = db.relationship("Centre", backref=db.backref("delays", lazy="select", cascade="all, delete-orphan"))
    slot = db.relationship("Slot", backref=db.backref("delays", lazy="select", cascade="all, delete-orphan"))
    creator = db.relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return f"<Delay id={self.id} centre_id={self.centre_id} date={self.delay_date} minutes={self.delay_minutes} status={self.status!r}>"
