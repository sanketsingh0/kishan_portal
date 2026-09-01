"""
Staff model - centre staff account.

A member of staff belongs to a User and (optionally) to a Procurement Centre
(centre assignment is a later milestone - the FK is nullable for that reason).
"""

from app.extensions import db
from app.models.common import TimestampMixin


class Staff(TimestampMixin, db.Model):
    __tablename__ = "staff"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # one staff profile per user
    )
    centre_id = db.Column(
        db.Integer,
        db.ForeignKey("centres.id", ondelete="SET NULL"),
        nullable=True,
    )
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=True)

    user = db.relationship("User", back_populates="staff")
    centre = db.relationship("Centre", back_populates="staff")

    def __repr__(self) -> str:
        return f"<Staff id={self.id} name={self.name!r}>"