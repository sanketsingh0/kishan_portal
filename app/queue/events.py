"""Flask-SocketIO event handlers and notification functions for Realtime Queue Management.

Namespace: /queue
Rooms:
    - farmer_booking_<booking_id>
    - centre_queue_<centre_id>_<date>
"""

from flask import request
from flask_socketio import Namespace, emit, join_room
from app.extensions import db, socketio
from app.models import Booking, UserRole
from app.auth.service import verify_token, get_local_user
from app.services.farmer_service import get_farmer_by_user_id


def emit_queue_update(centre_id: int, slot_date, booking_id: int | None = None, reason: str = "QUEUE_CHANGED"):
    """Emit lightweight queue_updated Socket.IO event after DB commit.

    Args:
        centre_id: Procurement centre ID.
        slot_date: Date object or YYYY-MM-DD string.
        booking_id: Optional relevant booking ID.
        reason: Action triggering update (e.g. BOOKING_CREATED, BOOKING_CANCELLED).
    """
    if hasattr(slot_date, "isoformat"):
        date_str = slot_date.isoformat()
    else:
        date_str = str(slot_date)

    centre_room = f"centre_queue_{centre_id}_{date_str}"
    payload = {
        "centre_id": centre_id,
        "slot_date": date_str,
        "booking_id": booking_id,
        "reason": reason,
    }

    # Broadcast to centre/date room
    socketio.emit("queue_updated", payload, to=centre_room, namespace="/queue")

    # Broadcast to specific farmer booking room if present
    if booking_id:
        farmer_room = f"farmer_booking_{booking_id}"
        socketio.emit("queue_updated", payload, to=farmer_room, namespace="/queue")


def emit_procurement_update(booking_id: int, centre_id: int | None = None, slot_date=None, reason: str = "PROCUREMENT_UPDATED"):
    """Emit lightweight procurement_updated event post DB commit."""
    payload = {
        "booking_id": booking_id,
        "reason": reason,
    }
    if centre_id:
        payload["centre_id"] = centre_id
    if slot_date:
        payload["slot_date"] = slot_date.isoformat() if hasattr(slot_date, "isoformat") else str(slot_date)

    farmer_room = f"farmer_booking_{booking_id}"
    socketio.emit("procurement_updated", payload, to=farmer_room, namespace="/queue")

    if centre_id and slot_date:
        date_str = slot_date.isoformat() if hasattr(slot_date, "isoformat") else str(slot_date)
        centre_room = f"centre_queue_{centre_id}_{date_str}"
        socketio.emit("procurement_updated", payload, to=centre_room, namespace="/queue")


def emit_payment_update(booking_id: int, centre_id: int | None = None, slot_date=None, reason: str = "PAYMENT_UPDATED"):
    """Emit lightweight payment_updated event post DB commit."""
    payload = {
        "booking_id": booking_id,
        "reason": reason,
    }
    if centre_id:
        payload["centre_id"] = centre_id
    if slot_date:
        payload["slot_date"] = slot_date.isoformat() if hasattr(slot_date, "isoformat") else str(slot_date)

    farmer_room = f"farmer_booking_{booking_id}"
    socketio.emit("payment_updated", payload, to=farmer_room, namespace="/queue")

    if centre_id and slot_date:
        date_str = slot_date.isoformat() if hasattr(slot_date, "isoformat") else str(slot_date)
        centre_room = f"centre_queue_{centre_id}_{date_str}"
        socketio.emit("payment_updated", payload, to=centre_room, namespace="/queue")


def emit_delay_update(centre_id: int, slot_date, reason: str = "DELAY_UPDATED"):
    """Emit lightweight delay_updated event post DB commit."""
    if hasattr(slot_date, "isoformat"):
        date_str = slot_date.isoformat()
    else:
        date_str = str(slot_date)

    centre_room = f"centre_queue_{centre_id}_{date_str}"
    payload = {
        "centre_id": centre_id,
        "slot_date": date_str,
        "reason": reason,
    }

    socketio.emit("delay_updated", payload, to=centre_room, namespace="/queue")


def emit_notification_created(user_id: int, notification):
    """Emit lightweight notification_created event post DB commit to specific user's room.

    Args:
        user_id: Local user ID receiving the notification.
        notification: Notification model instance or dict with keys.
    """
    user_room = f"farmer_user_{user_id}"
    notif_id = getattr(notification, "id", None) or notification.get("id")
    notif_type = getattr(notification, "notification_type", None) or notification.get("notification_type")
    title = getattr(notification, "title", None) or notification.get("title")
    message = getattr(notification, "message", None) or notification.get("message")
    created_at = getattr(notification, "created_at", None)
    if created_at and hasattr(created_at, "isoformat"):
        created_at_str = created_at.isoformat()
    else:
        created_at_str = str(created_at) if created_at else None

    payload = {
        "notification_id": notif_id,
        "type": notif_type,
        "title": title,
        "message": message,
        "created_at": created_at_str,
        "is_read": False,
    }

    socketio.emit("notification_created", payload, to=user_room, namespace="/queue")


class QueueNamespace(Namespace):
    """SocketIO Namespace handler for /queue."""

    def on_connect(self, auth=None):
        """Client connection handler."""
        pass

    def on_subscribe_user_notifications(self, data):
        """Subscribe authenticated user to their notification room (farmer_user_<user_id>)."""
        if not isinstance(data, dict):
            return {"error": "Invalid payload format. Expected JSON object."}

        token = data.get("token") or (
            request.headers.get("Authorization", "").replace("Bearer ", "")
            if request.headers.get("Authorization")
            else None
        )

        if not token:
            return {"error": "Authentication required."}

        supabase_user = verify_token(token)
        if not supabase_user:
            return {"error": "Invalid or expired authentication token."}

        user = get_local_user(supabase_user.id)
        if not user or not user.is_active:
            return {"error": "Unauthorized access."}

        user_room = f"farmer_user_{user.id}"
        join_room(user_room)

        return {
            "status": "subscribed",
            "user_id": user.id,
            "room": user_room,
        }

    def on_subscribe_queue(self, data):
        """Subscribe authenticated farmer to their booking queue room."""
        if not isinstance(data, dict):
            return {"error": "Invalid payload format. Expected JSON object."}

        booking_id = data.get("booking_id")
        token = data.get("token") or (
            request.headers.get("Authorization", "").replace("Bearer ", "")
            if request.headers.get("Authorization")
            else None
        )

        if not booking_id:
            return {"error": "booking_id is required."}

        if not token:
            return {"error": "Authentication required."}

        supabase_user = verify_token(token)
        if not supabase_user:
            return {"error": "Invalid or expired authentication token."}

        user = get_local_user(supabase_user.id)
        if not user or not user.is_active or user.role != UserRole.FARMER:
            return {"error": "Unauthorized access. FARMER role required."}

        farmer = get_farmer_by_user_id(user.id)
        if not farmer:
            return {"error": "Farmer profile not found."}

        booking = db.session.get(Booking, booking_id)
        if not booking or booking.farmer_id != farmer.id:
            return {"error": "Booking not found or access denied."}

        farmer_room = f"farmer_booking_{booking.id}"
        join_room(farmer_room)

        # Also join user notification room
        user_room = f"farmer_user_{user.id}"
        join_room(user_room)

        # Also join centre date room so farmer receives centre-wide queue events
        if booking.slot:
            centre_room = f"centre_queue_{booking.slot.centre_id}_{booking.slot.slot_date.isoformat()}"
            join_room(centre_room)

        return {
            "status": "subscribed",
            "booking_id": booking.id,
            "room": farmer_room
        }

    def on_subscribe_centre_queue(self, data):
        """Subscribe staff/admin client to a centre queue room."""
        if not isinstance(data, dict):
            return {"error": "Invalid payload format. Expected JSON object."}

        centre_id = data.get("centre_id")
        date_str = data.get("date")
        token = data.get("token") or (
            request.headers.get("Authorization", "").replace("Bearer ", "")
            if request.headers.get("Authorization")
            else None
        )

        if not centre_id or not date_str:
            return {"error": "centre_id and date are required."}

        if not token:
            return {"error": "Authentication required."}

        supabase_user = verify_token(token)
        if not supabase_user:
            return {"error": "Invalid or expired authentication token."}

        user = get_local_user(supabase_user.id)
        if not user or not user.is_active or user.role not in (UserRole.STAFF, UserRole.ADMIN):
            return {"error": "Unauthorized access. STAFF or ADMIN role required."}

        centre_room = f"centre_queue_{centre_id}_{date_str}"
        join_room(centre_room)

        return {
            "status": "subscribed",
            "centre_id": centre_id,
            "date": date_str,
            "room": centre_room
        }


def init_queue_events(socketio_instance):
    """Register QueueNamespace with SocketIO instance."""
    socketio_instance.on_namespace(QueueNamespace("/queue"))
