"""Procurement Slot Booking API routes.

Endpoints:
    POST   /api/bookings               -> book an available slot (FARMER only)
    GET    /api/bookings/my            -> view my bookings (FARMER only)
    GET    /api/bookings/<id>          -> view specific booking details (FARMER only)
    PUT    /api/bookings/<id>/cancel   -> cancel a booking (FARMER only)
    POST   /api/bookings/<id>/cancel   -> cancel a booking (alias)
"""

from flask import Blueprint, jsonify, request, g

from app.auth.decorators import login_required, role_required
from app.models import UserRole
from app.services.slot_service import format_date_string, format_time_string
from app.services.booking_service import (
    create_booking,
    get_farmer_bookings,
    get_booking_by_id,
    cancel_booking,
    BookingValidationError,
    BookingConflictError,
    BookingNotFoundError,
    BookingError,
)

bookings_bp = Blueprint("bookings", __name__, url_prefix="/api/bookings")


def _format_booking(b):
    """Serialize Booking instance to clean JSON dictionary."""
    return {
        "id": b.id,
        "farmer_id": b.farmer_id,
        "slot_id": b.slot_id,
        "status": b.status,
        "token_number": b.token_number,
        "token_generated_at": b.token_generated_at.isoformat() if b.token_generated_at else None,
        "booking_date": b.booking_date.isoformat() if b.booking_date else None,
        "slot": {
            "id": b.slot.id,
            "slot_date": format_date_string(b.slot.slot_date),
            "start_time": format_time_string(b.slot.start_time),
            "end_time": format_time_string(b.slot.end_time),
            "centre": b.slot.centre.name if b.slot and b.slot.centre else None,
            "crop": b.slot.crop.name if b.slot and b.slot.crop else None,
        } if b.slot else None,
    }


@bookings_bp.route("", methods=["POST"])
@login_required
@role_required(UserRole.FARMER)
def add_booking():
    """Book an available procurement slot (FARMER only).

    Request JSON:
        { "slot_id": int }

    Returns:
        201 Created: { message, booking }
        400 Bad Request: missing slot_id or invalid slot state
        409 Conflict: slot full, duplicate booking, or time conflict
    """
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid request", "message": "JSON body required."}), 400

    slot_id = data.get("slot_id")

    try:
        booking = create_booking(user_id=g.current_user.id, slot_id=slot_id)
    except BookingConflictError as exc:
        return jsonify({"error": "Conflict", "message": exc.message, "code": exc.code}), 409
    except BookingValidationError as exc:
        return jsonify({"error": "Validation failed", "messages": exc.errors}), 400
    except BookingError as exc:
        return jsonify({"error": "Server error", "message": exc.message}), 500

    return jsonify({
        "message": "Booking created successfully",
        "booking": _format_booking(booking),
    }), 201


@bookings_bp.route("/my", methods=["GET"])
@login_required
@role_required(UserRole.FARMER)
def list_my_bookings():
    """List bookings for the authenticated farmer.

    Query parameters:
        status: PENDING, CONFIRMED, CANCELLED, etc.

    Returns:
        200 OK: { bookings: [...] }
    """
    status = request.args.get("status")
    bookings = get_farmer_bookings(user_id=g.current_user.id, status=status)
    return jsonify({"bookings": [_format_booking(b) for b in bookings]}), 200


@bookings_bp.route("/<int:booking_id>", methods=["GET"])
@login_required
@role_required(UserRole.FARMER)
def get_booking(booking_id: int):
    """View details of a specific booking owned by the authenticated farmer.

    Returns:
        200 OK: { booking: { ... } }
        404 Not Found: missing or inaccessible booking
    """
    booking = get_booking_by_id(booking_id, user_id=g.current_user.id)
    if not booking:
        return jsonify({"error": "Not Found", "message": "Booking not found or access denied."}), 404

    return jsonify({"booking": _format_booking(booking)}), 200


@bookings_bp.route("/<int:booking_id>/token", methods=["GET"])
@login_required
@role_required(UserRole.FARMER)
def get_booking_token(booking_id: int):
    """Retrieve procurement token details for a booking owned by the authenticated farmer.

    Returns:
        200 OK: { booking_id, token_number, token_generated_at, status }
        404 Not Found: missing or inaccessible booking
    """
    booking = get_booking_by_id(booking_id, user_id=g.current_user.id)
    if not booking:
        return jsonify({"error": "Not Found", "message": "Booking not found or access denied."}), 404

    return jsonify({
        "booking_id": booking.id,
        "token_number": booking.token_number,
        "token_generated_at": booking.token_generated_at.isoformat() if booking.token_generated_at else None,
        "status": booking.status,
    }), 200


@bookings_bp.route("/<int:booking_id>/cancel", methods=["PUT", "POST"])
@login_required
@role_required(UserRole.FARMER)
def cancel_my_booking(booking_id: int):
    """Cancel an active booking owned by the authenticated farmer.

    Returns:
        200 OK: { message, booking }
        400 Bad Request: already cancelled or completed
        404 Not Found: missing or inaccessible booking
    """
    try:
        cancelled = cancel_booking(booking_id, user_id=g.current_user.id)
    except BookingNotFoundError as exc:
        return jsonify({"error": "Not Found", "message": exc.message}), 404
    except BookingValidationError as exc:
        return jsonify({"error": "Validation failed", "messages": exc.errors}), 400
    except BookingError as exc:
        return jsonify({"error": "Server error", "message": exc.message}), 500

    return jsonify({
        "message": "Booking cancelled successfully",
        "booking": _format_booking(cancelled),
    }), 200
