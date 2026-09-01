"""
Farmer model - minimal profile data for a registered farmer.

Only basic prototype information is collected. No sensitive/unnecessary fields.
"""

from app.extensions import db
from app.models.common import TimestampMixin


class Farmer(TimestampMixin, db.Model):
    __tablename__ = "farmers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # one farmer profile per user
    )
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=True, unique=True)
    address = db.Column(db.Text, nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    pincode = db.Column(db.String(10), nullable=True)

    user = db.relationship("User", back_populates="farmer")

    def __repr__(self) -> str:
        return f"<Farmer id={self.id} name={self.name!r}>"