"""Procurement Queue Management API routes.

Endpoints:
    GET /api/queue/my/<booking_id>    -> View queue status for farmer's own booking (FARMER only)
    GET /api/queue/centre/<centre_id>  -> View full active queue for a centre (STAFF/ADMIN only)
"""

from datetime import datetime, date
from flask import Blueprint, jsonify, request, g

from app.auth.decorators import login_required, role_required, roles_required
from app.models import UserRole
from app.services.queue_service import get_booking_queue_status, get_centre_queue

queue_bp = Blueprint("queue", __name__, url_prefix="/api/queue")


@queue_bp.route("/my/<int:booking_id>", methods=["GET"])
@login_required
@role_required(UserRole.FARMER)
def get_my_queue_status(booking_id: int):
    """Retrieve queue position, farmers ahead, and estimated wait for authenticated farmer's booking.

    Returns:
        200 OK: Queue status dictionary
        404 Not Found: Booking missing or access denied
    """
    queue_data = get_booking_queue_status(booking_id, user_id=g.current_user.id)
    if not queue_data:
        return jsonify({"error": "Not Found", "message": "Booking not found or access denied."}), 404

    return jsonify(queue_data), 200


@queue_bp.route("/centre/<int:centre_id>", methods=["GET"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
def get_centre_queue_status(centre_id: int):
    """Retrieve ordered active queue for a procurement centre (STAFF or ADMIN only).

    Query Parameters:
        date: Optional YYYY-MM-DD date string (defaults to today)

    Returns:
        200 OK: Centre queue dictionary
        400 Bad Request: Invalid date format
        404 Not Found: Centre not found
    """
    date_str = request.args.get("date")
    target_date = None

    if date_str:
        try:
            target_date = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            return jsonify({
                "error": "Bad Request",
                "message": "Invalid date format. Expected YYYY-MM-DD."
            }), 400

    queue_data = get_centre_queue(centre_id, target_date=target_date)
    if not queue_data:
        return jsonify({"error": "Not Found", "message": "Procurement centre not found."}), 404

    return jsonify(queue_data), 200
