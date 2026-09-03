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
