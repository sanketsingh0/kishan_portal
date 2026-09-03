"""Procurement API routes.

Endpoints:
    GET  /api/procurement/my/<booking_id>  -> farmer view own procurement status (FARMER)
    GET  /api/procurement/<booking_id>     -> staff/admin view procurement (STAFF/ADMIN)
    POST /api/procurement/<booking_id>     -> create procurement record (STAFF/ADMIN)
    PUT  /api/procurement/<booking_id>     -> update procurement record (STAFF/ADMIN)
"""

from flask import Blueprint, jsonify, request, g
from app.auth.decorators import login_required, role_required, roles_required, staff_centre_required
from app.models import UserRole, Booking, ProcurementStatus
from app.extensions import db
from app.services.farmer_service import get_farmer_by_user_id
from app.services.procurement_service import (
    get_procurement_by_booking,
    create_procurement,
    update_procurement,
    ProcurementNotFoundError,
    ProcurementConflictError,
    ProcurementValidationError,
    ProcurementError,
)

procurement_bp = Blueprint("procurement", __name__, url_prefix="/api/procurement")


def _format_procurement_response(booking_id: int, procurement):
    """Serialize Procurement instance or return clean default payload."""
    if not procurement:
        return {
            "booking_id": booking_id,
            "procurement_status": ProcurementStatus.PENDING,
            "quantity": None,
            "unit": "quintal",
            "procurement_date": None,
            "remarks": None,
        }
    return {
        "id": procurement.id,
        "booking_id": procurement.booking_id,
        "procurement_status": procurement.procurement_status,
        "quantity": procurement.quantity,
        "unit": procurement.unit,
        "procurement_date": procurement.procurement_date.isoformat() if procurement.procurement_date else None,
        "remarks": procurement.remarks,
        "created_at": procurement.created_at.isoformat() if procurement.created_at else None,
        "updated_at": procurement.updated_at.isoformat() if procurement.updated_at else None,
    }


@procurement_bp.route("/my/<int:booking_id>", methods=["GET"])
@login_required
@role_required(UserRole.FARMER)
def farmer_get_procurement(booking_id: int):
    """View procurement status for a booking owned by the authenticated farmer."""
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({"error": "Not Found", "message": f"Booking {booking_id} not found."}), 404

    farmer = get_farmer_by_user_id(g.current_user.id)
    if not farmer or booking.farmer_id != farmer.id:
        return jsonify({"error": "Not Found", "message": "Booking not found or access denied."}), 404

    return jsonify({"procurement": _format_procurement_response(booking.id, booking.procurement)}), 200


@procurement_bp.route("/<int:booking_id>", methods=["GET"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
@staff_centre_required
def staff_get_procurement(booking_id: int):
    """View procurement details for a booking (STAFF/ADMIN).

    STAFF may only access procurement for bookings at their assigned centre.
    """
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({"error": "Not Found", "message": f"Booking {booking_id} not found."}), 404

    # Centre isolation: resolve centre from booking -> slot
    if g.current_user.role == UserRole.STAFF:
        centre_id = booking.slot.centre_id if booking.slot else None
        if centre_id != g.current_staff.centre_id:
            return jsonify({
                "error": "Forbidden",
                "message": "Access denied for this centre.",
            }), 403

    return jsonify({"procurement": _format_procurement_response(booking.id, booking.procurement)}), 200


@procurement_bp.route("/<int:booking_id>", methods=["POST"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
@staff_centre_required
def staff_create_procurement(booking_id: int):
    """Create procurement record for a booking (STAFF/ADMIN).

    STAFF may only create procurement for bookings at their assigned centre.
    """
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid request", "message": "JSON body required."}), 400

    # Centre isolation: resolve centre from booking -> slot
    if g.current_user.role == UserRole.STAFF:
        booking = db.session.get(Booking, booking_id)
        if not booking:
            return jsonify({"error": "Not Found", "message": f"Booking {booking_id} not found."}), 404
        centre_id = booking.slot.centre_id if booking.slot else None
        if centre_id != g.current_staff.centre_id:
            return jsonify({
                "error": "Forbidden",
                "message": "Access denied for this centre.",
            }), 403

    try:
        procurement = create_procurement(booking_id, data)
    except ProcurementConflictError as pce:
        return jsonify({"error": "Conflict", "message": pce.message}), 409
    except ProcurementNotFoundError as pnf:
        return jsonify({"error": "Not Found", "message": pnf.message}), 404
    except ProcurementValidationError as pve:
        return jsonify({"error": "Validation failed", "messages": pve.errors}), 400
    except ProcurementError as pe:
        return jsonify({"error": "Server error", "message": pe.message}), 500

    return jsonify({
        "message": "Procurement record created successfully",
        "procurement": _format_procurement_response(booking_id, procurement),
    }), 201


@procurement_bp.route("/<int:booking_id>", methods=["PUT"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
@staff_centre_required
def staff_update_procurement(booking_id: int):
    """Update procurement record for a booking (STAFF/ADMIN).

    STAFF may only update procurement for bookings at their assigned centre.
    """
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid request", "message": "JSON body required."}), 400

    # Centre isolation: resolve centre from booking -> slot
    if g.current_user.role == UserRole.STAFF:
        booking = db.session.get(Booking, booking_id)
        if not booking:
            return jsonify({"error": "Not Found", "message": f"Booking {booking_id} not found."}), 404
        centre_id = booking.slot.centre_id if booking.slot else None
        if centre_id != g.current_staff.centre_id:
            return jsonify({
                "error": "Forbidden",
                "message": "Access denied for this centre.",
            }), 403

    try:
        procurement = update_procurement(booking_id, data)
    except ProcurementNotFoundError as pnf:
        return jsonify({"error": "Not Found", "message": pnf.message}), 404
    except ProcurementValidationError as pve:
        return jsonify({"error": "Validation failed", "messages": pve.errors}), 400
    except ProcurementError as pe:
        return jsonify({"error": "Server error", "message": pe.message}), 500

    return jsonify({
        "message": "Procurement record updated successfully",
        "procurement": _format_procurement_response(booking_id, procurement),
    }), 200
