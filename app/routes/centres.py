"""Procurement Centre API routes.

Endpoints:
    GET    /api/centres       -> list active centres (or all centres for ADMIN)
    GET    /api/centres/<id>  -> view centre details
    POST   /api/centres       -> create centre (ADMIN only)
    PUT    /api/centres/<id>  -> update centre (ADMIN only)
    DELETE /api/centres/<id>  -> deactivate centre (ADMIN only)
"""

from flask import Blueprint, jsonify, request, g

from app.auth.decorators import login_required, role_required
from app.models import UserRole
from app.services.centre_service import (
    get_all_centres,
    get_centre_by_id,
    create_centre,
    update_centre,
    deactivate_centre,
    format_time_string,
    DuplicateCentreNameError,
    CentreValidationError,
    CentreError,
)

centres_bp = Blueprint("centres", __name__, url_prefix="/api/centres")


def _format_centre(c):
    """Serialize Centre instance to clean JSON dictionary."""
    return {
        "id": c.id,
        "name": c.name,
        "location": c.location,
        "opening_time": format_time_string(c.opening_time),
        "closing_time": format_time_string(c.closing_time),
        "daily_capacity": c.daily_capacity,
        "average_processing_minutes": c.average_processing_minutes,
        "is_active": c.is_active,
        "active": c.is_active,
    }


@centres_bp.route("", methods=["GET"])
@login_required
def list_centres():
    """List procurement centres.

    Query params:
        all: 'true' to include inactive (ADMIN only)
        include_inactive: 'true' to include inactive (ADMIN only)

    Returns:
        200 OK: { centres: [...] }
    """
    is_admin = (getattr(g, "current_user", None) and g.current_user.role == UserRole.ADMIN)
    req_all = request.args.get("all", "").lower() in ("true", "1") or \
              request.args.get("include_inactive", "").lower() in ("true", "1")

    include_inactive = is_admin and req_all
    centres = get_all_centres(include_inactive=include_inactive)

    return jsonify({"centres": [_format_centre(c) for c in centres]}), 200


@centres_bp.route("/<int:centre_id>", methods=["GET"])
@login_required
def get_centre(centre_id: int):
    """View details of a specific procurement centre.

    Returns:
        200 OK: { centre: { ... } }
        404 Not Found: if centre does not exist or is inactive (for non-admins)
    """
    is_admin = (getattr(g, "current_user", None) and g.current_user.role == UserRole.ADMIN)
    centre = get_centre_by_id(centre_id, include_inactive=is_admin)

    if not centre:
        return jsonify({"error": "Not Found", "message": "Centre not found."}), 404

    return jsonify({"centre": _format_centre(centre)}), 200


@centres_bp.route("", methods=["POST"])
@login_required
@role_required(UserRole.ADMIN)
def add_centre():
    """Create a new procurement centre (ADMIN only).

    Request JSON:
        { name, location, opening_time, closing_time, daily_capacity, average_processing_minutes }

    Returns:
        201 Created: { message, centre }
        400 Bad Request: validation error
        409 Conflict: duplicate centre name
    """
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid request", "message": "JSON body required."}), 400

    try:
        centre = create_centre(data)
    except DuplicateCentreNameError as exc:
        return jsonify({"error": "Conflict", "message": exc.message}), 409
    except CentreValidationError as exc:
        return jsonify({"error": "Validation failed", "messages": exc.errors}), 400
    except CentreError as exc:
        return jsonify({"error": "Server error", "message": exc.message}), 500

    return jsonify({
        "message": "Centre created successfully",
        "centre": _format_centre(centre),
    }), 201


@centres_bp.route("/<int:centre_id>", methods=["PUT"])
@login_required
@role_required(UserRole.ADMIN)
def edit_centre(centre_id: int):
    """Update an existing centre (ADMIN only).

    Returns:
        200 OK: { message, centre }
        400 Bad Request: validation error
        404 Not Found: centre missing
        409 Conflict: duplicate name
    """
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid request", "message": "JSON body required."}), 400

    try:
        updated = update_centre(centre_id, data)
    except DuplicateCentreNameError as exc:
        return jsonify({"error": "Conflict", "message": exc.message}), 409
    except CentreValidationError as exc:
        code = 404 if "not found" in exc.message.lower() else 400
        return jsonify({"error": "Validation failed" if code == 400 else "Not Found", "messages": exc.errors}), code
    except CentreError as exc:
        return jsonify({"error": "Server error", "message": exc.message}), 500

    return jsonify({
        "message": "Centre updated successfully",
        "centre": _format_centre(updated),
    }), 200


@centres_bp.route("/<int:centre_id>", methods=["DELETE"])
@login_required
@role_required(UserRole.ADMIN)
def remove_centre(centre_id: int):
    """Soft-delete / deactivate a centre (ADMIN only).

    Returns:
        200 OK: { message, centre }
        404 Not Found: centre missing
    """
    try:
        deactivated = deactivate_centre(centre_id)
    except CentreValidationError as exc:
        return jsonify({"error": "Not Found", "message": exc.message}), 404
    except CentreError as exc:
        return jsonify({"error": "Server error", "message": exc.message}), 500

    return jsonify({
        "message": "Centre deactivated successfully",
        "centre": _format_centre(deactivated),
    }), 200
