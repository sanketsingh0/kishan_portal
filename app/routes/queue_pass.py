"""Smart Queue Pass API routes (SIH 26032 - Stage 1 backend foundation).

Endpoints:
    GET  /api/queue-pass/my/<booking_id>   -> farmer retrieves own pass (FARMER only)
    GET  /api/queue-pass/lookup/<pass_id>  -> staff/admin review a pass (centre isolated)
    POST /api/queue-pass/verify            -> staff/admin verify mandi entry (centre isolated)

Stage 1 is backend-only: no QR image generation, PDF export or scanner UI.
The secure pass identifier is designed to be used as a QR payload in Stage 2.
"""

from flask import Blueprint, jsonify, request, g, render_template

from app.auth.decorators import (
    login_required,
    role_required,
    roles_required,
    staff_centre_required,
)
from app.extensions import db
from app.models import Booking, SmartQueuePassStatus, UserRole
from app.services.farmer_service import get_farmer_by_user_id
from app.services.slot_service import format_date_string, format_time_string
from app.services.smart_queue_pass_service import (
    SmartQueuePassConflictError,
    SmartQueuePassError,
    SmartQueuePassForbiddenError,
    SmartQueuePassNotFoundError,
    SmartQueuePassValidationError,
    get_or_create_pass_for_booking,
    get_pass_context,
    get_pass_for_centre,
    get_pass_for_display,
    record_verification_failure,
    verify_pass,
)

queue_pass_bp = Blueprint("queue_pass", __name__, url_prefix="/api/queue-pass")


def _error_status_and_label(exc: SmartQueuePassError) -> tuple[int, str]:
    """Map a Smart Queue Pass business error to an HTTP status + error label."""
    if isinstance(exc, SmartQueuePassNotFoundError):
        return 404, "Not Found"
    if isinstance(exc, SmartQueuePassForbiddenError):
        return 403, "Forbidden"
    if isinstance(exc, SmartQueuePassConflictError):
        return 409, "Conflict"
    if isinstance(exc, SmartQueuePassValidationError):
        return 400, "Validation failed"
    return 500, "Server error"


def _format_queue_pass(pass_row) -> dict:
    """Serialize a Smart Queue Pass for API responses.

    Only non-sensitive operational data is exposed (booking, farmer name,
    centre, crop, slot, token, pass status). Phone numbers, bank details, IFSC,
    JWTs and passwords are never included.
    """
    payload = pass_row.to_dict()
    booking = pass_row.booking
    slot = booking.slot if booking else None
    procurement = booking.procurement if booking else None

    payload.update({
        "entry_verified": pass_row.status == SmartQueuePassStatus.VERIFIED,
        "booking": {
            "id": booking.id,
            "status": booking.status,
            "token_number": booking.token_number,
            "booking_date": booking.booking_date.isoformat() if booking.booking_date else None,
        } if booking else None,
        "farmer": {
            "id": booking.farmer.id,
            "name": booking.farmer.name,
        } if booking and booking.farmer else None,
        "centre": {
            "id": slot.centre.id,
            "name": slot.centre.name,
            "location": slot.centre.location,
        } if slot and slot.centre else None,
        "crop": {
            "id": slot.crop.id,
            "name": slot.crop.name,
        } if slot and slot.crop else None,
        "slot": {
            "id": slot.id,
            "slot_date": format_date_string(slot.slot_date),
            "start_time": format_time_string(slot.start_time),
            "end_time": format_time_string(slot.end_time),
        } if slot else None,
        "procurement": {
            "procurement_status": procurement.procurement_status,
            "procurement_date": (
                procurement.procurement_date.isoformat()
                if procurement.procurement_date else None
            ),
        } if procurement else None,
    })
    return payload


def _operating_centre_id() -> int | None:
    """Centre the authenticated actor is operating on (server-side value only).

    STAFF are pinned to their assigned centre by @staff_centre_required; ADMIN
    operate system-wide (None), in which case the pass's own centre is used.
    """
    if g.current_user.role == UserRole.STAFF:
        return g.current_staff.centre_id
    return None


@queue_pass_bp.route("/my/<int:booking_id>", methods=["GET"])
@login_required
@role_required(UserRole.FARMER)
def get_my_smart_queue_pass(booking_id: int):
    """Retrieve the Smart Queue Pass of the authenticated farmer's own booking.

    A confirmed booking without a pass (e.g. created before this feature) gets
    its pass lazily - at most one pass ever exists per booking.

    Returns:
        200 OK: { smart_queue_pass: { ... } }
        404 Not Found: missing booking or another farmer's booking
        409 Conflict: booking is not in a confirmed state
    """
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({
            "error": "Not Found",
            "message": f"Booking {booking_id} not found.",
        }), 404

    farmer = get_farmer_by_user_id(g.current_user.id)
    if not farmer or booking.farmer_id != farmer.id:
        # Identical to "missing" so the existence of other farmers' bookings is
        # never disclosed.
        return jsonify({
            "error": "Not Found",
            "message": "Booking not found or access denied.",
        }), 404

    try:
        pass_row = get_or_create_pass_for_booking(booking)
    except SmartQueuePassError as exc:
        status, label = _error_status_and_label(exc)
        return jsonify({"error": label, "message": exc.message, "code": exc.code}), status

    if pass_row is None:
        return jsonify({
            "error": "Conflict",
            "message": (
                f"Booking is {booking.status}. A Smart Queue Pass is only "
                "available for confirmed bookings."
            ),
            "code": "PASS_CONFLICT",
        }), 409

    return jsonify({"smart_queue_pass": _format_queue_pass(pass_row)}), 200


@queue_pass_bp.route("/my/<int:booking_id>/display", methods=["GET"])
@login_required
@role_required(UserRole.FARMER)
def get_queue_pass_for_display(booking_id: int):
    """Get a Smart Queue Pass ready for display to the farmer (FARMER only).

    This endpoint returns all the data needed to render the pass UI,
    including the QR code as a base64-encoded PNG image.

    The QR code encodes ONLY the secure_pass_id (kp_pass_<random>).
    It contains NO farmer information, phone, bank details, JWT, or
    any other sensitive data.

    Returns:
        200 OK: { pass_data: { ... } } with QR code and pass details
        403 Forbidden: non-farmer access
        404 Not Found: no pass for this booking
        409 Conflict: pass not available (e.g., booking not confirmed)
    """
    # Verify the booking belongs to the authenticated farmer
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return jsonify({
            "error": "Not Found",
            "message": "No Smart Queue Pass found for this booking.",
            "code": "NOT_FOUND",
        }), 404

    farmer = get_farmer_by_user_id(g.current_user.id)
    if not farmer or booking.farmer_id != farmer.id:
        # Don't disclose that the booking exists but belongs to another farmer
        return jsonify({
            "error": "Not Found",
            "message": "No Smart Queue Pass found for this booking.",
            "code": "NOT_FOUND",
        }), 404

    pass_data = get_pass_for_display(booking_id)
    if pass_data is None:
        return jsonify({
            "error": "Not Found",
            "message": "No Smart Queue Pass found for this booking.",
            "code": "NOT_FOUND",
        }), 404

    return jsonify({"pass_data": pass_data}), 200


@queue_pass_bp.route("/my/<int:booking_id>/view", methods=["GET"])
@login_required
@role_required(UserRole.FARMER)
def view_queue_pass(booking_id: int):
    """Deprecated HTML alias for the Smart Queue Pass page (FARMER only).

    Kept for backwards compatibility with clients that already request this
    path programmatically. It renders the SAME data-free ``queue_pass.html``
    shell as the page route ``/farmer/queue-pass/<booking_id>``: no pass, QR or
    farmer data is embedded server-side, so nothing is disclosed even if a
    caller passes another farmer's booking id - ownership is enforced by
    ``GET /api/queue-pass/my/<booking_id>/display``, which the page calls with
    ``window.KP.authFetch()``.

    Note: the Farmer Dashboard must NOT navigate here directly. Because this
    path lives under the protected ``/api`` prefix it requires a Bearer
    Authorization header, which a plain browser navigation cannot send; the
    dashboard opens ``/farmer/queue-pass/<booking_id>`` instead.

    Returns:
        200 OK: Rendered queue_pass.html shell (booking id only)
        401 Unauthorized: missing/malformed Bearer token (API behaviour is kept)
        403 Forbidden: non-farmer access
    """
    return render_template("queue_pass.html", booking_id=booking_id)


@queue_pass_bp.route("/lookup/<string:pass_id>", methods=["GET"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
@staff_centre_required
def lookup_smart_queue_pass(pass_id: str):
    """Read-only review of a pass before entry verification (STAFF/ADMIN).

    STAFF may only look up passes belonging to their assigned centre.

    Returns:
        200 OK: { smart_queue_pass: { ... } }
        403 Forbidden: staff accessing another centre's pass
        404 Not Found: no pass for this identifier
    """
    try:
        pass_row = get_pass_for_centre(
            pass_id, verification_centre_id=_operating_centre_id()
        )
    except SmartQueuePassError as exc:
        status, label = _error_status_and_label(exc)
        return jsonify({"error": label, "message": exc.message, "code": exc.code}), status

    return jsonify({"smart_queue_pass": _format_queue_pass(pass_row)}), 200


@queue_pass_bp.route("/verify", methods=["POST"])
@login_required
@roles_required(UserRole.STAFF, UserRole.ADMIN)
@staff_centre_required
def verify_smart_queue_pass():
    """Verify a Smart Queue Pass at the mandi gate (STAFF/ADMIN only).

    Request JSON:
        { "pass_id": "kp_pass_..." }

    The booking, farmer and centre are all derived server-side from the secure
    pass identifier - never from client-supplied values. Verification only
    confirms mandi entry; procurement is not started or completed here.

    Returns:
        200 OK: { message, smart_queue_pass }
        400 Bad Request: missing/blank pass_id
        403 Forbidden: farmer, unassigned staff, or another centre's pass
        404 Not Found: no pass for this identifier
        409 Conflict: cancelled/verified pass or ineligible booking
    """
    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid request", "message": "JSON body required."}), 400

    pass_id = data.get("pass_id") or data.get("secure_pass_id")
    if not isinstance(pass_id, str) or not pass_id.strip():
        return jsonify({
            "error": "Validation failed",
            "message": "A non-empty 'pass_id' string is required.",
        }), 400

    verification_centre_id = _operating_centre_id()

    try:
        pass_row = verify_pass(
            pass_id,
            actor_user=g.current_user,
            verification_centre_id=verification_centre_id,
            actor_staff=getattr(g, "current_staff", None),
        )
    except SmartQueuePassError as exc:
        # Audit rejected security-sensitive attempts (cross-centre, replay,
        # cancelled/ineligible passes, unknown identifiers).
        booking_id, pass_centre_id = get_pass_context(pass_id)
        record_verification_failure(
            actor_user=g.current_user,
            code=exc.code,
            message=exc.message,
            attempted_pass_id=pass_id,
            booking_id=booking_id,
            centre_id=verification_centre_id or pass_centre_id,
        )
        status, label = _error_status_and_label(exc)
        return jsonify({"error": label, "message": exc.message, "code": exc.code}), status

    return jsonify({
        "message": (
            "Mandi entry verified. The farmer can now start processing; "
            "procurement is not started by this action."
        ),
        "smart_queue_pass": _format_queue_pass(pass_row),
    }), 200