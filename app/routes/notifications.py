"""Notification API blueprint (/api/notifications).

Exposes endpoints for listing notifications, fetching unread count, marking read,
and managing browser push subscriptions for authenticated users.
"""

from flask import Blueprint, request, jsonify, g
from app.auth.decorators import login_required
from app.services.notification_service import (
    get_user_notifications,
    get_unread_count,
    mark_notification_read,
    mark_all_notifications_read,
    save_push_subscription,
    remove_push_subscription,
    NotificationError,
    NotificationNotFoundError,
    NotificationValidationError,
)

notifications_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


# 1. Get user notifications
@notifications_bp.route("", methods=["GET"])
@login_required
def get_my_notifications():
    limit = request.args.get("limit", default=20, type=int)
    offset = request.args.get("offset", default=0, type=int)
    unread_only = request.args.get("unread_only", default="false").lower() in ("true", "1", "yes")

    notifications = get_user_notifications(
        user_id=g.current_user.id,
        limit=limit,
        offset=offset,
        unread_only=unread_only,
    )
    unread_cnt = get_unread_count(g.current_user.id)

    return jsonify({
        "notifications": [n.to_dict() for n in notifications],
        "unread_count": unread_cnt,
        "limit": limit,
        "offset": offset,
    }), 200


# 2. Get unread count
@notifications_bp.route("/unread-count", methods=["GET"])
@login_required
def get_my_unread_count():
    unread_cnt = get_unread_count(g.current_user.id)
    return jsonify({"unread_count": unread_cnt}), 200


# 3. Mark single notification as read
@notifications_bp.route("/<int:notification_id>/read", methods=["PUT"])
@login_required
def mark_single_read(notification_id: int):
    try:
        notification = mark_notification_read(notification_id, g.current_user.id)
        return jsonify({
            "message": "Notification marked as read",
            "notification": notification.to_dict(),
        }), 200
    except NotificationNotFoundError as nnfe:
        return jsonify({"error": "Not Found", "message": str(nnfe)}), 404
    except NotificationError as ne:
        return jsonify({"error": "Bad Request", "message": str(ne)}), 400


# 4. Mark all notifications as read
@notifications_bp.route("/read-all", methods=["PUT"])
@login_required
def mark_all_read():
    try:
        updated_count = mark_all_notifications_read(g.current_user.id)
        return jsonify({
            "message": "All notifications marked as read",
            "updated_count": updated_count,
        }), 200
    except NotificationError as ne:
        return jsonify({"error": "Bad Request", "message": str(ne)}), 400


# 5. Save browser push subscription
@notifications_bp.route("/push/subscribe", methods=["POST"])
@login_required
def subscribe_push():
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint")
    keys = data.get("keys", {})
    p256dh = data.get("p256dh") or keys.get("p256dh")
    auth = data.get("auth") or keys.get("auth")

    try:
        subscription = save_push_subscription(
            user_id=g.current_user.id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
        )
        return jsonify({
            "message": "Push subscription saved successfully",
            "subscription": subscription.to_dict(),
        }), 201
    except NotificationValidationError as nve:
        return jsonify({
            "error": "Validation Error",
            "message": str(nve),
            "messages": nve.errors if isinstance(nve.errors, list) else [str(nve)],
        }), 400
    except NotificationError as ne:
        return jsonify({"error": "Bad Request", "message": str(ne)}), 400


# 6. Remove browser push subscription
@notifications_bp.route("/push/subscribe", methods=["DELETE"])
@login_required
def unsubscribe_push():
    data = request.get_json(silent=True) or {}
    endpoint = data.get("endpoint") or request.args.get("endpoint")

    try:
        removed = remove_push_subscription(user_id=g.current_user.id, endpoint=endpoint)
        if not removed:
            return jsonify({"error": "Not Found", "message": "Subscription endpoint not found."}), 404
        return jsonify({"message": "Push subscription removed successfully"}), 200
    except NotificationValidationError as nve:
        return jsonify({"error": "Validation Error", "message": str(nve)}), 400
    except NotificationError as ne:
        return jsonify({"error": "Bad Request", "message": str(ne)}), 400
