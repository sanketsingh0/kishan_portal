"""
Procurement Centre model.

`average_processing_minutes` will later feed the queue waiting-time estimate
(estimated wait = farmers ahead x average processing time). No queue logic
is implemented yet.
"""

from app.extensions import db
from app.models.common import TimestampMixin


class Centre(TimestampMixin, db.Model):
    __tablename__ = "centres"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False, unique=True)
    location = db.Column(db.String(255), nullable=False)
    opening_time = db.Column(db.Time, nullable=True)
    closing_time = db.Column(db.Time, nullable=True)
    daily_capacity = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    average_processing_minutes = db.Column(db.Integer, nullable=False, default=15)

    staff = db.relationship("Staff", back_populates="centre")

    def __repr__(self) -> str:
        return f"<Centre id={self.id} name={self.name!r}>"