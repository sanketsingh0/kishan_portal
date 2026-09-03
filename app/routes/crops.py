"""Crop Catalogue API routes.

Endpoints:
    GET    /api/crops       -> list active crops (or all crops for ADMIN)
    GET    /api/crops/<id>  -> view crop details
    POST   /api/crops       -> create crop (ADMIN only)
    PUT    /api/crops/<id>  -> update crop (ADMIN only)
    DELETE /api/crops/<id>  -> deactivate crop (ADMIN only)
"""

from flask import Blueprint, jsonify, request, g

from app.auth.decorators import login_required, role_required
from app.models import UserRole
from app.services.crop_service import (
    get_all_crops,
    get_crop_by_id,
    create_crop,
    update_crop,
    deactivate_crop,
    DuplicateCropNameError,
    CropValidationError,
    CropError,
)

crops_bp = Blueprint("crops", __name__, url_prefix="/api/crops")


def _format_crop(c):
    """Serialize Crop instance to clean JSON dictionary."""
    return {
        "id": c.id,
        "name": c.name,
        "category": c.category,
        "is_active": c.is_active,
        "active": c.is_active,
    }


@crops_bp.route("", methods=["GET"])
@login_required
def list_crops():
    """List crop catalogue items.

    Query params:
        all: 'true' to include inactive (ADMIN only)
        include_inactive: 'true' to include inactive (ADMIN only)

    Returns:
        200 OK: { crops: [...] }
    """
    is_admin = (getattr(g, "current_user", None) and g.current_user.role == UserRole.ADMIN)
    req_all = request.args.get("all", "").lower() in ("true", "1") or \
              request.args.get("include_inactive", "").lower() in ("true", "1")

    include_inactive = is_admin and req_all
    crops = get_all_crops(include_inactive=include_inactive)

    return jsonify({"crops": [_format_crop(c) for c in crops]}), 200


@crops_bp.route("/<int:crop_id>", methods=["GET"])
@login_required
def get_crop(crop_id: int):
    """View details of a specific crop.

    Returns:
        200 OK: { crop: { ... } }
        404 Not Found: if crop does not exist or is inactive (for non-admins)
    """
    is_admin = (getattr(g, "current_user", None) and g.current_user.role == UserRole.ADMIN)
    crop = get_crop_by_id(crop_id, include_inactive=is_admin)

    if not crop:
        return jsonify({"error": "Not Found", "message": "Crop not found."}), 404

    return jsonify({"crop": _format_crop(crop)}), 200


@crops_bp.route("", methods=["POST"])
@login_required
@role_required(UserRole.ADMIN)
def add_crop():
    """Create a new crop entry (ADMIN only).

    Request JSON:
        { name, category }

    Returns:
        201 Created: { message, crop }
        400 Bad Request: validation error
        409 Conflict: duplicate crop name
    """
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid request", "message": "JSON body required."}), 400

    try:
        crop = create_crop(data)
    except DuplicateCropNameError as exc:
        return jsonify({"error": "Conflict", "message": exc.message}), 409
    except CropValidationError as exc:
        return jsonify({"error": "Validation failed", "messages": exc.errors}), 400
    except CropError as exc:
        return jsonify({"error": "Server error", "message": exc.message}), 500

    return jsonify({
        "message": "Crop created successfully",
        "crop": _format_crop(crop),
    }), 201


@crops_bp.route("/<int:crop_id>", methods=["PUT"])
@login_required
@role_required(UserRole.ADMIN)
def edit_crop(crop_id: int):
    """Update an existing crop (ADMIN only).

    Returns:
        200 OK: { message, crop }
        400 Bad Request: validation error
        404 Not Found: crop missing
        409 Conflict: duplicate name
    """
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid request", "message": "JSON body required."}), 400

    try:
        updated = update_crop(crop_id, data)
    except DuplicateCropNameError as exc:
        return jsonify({"error": "Conflict", "message": exc.message}), 409
    except CropValidationError as exc:
        code = 404 if "not found" in exc.message.lower() else 400
        return jsonify({"error": "Validation failed" if code == 400 else "Not Found", "messages": exc.errors}), code
    except CropError as exc:
        return jsonify({"error": "Server error", "message": exc.message}), 500

    return jsonify({
        "message": "Crop updated successfully",
        "crop": _format_crop(updated),
    }), 200


@crops_bp.route("/<int:crop_id>", methods=["DELETE"])
@login_required
@role_required(UserRole.ADMIN)
def remove_crop(crop_id: int):
    """Soft-delete / deactivate a crop (ADMIN only).

    Returns:
        200 OK: { message, crop }
        404 Not Found: crop missing
    """
    try:
        deactivated = deactivate_crop(crop_id)
    except CropValidationError as exc:
        return jsonify({"error": "Not Found", "message": exc.message}), 404
    except CropError as exc:
        return jsonify({"error": "Server error", "message": exc.message}), 500

    return jsonify({
        "message": "Crop deactivated successfully",
        "crop": _format_crop(deactivated),
    }), 200
