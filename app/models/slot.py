"""Procurement Slot model.

Represents a time window at a procurement centre for a specific crop, date,
and maximum farmer capacity.

Used as the resource foundation for slot booking in Task 7.
"""

from app.extensions import db
from app.models.common import TimestampMixin


class SlotStatus:
    """Allowed slot statuses."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"

    choices = (OPEN, CLOSED, CANCELLED)


class Slot(TimestampMixin, db.Model):
    __tablename__ = "slots"
    __table_args__ = (
        db.UniqueConstraint(
            "centre_id", "crop_id", "slot_date", "start_time", "end_time",
            name="uq_slot_centre_crop_date_time"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    centre_id = db.Column(db.Integer, db.ForeignKey("centres.id", ondelete="CASCADE"), nullable=False)
    crop_id = db.Column(db.Integer, db.ForeignKey("crops.id", ondelete="CASCADE"), nullable=False)
    slot_date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=SlotStatus.OPEN)

    # Relationships
    centre = db.relationship("Centre", backref=db.backref("slots", lazy="select", cascade="all, delete-orphan"))
    crop = db.relationship("Crop", backref=db.backref("slots", lazy="select", cascade="all, delete-orphan"))

    def __repr__(self) -> str:
        return f"<Slot id={self.id} centre_id={self.centre_id} crop_id={self.crop_id} date={self.slot_date} time={self.start_time}-{self.end_time} status={self.status!r}>"
