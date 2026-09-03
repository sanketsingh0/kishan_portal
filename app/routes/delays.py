"""Delay management API blueprint (/api/delays).

Exposes RESTful endpoints for recording, viewing, updating, cancelling, and inspecting
procurement delays and their impact on queue waiting times.
"""

from flask import Blueprint, request, jsonify, g
from app.extensions import db
from app.models import UserRole, Booking, Delay
from app.auth.decorators import login_required, role_required, roles_required
from app.services.farmer_service import get_farmer_by_user_id
from app.services.queue_service import get_booking_queue_status
from app.services.delay_service import (
    create_delay,
    update_delay,
    cancel_delay,
    get_delay_by_id,
    get_delays,
    get_active_delays_for_scope,
    DelayError,
    DelayNotFoundError,
    DelayValidationError,
)

delays_bp = Blueprint("delays", __name__, url_prefix="/api/delays")


def _format_delay_response(delay: Delay) -> dict:
    """Format Delay model instance for JSON API response."""
    return {
        "id": delay.id,
        "centre_id": delay.centre_id,
        "centre_name": delay.centre.name if delay.centre else None,
        "slot_id": delay.slot_id,
        "delay_date": delay.delay_date.isoformat() if delay.delay_date else None,
        "delay_minutes": delay.delay_minutes,
        "reason": delay.reason,
        "status": delay.status,
        "created_by": delay.created_by,
        "created_at": delay.created_at.isoformat() if delay.created_at else None,
        "updated_at": delay.updated_at.isoformat() if delay.updated_at else None,
    }


# 1. Staff/Admin create delay
@delays_bp.route("", methods=["POST"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
def staff_create_delay():
    data = request.get_json(silent=True) or {}
    try:
        delay = create_delay(data, g.current_user.id)
        return jsonify({
            "message": "Delay recorded successfully",
            "delay": _format_delay_response(delay)
        }), 201
    except DelayValidationError as dve:
        return jsonify({
            "error": "Validation Error",
            "message": str(dve),
            "messages": dve.errors if isinstance(dve.errors, list) else [str(dve)]
        }), 400
    except DelayError as de:
        return jsonify({"error": "Bad Request", "message": str(de)}), 400


# 2. Staff/Admin list delays with optional query filters
@delays_bp.route("", methods=["GET"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
def staff_get_delays():
    centre_id = request.args.get("centre_id", type=int)
    slot_id = request.args.get("slot_id", type=int)
    date_val = request.args.get("date")
    status = request.args.get("status")

    try:
        delays = get_delays(centre_id=centre_id, slot_id=slot_id, delay_date=date_val, status=status)
        return jsonify({
            "delays": [_format_delay_response(d) for d in delays]
        }), 200
    except DelayValidationError as dve:
        return jsonify({"error": "Bad Request", "message": str(dve)}), 400


# 3. Farmer read delay info for own booking
@delays_bp.route("/my/<int:booking_id>", methods=["GET"])
@login_required
@role_required(UserRole.FARMER)
def farmer_get_booking_delays(booking_id: int):
    farmer = get_farmer_by_user_id(g.current_user.id)
    if not farmer:
        return jsonify({"error": "Not Found", "message": "Farmer profile not found."}), 404

    booking = db.session.get(Booking, booking_id)
    if not booking or booking.farmer_id != farmer.id:
        return jsonify({"error": "Not Found", "message": "Booking not found or access denied."}), 404

    queue_status = get_booking_queue_status(booking.id, user_id=g.current_user.id)
    if not queue_status:
        return jsonify({"error": "Not Found", "message": "Queue status unavailable."}), 404

    slot = booking.slot
    active_delays = get_active_delays_for_scope(slot.centre_id, slot.slot_date, slot.id) if slot else []

    return jsonify({
        "booking_id": booking.id,
        "token_number": booking.token_number,
        "centre_id": slot.centre_id if slot else None,
        "centre_name": slot.centre.name if slot and slot.centre else None,
        "slot_date": slot.slot_date.isoformat() if slot else None,
        "base_estimated_wait": queue_status.get("base_estimated_wait", 0),
        "active_delay_minutes": queue_status.get("active_delay_minutes", 0),
        "adjusted_estimated_wait": queue_status.get("adjusted_estimated_wait", 0),
        "active_delays": [_format_delay_response(d) for d in active_delays],
    }), 200


# 4. Staff/Admin inspect single delay
@delays_bp.route("/<int:delay_id>", methods=["GET"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
def staff_get_delay(delay_id: int):
    delay = get_delay_by_id(delay_id)
    if not delay:
        return jsonify({"error": "Not Found", "message": f"Delay {delay_id} not found."}), 404

    return jsonify({"delay": _format_delay_response(delay)}), 200


# 5. Staff/Admin update delay
@delays_bp.route("/<int:delay_id>", methods=["PUT"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
def staff_update_delay(delay_id: int):
    data = request.get_json(silent=True) or {}
    try:
        delay = update_delay(delay_id, data)
        return jsonify({
            "message": "Delay updated successfully",
            "delay": _format_delay_response(delay)
        }), 200
    except DelayNotFoundError as dnfe:
        return jsonify({"error": "Not Found", "message": str(dnfe)}), 404
    except DelayValidationError as dve:
        return jsonify({
            "error": "Validation Error",
            "message": str(dve),
            "messages": dve.errors if isinstance(dve.errors, list) else [str(dve)]
        }), 400
    except DelayError as de:
        return jsonify({"error": "Bad Request", "message": str(de)}), 400


# 6. Staff/Admin soft-cancel delay
@delays_bp.route("/<int:delay_id>", methods=["DELETE"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
def staff_cancel_delay(delay_id: int):
    try:
        delay = cancel_delay(delay_id)
        return jsonify({
            "message": "Delay cancelled successfully",
            "delay": _format_delay_response(delay)
        }), 200
    except DelayNotFoundError as dnfe:
        return jsonify({"error": "Not Found", "message": str(dnfe)}), 404
    except DelayError as de:
        return jsonify({"error": "Bad Request", "message": str(de)}), 400
