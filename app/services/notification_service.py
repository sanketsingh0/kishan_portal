"""Notification service layer for KisanProcure (Task 13).

Encapsulates logic for creating, fetching, reading notifications, and managing
browser push subscriptions.
"""

from datetime import datetime
from app.extensions import db
from app.models import Notification, NotificationType, PushSubscription, User, utcnow
from app.queue.events import emit_notification_created


class NotificationError(Exception):
    """Base exception for notification service errors."""

    def __init__(self, message="Notification operation failed"):
        self.message = message
        super().__init__(self.message)


class NotificationNotFoundError(NotificationError):
    """Raised when notification record is not found."""

    def __init__(self, message="Notification not found"):
        super().__init__(message)


class NotificationValidationError(NotificationError):
    """Raised when validation fails for notification payload."""

    def __init__(self, errors):
        self.errors = errors
        message = "; ".join(errors) if isinstance(errors, list) else str(errors)
        super().__init__(message)


def create_notification(
    user_id: int,
    notification_type: str,
    title: str,
    message: str,
    booking_id: int | None = None,
) -> Notification:
    """Create a new notification for a specific user and emit a Socket.IO event post-commit.

    Args:
        user_id: Local user ID recipient.
        notification_type: Enum string from NotificationType.
        title: Short title summary.
        message: Detailed message content.
        booking_id: Optional linked booking ID.

    Returns:
        Created Notification model instance.
    """
    if not user_id or not isinstance(user_id, int):
        raise NotificationValidationError(["Valid user_id is required."])

    if not title or not isinstance(title, str) or not title.strip():
        raise NotificationValidationError(["Title is required."])

    if not message or not isinstance(message, str) or not message.strip():
        raise NotificationValidationError(["Message is required."])

    if notification_type not in NotificationType.choices:
        notification_type = NotificationType.SYSTEM

    notification = Notification(
        user_id=user_id,
        notification_type=notification_type,
        title=title.strip()[:255],
        message=message.strip(),
        booking_id=booking_id,
        is_read=False,
    )

    try:
        db.session.add(notification)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise NotificationError(f"Database error while creating notification: {exc}")

    # Emit realtime notification event after successful commit
    try:
        emit_notification_created(user_id, notification)
    except Exception:
        # Prevent Socket.IO emission failures from breaking main transaction workflow
        pass

    return notification


def get_user_notifications(
    user_id: int,
    limit: int = 20,
    offset: int = 0,
    unread_only: bool = False,
) -> list[Notification]:
    """Retrieve notifications belonging to a specific user with pagination."""
    query = Notification.query.filter(Notification.user_id == user_id)

    if unread_only:
        query = query.filter(Notification.is_read == False)

    query = query.order_by(Notification.created_at.desc())

    if limit is not None and limit > 0:
        query = query.limit(limit)

    if offset is not None and offset > 0:
        query = query.offset(offset)

    return query.all()


def get_unread_count(user_id: int) -> int:
    """Get total count of unread notifications for a user."""
    return Notification.query.filter(
        Notification.user_id == user_id,
        Notification.is_read == False,
    ).count()


def mark_notification_read(notification_id: int, user_id: int) -> Notification:
    """Mark a single notification as read if it belongs to user_id."""
    notification = db.session.get(Notification, notification_id)
    if not notification or notification.user_id != user_id:
        raise NotificationNotFoundError(f"Notification {notification_id} not found or access denied.")

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = utcnow()
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            raise NotificationError(f"Database error while updating notification: {exc}")

    return notification


def mark_all_notifications_read(user_id: int) -> int:
    """Mark all unread notifications belonging to user_id as read.

    Returns:
        Number of updated notification rows.
    """
    now = utcnow()
    unread_notifs = Notification.query.filter(
        Notification.user_id == user_id,
        Notification.is_read == False,
    ).all()

    count = len(unread_notifs)
    if count > 0:
        for notif in unread_notifs:
            notif.is_read = True
            notif.read_at = now
        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            raise NotificationError(f"Database error while updating notifications: {exc}")

    return count


def save_push_subscription(user_id: int, endpoint: str, p256dh: str, auth: str) -> PushSubscription:
    """Save or update a web browser push subscription for a user."""
    if not endpoint or not isinstance(endpoint, str):
        raise NotificationValidationError(["Valid endpoint URL is required."])
    if not p256dh or not auth:
        raise NotificationValidationError(["p256dh and auth encryption keys are required."])

    subscription = PushSubscription.query.filter_by(endpoint=endpoint).first()
    if subscription:
        subscription.user_id = user_id
        subscription.p256dh = p256dh
        subscription.auth = auth
    else:
        subscription = PushSubscription(
            user_id=user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
        )
        db.session.add(subscription)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise NotificationError(f"Database error saving push subscription: {exc}")

    return subscription


def remove_push_subscription(user_id: int, endpoint: str) -> bool:
    """Remove a browser push subscription for a user."""
    if not endpoint:
        raise NotificationValidationError(["Endpoint URL is required."])

    subscription = PushSubscription.query.filter_by(endpoint=endpoint, user_id=user_id).first()
    if not subscription:
        return False

    try:
        db.session.delete(subscription)
        db.session.commit()
        return True
    except Exception as exc:
        db.session.rollback()
        raise NotificationError(f"Database error removing push subscription: {exc}")
