"""Procurement Slot API routes.

Endpoints:
    GET    /api/slots       -> list available/filtered slots
    GET    /api/slots/<id>  -> view slot details
    POST   /api/slots       -> create slot (STAFF / ADMIN only)
    PUT    /api/slots/<id>  -> update slot (STAFF / ADMIN only)
    DELETE /api/slots/<id>  -> soft cancel slot (STAFF / ADMIN only)
"""

from flask import Blueprint, jsonify, request, g

from app.auth.decorators import login_required, role_required, roles_required, staff_centre_required
from app.models import UserRole, BookingStatus
from app.services.slot_service import (
    get_slots,
    get_slot_by_id,
    create_slot,
    update_slot,
    cancel_slot,
    format_date_string,
    format_time_string,
    DuplicateSlotError,
    SlotOverlapError,
    DailyCapacityExceededError,
    SlotValidationError,
    SlotError,
)

slots_bp = Blueprint("slots", __name__, url_prefix="/api/slots")


def _format_slot(s):
    """Serialize Slot instance to clean JSON dictionary."""
    active_booked = sum(1 for b in s.bookings if b.status in (BookingStatus.PENDING, BookingStatus.CONFIRMED))
    return {
        "id": s.id,
        "centre_id": s.centre_id,
        "centre_name": s.centre.name if s.centre else None,
        "crop_id": s.crop_id,
        "crop_name": s.crop.name if s.crop else None,
        "slot_date": format_date_string(s.slot_date),
        "start_time": format_time_string(s.start_time),
        "end_time": format_time_string(s.end_time),
        "capacity": s.capacity,
        "booked_count": active_booked,
        "remaining_capacity": max(0, s.capacity - active_booked),
        "status": s.status,
    }


@slots_bp.route("", methods=["GET"])
@login_required
def list_slots():
    """List procurement slots with filtering.

    Query parameters:
        centre_id: int
        crop_id: int
        date / slot_date: YYYY-MM-DD
        status: OPEN, CLOSED, CANCELLED

    Returns:
        200 OK: { slots: [...] }
    """
    user_role = g.current_user.role if getattr(g, "current_user", None) else None
    is_staff_or_admin = user_role in (UserRole.STAFF, UserRole.ADMIN)

    centre_id = request.args.get("centre_id", type=int)
    crop_id = request.args.get("crop_id", type=int)
    slot_date = request.args.get("date") or request.args.get("slot_date")
    status = request.args.get("status")

    # Farmers only see upcoming OPEN slots
    upcoming_only = not is_staff_or_admin

    slots = get_slots(
        centre_id=centre_id,
        crop_id=crop_id,
        slot_date=slot_date,
        status=status,
        upcoming_only=upcoming_only,
    )

    return jsonify({"slots": [_format_slot(s) for s in slots]}), 200


@slots_bp.route("/<int:slot_id>", methods=["GET"])
@login_required
def get_slot(slot_id: int):
    """View details of a specific procurement slot.

    Returns:
        200 OK: { slot: { ... } }
        404 Not Found: if slot missing or not accessible to farmers
    """
    user_role = g.current_user.role if getattr(g, "current_user", None) else None
    is_staff_or_admin = user_role in (UserRole.STAFF, UserRole.ADMIN)

    slot = get_slot_by_id(slot_id, is_admin_or_staff=is_staff_or_admin)
    if not slot:
        return jsonify({"error": "Not Found", "message": "Slot not found or unavailable."}), 404

    return jsonify({"slot": _format_slot(slot)}), 200


@slots_bp.route("", methods=["POST"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
@staff_centre_required
def add_slot():
    """Create a new procurement slot (STAFF or ADMIN only).

    Request JSON:
        { centre_id, crop_id, slot_date, start_time, end_time, capacity, status }

    STAFF may only create slots for their assigned centre.

    Returns:
        201 Created: { message, slot }
        400 Bad Request: validation error
        403 Forbidden: staff accessing another centre
        409 Conflict: duplicate slot, overlap, or daily capacity exceeded
    """
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid request", "message": "JSON body required."}), 400

    # Centre isolation: STAFF may only create slots for their own centre
    if g.current_user.role == UserRole.STAFF:
        target_centre_id = data.get("centre_id")
        if target_centre_id != g.current_staff.centre_id:
            return jsonify({
                "error": "Forbidden",
                "message": "Access denied for this centre.",
            }), 403

    try:
        slot = create_slot(data)
    except (DuplicateSlotError, SlotOverlapError, DailyCapacityExceededError) as exc:
        return jsonify({"error": "Conflict", "message": exc.message, "code": exc.code}), 409
    except SlotValidationError as exc:
        return jsonify({"error": "Validation failed", "messages": exc.errors}), 400
    except SlotError as exc:
        return jsonify({"error": "Server error", "message": exc.message}), 500

    return jsonify({
        "message": "Slot created successfully",
        "slot": _format_slot(slot),
    }), 201


@slots_bp.route("/<int:slot_id>", methods=["PUT"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
@staff_centre_required
def edit_slot(slot_id: int):
    """Update an existing procurement slot (STAFF or ADMIN only).

    STAFF may only update slots belonging to their assigned centre.

    Returns:
        200 OK: { message, slot }
        400 Bad Request: validation error
        403 Forbidden: staff accessing another centre
        404 Not Found: slot missing
        409 Conflict: duplicate slot, overlap, or capacity exceeded
    """
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid request", "message": "JSON body required."}), 400

    # Centre isolation: load slot and verify ownership
    if g.current_user.role == UserRole.STAFF:
        existing = get_slot_by_id(slot_id, is_admin_or_staff=True)
        if not existing:
            return jsonify({"error": "Not Found", "message": "Slot not found."}), 404
        if existing.centre_id != g.current_staff.centre_id:
            return jsonify({
                "error": "Forbidden",
                "message": "Access denied for this centre.",
            }), 403
        # Prevent staff from moving a slot to another centre
        if "centre_id" in data and data["centre_id"] != g.current_staff.centre_id:
            return jsonify({
                "error": "Forbidden",
                "message": "Access denied for this centre.",
            }), 403

    try:
        updated = update_slot(slot_id, data)
    except (DuplicateSlotError, SlotOverlapError, DailyCapacityExceededError) as exc:
        return jsonify({"error": "Conflict", "message": exc.message, "code": exc.code}), 409
    except SlotValidationError as exc:
        code = 404 if "not found" in exc.message.lower() else 400
        return jsonify({"error": "Validation failed" if code == 400 else "Not Found", "messages": exc.errors}), code
    except SlotError as exc:
        return jsonify({"error": "Server error", "message": exc.message}), 500

    return jsonify({
        "message": "Slot updated successfully",
        "slot": _format_slot(updated),
    }), 200


@slots_bp.route("/<int:slot_id>", methods=["DELETE"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
@staff_centre_required
def remove_slot(slot_id: int):
    """Soft cancel a slot by setting status = CANCELLED (STAFF or ADMIN only).

    STAFF may only cancel slots belonging to their assigned centre.

    Returns:
        200 OK: { message, slot }
        403 Forbidden: staff accessing another centre
        404 Not Found: slot missing
    """
    # Centre isolation: load slot and verify ownership
    if g.current_user.role == UserRole.STAFF:
        existing = get_slot_by_id(slot_id, is_admin_or_staff=True)
        if not existing:
            return jsonify({"error": "Not Found", "message": "Slot not found."}), 404
        if existing.centre_id != g.current_staff.centre_id:
            return jsonify({
                "error": "Forbidden",
                "message": "Access denied for this centre.",
            }), 403

    try:
        cancelled = cancel_slot(slot_id)
    except SlotValidationError as exc:
        return jsonify({"error": "Not Found", "message": exc.message}), 404
    except SlotError as exc:
        return jsonify({"error": "Server error", "message": exc.message}), 500

    return jsonify({
        "message": "Slot cancelled successfully",
        "slot": _format_slot(cancelled),
    }), 200
