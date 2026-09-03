"""Farmer API routes.

Endpoints:
    GET /api/farmers/me  -> view current authenticated farmer profile
    PUT /api/farmers/me  -> update current authenticated farmer profile
"""

from flask import Blueprint, jsonify, request, g

from app.auth.decorators import login_required, role_required
from app.models import UserRole
from app.services.farmer_service import (
    get_farmer_by_user_id,
    update_farmer_profile,
    DuplicatePhoneError,
    FarmerValidationError,
    FarmerError,
)

farmers_bp = Blueprint("farmers", __name__, url_prefix="/api/farmers")


def _format_farmer_response(farmer):
    """Serialize farmer object to safe JSON dictionary."""
    return {
        "id": farmer.id,
        "user_id": farmer.user_id,
        "name": farmer.name,
        "phone": farmer.phone,
        "address": farmer.address,
        "city": farmer.city,
        "state": farmer.state,
        "pincode": farmer.pincode,
    }


@farmers_bp.route("/me", methods=["GET"])
@login_required
@role_required(UserRole.FARMER)
def get_my_profile():
    """Get the authenticated farmer's profile.

    Returns:
        200 OK: { farmer: { id, user_id, name, phone, address, city, state, pincode } }
        401 Unauthorized: if missing/invalid token
        403 Forbidden: if user is not a FARMER
        404 Not Found: if farmer profile record does not exist
    """
    farmer = get_farmer_by_user_id(g.current_user.id)
    if not farmer:
        return jsonify({
            "error": "Not Found",
            "message": "Farmer profile record not found.",
        }), 404

    return jsonify({"farmer": _format_farmer_response(farmer)}), 200


@farmers_bp.route("/me", methods=["PUT"])
@login_required
@role_required(UserRole.FARMER)
def update_my_profile():
    """Update the authenticated farmer's profile.

    Request JSON:
        {"name": "...", "phone": "...", "address": "...", "city": "...", "state": "...", "pincode": "..."}

    Returns:
        200 OK: { message, farmer: { ... } }
        400 Bad Request: validation failed or JSON body missing
        401 Unauthorized: if missing/invalid token
        403 Forbidden: if user is not a FARMER
        409 Conflict: if phone number is already registered to another account
        500 Internal Server Error: database failure
    """
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({
            "error": "Invalid request",
            "message": "JSON body required.",
        }), 400

    try:
        updated_farmer = update_farmer_profile(g.current_user.id, data)
    except DuplicatePhoneError as exc:
        return jsonify({
            "error": "Conflict",
            "message": exc.message,
        }), 409
    except FarmerValidationError as exc:
        return jsonify({
            "error": "Validation failed",
            "messages": exc.errors,
        }), 400
    except FarmerError as exc:
        return jsonify({
            "error": "Server error",
            "message": exc.message,
        }), 500

    return jsonify({
        "message": "Profile updated successfully",
        "farmer": _format_farmer_response(updated_farmer),
    }), 200
