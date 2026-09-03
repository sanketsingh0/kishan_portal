"""Notification & PushSubscription models for KisanProcure (Task 13).

Tracks in-app notifications and web browser push subscriptions for farmers and users.
"""

from app.extensions import db
from app.models.common import TimestampMixin, utcnow


class NotificationType:
    """Notification categories."""

    BOOKING_CONFIRMED = "BOOKING_CONFIRMED"
    BOOKING_CANCELLED = "BOOKING_CANCELLED"
    QUEUE_UPDATE = "QUEUE_UPDATE"
    DELAY_UPDATE = "DELAY_UPDATE"
    PROCUREMENT_UPDATE = "PROCUREMENT_UPDATE"
    PAYMENT_UPDATE = "PAYMENT_UPDATE"
    SLOT_UPDATE = "SLOT_UPDATE"
    SYSTEM = "SYSTEM"

    choices = (
        BOOKING_CONFIRMED,
        BOOKING_CANCELLED,
        QUEUE_UPDATE,
        DELAY_UPDATE,
        PROCUREMENT_UPDATE,
        PAYMENT_UPDATE,
        SLOT_UPDATE,
        SYSTEM,
    )


class Notification(TimestampMixin, db.Model):
    """In-app notification model for user updates."""

    __tablename__ = "notifications"
    __table_args__ = (
        db.Index("idx_notif_user_created", "user_id", "created_at"),
        db.Index("idx_notif_user_read", "user_id", "is_read"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notification_type = db.Column(db.String(50), nullable=False, default=NotificationType.SYSTEM, index=True)
    title = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    booking_id = db.Column(
        db.Integer,
        db.ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    read_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Relationships
    user = db.relationship("User", backref=db.backref("notifications", lazy="select", cascade="all, delete-orphan"))
    booking = db.relationship("Booking", backref=db.backref("notifications", lazy="select"))

    def to_dict(self) -> dict:
        """Serialize notification object to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "notification_type": self.notification_type,
            "title": self.title,
            "message": self.message,
            "booking_id": self.booking_id,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
        }

    def __repr__(self) -> str:
        return f"<Notification id={self.id} user_id={self.user_id} type={self.notification_type!r} is_read={self.is_read}>"


class PushSubscription(TimestampMixin, db.Model):
    """Browser Push Subscription details per user."""

    __tablename__ = "push_subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    endpoint = db.Column(db.Text, nullable=False, unique=True, index=True)
    p256dh = db.Column(db.Text, nullable=False)
    auth = db.Column(db.Text, nullable=False)

    user = db.relationship("User", backref=db.backref("push_subscriptions", lazy="select", cascade="all, delete-orphan"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "endpoint": self.endpoint,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<PushSubscription id={self.id} user_id={self.user_id}>"
