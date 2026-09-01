"""
Crop model - the catalogue of crops that can be procured.

Only the fields needed for slot/booking flows are included.
"""

from app.extensions import db
from app.models.common import TimestampMixin


class Crop(TimestampMixin, db.Model):
    __tablename__ = "crops"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    category = db.Column(db.String(80), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<Crop id={self.id} name={self.name!r}>"