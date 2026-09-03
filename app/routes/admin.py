"""
Admin Analytics and Audit Log API endpoints.

All endpoints under /api/admin are strictly restricted to ADMIN role.
"""

from flask import Blueprint, request, jsonify, g
from app.auth.decorators import login_required, role_required
from app.models.common import UserRole
from app.services.analytics_service import (
    get_overview_analytics,
    get_booking_analytics,
    get_procurement_analytics,
    get_payment_analytics,
    get_queue_analytics,
    get_delay_analytics,
    AnalyticsValidationError,
)
from app.services.audit_service import (
    get_audit_logs,
    get_audit_log_by_id,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


# --- 1. Analytics Endpoints ----------------------------------------------------

@admin_bp.route("/analytics/overview", methods=["GET"])
@login_required
@role_required(UserRole.ADMIN)
def admin_analytics_overview():
    """Return system-wide KPI summary metrics."""
    try:
        data = get_overview_analytics()
        return jsonify(data), 200
    except Exception as exc:
        return jsonify({"error": f"Failed to load overview analytics: {exc}"}), 500


@admin_bp.route("/analytics/bookings", methods=["GET"])
@login_required
@role_required(UserRole.ADMIN)
def admin_analytics_bookings():
    """Return booking breakdown statistics and daily trends."""
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    centre_id = request.args.get("centre_id", type=int)
    crop_id = request.args.get("crop_id", type=int)

    try:
        data = get_booking_analytics(
            start_date=start_date,
            end_date=end_date,
            centre_id=centre_id,
            crop_id=crop_id,
        )
        return jsonify(data), 200
    except AnalyticsValidationError as ave:
        return jsonify({"error": str(ave)}), 400
    except Exception as exc:
        return jsonify({"error": f"Failed to load booking analytics: {exc}"}), 500


@admin_bp.route("/analytics/procurement", methods=["GET"])
@login_required
@role_required(UserRole.ADMIN)
def admin_analytics_procurement():
    """Return procurement breakdown by status, crop, and centre."""
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    centre_id = request.args.get("centre_id", type=int)
    crop_id = request.args.get("crop_id", type=int)

    try:
        data = get_procurement_analytics(
            start_date=start_date,
            end_date=end_date,
            centre_id=centre_id,
            crop_id=crop_id,
        )
        return jsonify(data), 200
    except AnalyticsValidationError as ave:
        return jsonify({"error": str(ave)}), 400
    except Exception as exc:
        return jsonify({"error": f"Failed to load procurement analytics: {exc}"}), 500


@admin_bp.route("/analytics/payments", methods=["GET"])
@login_required
@role_required(UserRole.ADMIN)
def admin_analytics_payments():
    """Return high-level payment status and volume statistics."""
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    try:
        data = get_payment_analytics(start_date=start_date, end_date=end_date)
        return jsonify(data), 200
    except AnalyticsValidationError as ave:
        return jsonify({"error": str(ave)}), 400
    except Exception as exc:
        return jsonify({"error": f"Failed to load payment analytics: {exc}"}), 500


@admin_bp.route("/analytics/queue", methods=["GET"])
@login_required
@role_required(UserRole.ADMIN)
def admin_analytics_queue():
    """Return centre queue state and estimated wait metrics."""
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    centre_id = request.args.get("centre_id", type=int)

    try:
        data = get_queue_analytics(
            start_date=start_date,
            end_date=end_date,
            centre_id=centre_id,
        )
        return jsonify(data), 200
    except AnalyticsValidationError as ave:
        return jsonify({"error": str(ave)}), 400
    except Exception as exc:
        return jsonify({"error": f"Failed to load queue analytics: {exc}"}), 500


@admin_bp.route("/analytics/delays", methods=["GET"])
@login_required
@role_required(UserRole.ADMIN)
def admin_analytics_delays():
    """Return procurement delay breakdown statistics."""
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    centre_id = request.args.get("centre_id", type=int)

    try:
        data = get_delay_analytics(
            start_date=start_date,
            end_date=end_date,
            centre_id=centre_id,
        )
        return jsonify(data), 200
    except AnalyticsValidationError as ave:
        return jsonify({"error": str(ave)}), 400
    except Exception as exc:
        return jsonify({"error": f"Failed to load delay analytics: {exc}"}), 500


# --- 2. Audit Log Endpoints ----------------------------------------------------

@admin_bp.route("/audit-logs", methods=["GET"])
@login_required
@role_required(UserRole.ADMIN)
def admin_get_audit_logs():
    """List system audit logs with filtering and pagination."""
    action = request.args.get("action")
    entity_type = request.args.get("entity_type")
    user_id = request.args.get("user_id", type=int)
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    # Cap per_page
    per_page = min(max(per_page, 1), 100)

    try:
        logs, total = get_audit_logs(
            action=action,
            entity_type=entity_type,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            page=page,
            per_page=per_page,
        )
        return jsonify({
            "audit_logs": [log.to_dict() for log in logs],
            "total": total,
            "page": page,
            "per_page": per_page,
        }), 200
    except Exception as exc:
        return jsonify({"error": f"Failed to load audit logs: {exc}"}), 500


@admin_bp.route("/audit-logs/<int:log_id>", methods=["GET"])
@login_required
@role_required(UserRole.ADMIN)
def admin_get_audit_log_detail(log_id: int):
    """Retrieve details for a single audit log entry."""
    log = get_audit_log_by_id(log_id)
    if not log:
        return jsonify({"error": "Audit log not found"}), 404

    return jsonify({"audit_log": log.to_dict()}), 200


# --- 3. Staff Management Endpoints ----------------------------------------------------

def _format_staff(s):
    """Serialize Staff instance to clean JSON dictionary."""
    return {
        "id": s.id,
        "user_id": s.user_id,
        "name": s.name,
        "phone": s.phone,
        "is_active": s.user.is_active if s.user else None,
        "centre_id": s.centre_id,
        "centre_name": s.centre.name if s.centre else None,
    }


@admin_bp.route("/staff", methods=["GET"])
@login_required
@role_required(UserRole.ADMIN)
def admin_list_staff():
    """List all staff records with their assigned centre."""
    from app.services.staff_service import get_all_staff
    staff_list = get_all_staff()
    return jsonify({"staff": [_format_staff(s) for s in staff_list]}), 200


@admin_bp.route("/staff/<int:staff_id>", methods=["GET"])
@login_required
@role_required(UserRole.ADMIN)
def admin_get_staff(staff_id):
    """Retrieve a single staff record."""
    from app.services.staff_service import get_staff_by_id
    staff = get_staff_by_id(staff_id)
    if not staff:
        return jsonify({"error": "Not Found", "message": f"Staff {staff_id} not found."}), 404
    return jsonify({"staff": _format_staff(staff)}), 200


@admin_bp.route("/staff", methods=["POST"])
@login_required
@role_required(UserRole.ADMIN)
def admin_create_staff():
    """Provision a new staff user (creates Supabase Auth user + local records)."""
    from app.services.staff_service import (
        provision_staff,
        StaffValidationError,
        StaffConflictError,
        StaffError,
    )

    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid request", "message": "JSON body required."}), 400

    email = (data.get("email") or "").strip()
    name = (data.get("name") or "").strip()
    phone = data.get("phone")
    centre_id = data.get("centre_id")
    password = data.get("password")

    if not email or "@" not in email:
        return jsonify({"error": "Validation failed", "messages": ["A valid email is required."]}), 400
    if not name or len(name) < 2:
        return jsonify({"error": "Validation failed", "messages": ["Name must be at least 2 characters."]}), 400

    try:
        staff = provision_staff(
            email=email,
            name=name,
            phone=phone,
            centre_id=centre_id,
            password=password,
        )
    except StaffValidationError as exc:
        return jsonify({"error": "Validation failed", "messages": exc.errors}), 400
    except StaffConflictError as exc:
        return jsonify({"error": "Conflict", "message": exc.message}), 409
    except StaffError as exc:
        return jsonify({"error": "Server error", "message": exc.message}), 500

    return jsonify({
        "message": "Staff created successfully",
        "staff": _format_staff(staff),
    }), 201


@admin_bp.route("/staff/<int:staff_id>", methods=["PUT"])
@login_required
@role_required(UserRole.ADMIN)
def admin_update_staff(staff_id):
    """Update staff profile: name, phone, centre assignment, active status."""
    from app.services.staff_service import (
        update_staff,
        deactivate_staff,
        activate_staff,
        StaffValidationError,
        StaffNotFoundError,
        StaffError,
    )

    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid request", "message": "JSON body required."}), 400

    # Handle activation/deactivation explicitly
    if "is_active" in data:
        try:
            if data["is_active"]:
                staff = activate_staff(staff_id)
            else:
                staff = deactivate_staff(staff_id)
        except StaffNotFoundError:
            return jsonify({"error": "Not Found", "message": f"Staff {staff_id} not found."}), 404
        except StaffError as exc:
            return jsonify({"error": "Server error", "message": exc.message}), 500
        return jsonify({
            "message": "Staff updated successfully",
            "staff": _format_staff(staff),
        }), 200

    try:
        staff = update_staff(staff_id, data)
    except StaffNotFoundError:
        return jsonify({"error": "Not Found", "message": f"Staff {staff_id} not found."}), 404
    except StaffValidationError as exc:
        return jsonify({"error": "Validation failed", "messages": exc.errors}), 400
    except StaffError as exc:
        return jsonify({"error": "Server error", "message": exc.message}), 500

    return jsonify({
        "message": "Staff updated successfully",
        "staff": _format_staff(staff),
    }), 200


@admin_bp.route("/staff/<int:staff_id>", methods=["DELETE"])
@login_required
@role_required(UserRole.ADMIN)
def admin_delete_staff(staff_id):
    """Soft-deactivate a staff user. Does NOT delete the Supabase Auth user."""
    from app.services.staff_service import deactivate_staff, StaffNotFoundError, StaffError

    try:
        staff = deactivate_staff(staff_id)
    except StaffNotFoundError:
        return jsonify({"error": "Not Found", "message": f"Staff {staff_id} not found."}), 404
    except StaffError as exc:
        return jsonify({"error": "Server error", "message": exc.message}), 500

    return jsonify({
        "message": "Staff deactivated successfully",
        "staff": _format_staff(staff),
    }), 200
