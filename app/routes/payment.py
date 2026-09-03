"""Payment status API routes.

Endpoints:
    GET  /api/payment/my/<booking_id>  -> farmer view own payment status (FARMER)
    GET  /api/payment/<booking_id>     -> staff/admin view payment details (STAFF/ADMIN)
    POST /api/payment/<booking_id>     -> create payment record (STAFF/ADMIN)
    PUT  /api/payment/<booking_id>     -> update payment record (STAFF/ADMIN)
"""

from flask import Blueprint, jsonify, request, g
from app.auth.decorators import login_required, role_required, roles_required
from app.models import UserRole, Booking, PaymentStatus
from app.extensions import db
from app.services.farmer_service import get_farmer_by_user_id
from app.services.payment_service import (
    get_payment_by_booking,
    create_payment,
    update_payment,
    PaymentNotFoundError,
    PaymentConflictError,
    PaymentValidationError,
    PaymentError,
)

payment_bp = Blueprint("payment", __name__, url_prefix="/api/payment")


def _format_payment_response(booking_id: int, payment):
    """Serialize Payment instance or return clean default payload."""
    if not payment:
        return {
            "booking_id": booking_id,
            "payment_status": PaymentStatus.PENDING,
            "amount": None,
            "payment_reference": None,
            "payment_date": None,
            "remarks": None,
        }
    return {
        "id": payment.id,
        "booking_id": payment.booking_id,
        "payment_status": payment.payment_status,
        "amount": float(payment.amount) if payment.amount is not None else None,
        "payment_reference": payment.payment_reference,
        "payment_date": payment.payment_date.isoformat() if payment.payment_date else None,
        "remarks": payment.remarks,
        "created_at": payment.created_at.isoformat() if payment.created_at else None,
        "updated_at": payment.updated_at.isoformat() if payment.updated_at else None,
    }


@payment_bp.route("/my/<int:booking_id>", methods=["GET"])
@login_required
@role_required(UserRole.FARMER)
def farmer_get_payment(booking_id: int):
    """View payment status for a booking owned by the authenticated farmer."""
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({"error": "Not Found", "message": f"Booking {booking_id} not found."}), 404

    farmer = get_farmer_by_user_id(g.current_user.id)
    if not farmer or booking.farmer_id != farmer.id:
        return jsonify({"error": "Not Found", "message": "Booking not found or access denied."}), 404

    return jsonify({"payment": _format_payment_response(booking.id, booking.payment)}), 200


@payment_bp.route("/<int:booking_id>", methods=["GET"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
def staff_get_payment(booking_id: int):
    """View payment details for a booking (STAFF/ADMIN)."""
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({"error": "Not Found", "message": f"Booking {booking_id} not found."}), 404

    return jsonify({"payment": _format_payment_response(booking.id, booking.payment)}), 200


@payment_bp.route("/<int:booking_id>", methods=["POST"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
def staff_create_payment(booking_id: int):
    """Create payment status record for a booking (STAFF/ADMIN)."""
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid request", "message": "JSON body required."}), 400

    try:
        payment = create_payment(booking_id, data)
    except PaymentConflictError as pce:
        return jsonify({"error": "Conflict", "message": pce.message}), 409
    except PaymentNotFoundError as pnf:
        return jsonify({"error": "Not Found", "message": pnf.message}), 404
    except PaymentValidationError as pve:
        return jsonify({"error": "Validation failed", "messages": pve.errors}), 400
    except PaymentError as pe:
        return jsonify({"error": "Server error", "message": pe.message}), 500

    return jsonify({
        "message": "Payment status record created successfully",
        "payment": _format_payment_response(booking_id, payment),
    }), 201


@payment_bp.route("/<int:booking_id>", methods=["PUT"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
def staff_update_payment(booking_id: int):
    """Update payment status record for a booking (STAFF/ADMIN)."""
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid request", "message": "JSON body required."}), 400

    try:
        payment = update_payment(booking_id, data)
    except PaymentNotFoundError as pnf:
        return jsonify({"error": "Not Found", "message": pnf.message}), 404
    except PaymentValidationError as pve:
        return jsonify({"error": "Validation failed", "messages": pve.errors}), 400
    except PaymentError as pe:
        return jsonify({"error": "Server error", "message": pe.message}), 500

    return jsonify({
        "message": "Payment status record updated successfully",
        "payment": _format_payment_response(booking_id, payment),
    }), 200
