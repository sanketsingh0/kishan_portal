"""Staff-Controlled Next-Day Carry-Forward API routes.

Endpoints (STAFF/ADMIN only; FARMER is rejected by role check):
  GET  /api/staff/carry-forward/eligible?date=YYYY-MM-DD[&centre_id=N]
  POST /api/staff/carry-forward
"""

from datetime import datetime

from flask import Blueprint, jsonify, request, g

from app.auth.decorators import (
    login_required,
    roles_required,
    staff_centre_required,
)
from app.models import CarryForwardReason, UserRole
from app.services.slot_service import format_date_string, format_time_string

carry_forward_bp = Blueprint(
    "carry_forward", __name__, url_prefix="/api/staff/carry-forward")


def _resolve_centre(require_query_for_admin=False):
    """Return (centre_id, error_response)."""
    if g.current_user.role == UserRole.STAFF:
        staff = g.current_staff
        if staff is None or staff.centre_id is None:
            return None, (jsonify({
                "error": "Forbidden",
                "message": "No centre assigned to your account."}), 403)
        return staff.centre_id, None
    centre_id = request.args.get("centre_id", type=int)
    if require_query_for_admin and centre_id is None:
        # POST body variant handled separately; for GET require centre_id.
        return None, (jsonify({
            "error": "Validation failed",
            "message": "centre_id query parameter is required for ADMIN."}), 400)
    return centre_id, None


def _fmt_booking(b):
    slot = b.slot
    proc = b.procurement
    carry = None
    try:
        from app.models import BookingCarryForward
        carry = BookingCarryForward.query.filter_by(
            original_booking_id=b.id).first()
    except Exception:
        carry = None
    return {
        "booking_id": b.id,
        "token_number": b.token_number,
        "farmer_id": b.farmer_id,
        "farmer_name": b.farmer.name if b.farmer else "Farmer",
        "slot_id": b.slot_id,
        "slot_time": (f"{format_time_string(slot.start_time)} - "
                      f"{format_time_string(slot.end_time)}") if slot else None,
        "crop": slot.crop.name if slot and slot.crop else None,
        "booking_date": format_date_string(slot.slot_date) if slot else None,
        "status": b.status,
        "procurement_status": proc.procurement_status if proc else "PENDING",
        "already_carried_forward": carry is not None,
        "new_booking_id": carry.new_booking_id if carry else None,
    }

@carry_forward_bp.route("/eligible", methods=["GET"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
@staff_centre_required
def list_eligible():
    from app.extensions import db
    from app.models import Centre
    from app.services.carry_forward_service import (
        get_eligible_bookings, _parse_source_date)
    date_str = (request.args.get("date") or "").strip()
    if not date_str:
        return jsonify({"error": "Validation failed",
                        "message": "date query param YYYY-MM-DD required."}), 400
    try:
        src = _parse_source_date(date_str)
    except Exception as exc:
        return jsonify({"error": "Validation failed",
                        "message": str(exc)}), 400
    if g.current_user.role == UserRole.STAFF:
        centre_id = g.current_staff.centre_id
    else:
        centre_id = request.args.get("centre_id", type=int)
        if centre_id is None:
            return jsonify({"error": "Validation failed",
                            "message": "centre_id required for ADMIN."}), 400
    centre = db.session.get(Centre, centre_id)
    if centre is None:
        return jsonify({"error": "Not Found",
                        "message": f"Centre {centre_id} not found."}), 404
    bookings = get_eligible_bookings(centre_id, src)
    return jsonify({"centre_id": centre_id,
                    "date": format_date_string(src),
                    "eligible_count": len(bookings),
                    "eligible": [_fmt_booking(b) for b in bookings],
                    "reasons": list(CarryForwardReason.choices)}), 200


@carry_forward_bp.route("", methods=["POST"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
@staff_centre_required
def do_carry_forward():
    from app.services.carry_forward_execute import carry_forward_bookings
    from app.services.carry_forward_service import CarryForwardValidationError
    from app.services.carry_forward_service import CarryForwardError
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid request",
                        "message": "JSON body required."}), 400
    if g.current_user.role == UserRole.STAFF:
        centre_id = g.current_staff.centre_id
    else:
        centre_id = data.get("centre_id")
        if centre_id is None:
            centre_id = request.args.get("centre_id", type=int)
        if isinstance(centre_id, bool) or not isinstance(centre_id, int):
            return jsonify({"error": "Validation failed",
                            "message": "centre_id required for ADMIN."}), 400
    try:
        result = carry_forward_bookings(
            actor_user=g.current_user,
            centre_id=centre_id,
            booking_ids=data.get("booking_ids"),
            target_date=data.get("target_date"),
            reason=data.get("reason"),
            target_slot_id=data.get("target_slot_id"),
        )
    except CarryForwardValidationError as exc:
        return jsonify({"error": "Validation failed",
                        "message": exc.message,
                        "messages": exc.errors}), 400
    except CarryForwardError as exc:
        return jsonify({"error": "Server error",
                        "message": exc.message}), 500
    msg = (f"{result['successful_count']} bookings carried forward to "
           f"{result['target_date']}.")
    return jsonify({"message": msg, **result}), 200


