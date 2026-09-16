"""Smart Queue Pass service layer (SIH 26032 - Stage 1 backend foundation).

Business logic for the secure digital mandi entry pass:

* creation of exactly one pass per booking (idempotent),
* lifecycle transitions ``ACTIVE -> VERIFIED`` / ``ACTIVE -> CANCELLED``,
* full server-side validation of every entry verification request,
* audit logging through the existing AuditLog infrastructure.

Entry verification only confirms mandi entry - it never starts or completes
procurement. QR image generation, PDF export and the scanner UI are Stage 2.
"""

import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    Booking,
    BookingStatus,
    ProcurementStatus,
    SmartQueuePass,
    SmartQueuePassStatus,
    UserRole,
)

logger = logging.getLogger(__name__)

# Self-describing prefix - it reveals no internal identifier.
PASS_ID_PREFIX = "kp_pass_"
# 32 random bytes -> ~43 URL-safe characters (~256 bits of entropy).
PASS_ID_TOKEN_BYTES = 32
# Collision retry budget (a collision is statistically impossible).
PASS_ID_MAX_ATTEMPTS = 5


class SmartQueuePassError(Exception):
    """Base exception for Smart Queue Pass operations."""

    def __init__(self, message: str, code: str = "SMART_QUEUE_PASS_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class SmartQueuePassNotFoundError(SmartQueuePassError):
    """Raised when a pass (or a record it depends on) does not exist."""

    def __init__(self, message="Smart Queue Pass not found."):
        super().__init__(message, code="NOT_FOUND")


class SmartQueuePassValidationError(SmartQueuePassError):
    """Raised when the requested pass identifier is missing or malformed."""

    def __init__(self, message="Invalid Smart Queue Pass request."):
        super().__init__(message, code="VALIDATION_ERROR")


class SmartQueuePassConflictError(SmartQueuePassError):
    """Raised when a pass/booking is not eligible for entry verification."""

    def __init__(self, message="Smart Queue Pass is not eligible for verification."):
        super().__init__(message, code="PASS_CONFLICT")


class SmartQueuePassForbiddenError(SmartQueuePassError):
    """Raised when the operating centre does not own the pass."""

    def __init__(self, message="Access denied for this centre."):
        super().__init__(message, code="FORBIDDEN")


def generate_secure_pass_id() -> str:
    """Generate a cryptographically secure, non-sequential pass identifier.

    Built from ``secrets.token_urlsafe`` so it is unpredictable, unique in
    practice and safe to expose as a QR payload. It contains no farmer ID,
    booking ID, token number, phone number, bank detail or JWT.
    """
    return f"{PASS_ID_PREFIX}{secrets.token_urlsafe(PASS_ID_TOKEN_BYTES)}"


def get_pass_by_booking_id(booking_id: int | None) -> SmartQueuePass | None:
    """Retrieve the Smart Queue Pass belonging to a booking (or None)."""
    if booking_id is None:
        return None
    return SmartQueuePass.query.filter(
        SmartQueuePass.booking_id == booking_id
    ).first()


def get_pass_by_secure_id(secure_pass_id: str | None) -> SmartQueuePass | None:
    """Retrieve a pass by its secure (QR-safe) identifier (or None)."""
    if not isinstance(secure_pass_id, str):
        return None
    cleaned = secure_pass_id.strip()
    if not cleaned:
        return None
    return SmartQueuePass.query.filter(
        SmartQueuePass.secure_pass_id == cleaned
    ).first()


def get_booking_centre_id(booking: Booking | None) -> int | None:
    """Derive the operating centre of a booking server-side.

    The centre is always resolved from the booking -> slot chain; a centre id
    supplied by a client is never trusted.
    """
    if booking is None or booking.slot is None:
        return None
    return booking.slot.centre_id


def _generate_unique_pass_id() -> str:
    """Generate a pass identifier that is not yet present in the database."""
    for _ in range(PASS_ID_MAX_ATTEMPTS):
        candidate = generate_secure_pass_id()
        if get_pass_by_secure_id(candidate) is None:
            return candidate
    raise SmartQueuePassConflictError(
        "Could not generate a unique Smart Queue Pass identifier."
    )


def create_pass_for_booking(booking: Booking, commit: bool = True) -> SmartQueuePass:
    """Create (or return) the single Smart Queue Pass of a booking.

    Idempotent: if the booking already has a pass it is returned untouched, so
    a booking can never accumulate a second pass. The initial status is ACTIVE.

    Args:
        booking: A persisted Booking instance.
        commit: When False the caller owns the transaction (the pass is only
            flushed) so booking + pass can be committed atomically.
    """
    if booking is None or not isinstance(booking, Booking):
        raise SmartQueuePassValidationError(
            "A persisted booking is required to create a Smart Queue Pass."
        )

    booking_id = booking.id
    if booking_id is None:
        raise SmartQueuePassValidationError(
            "The booking must be persisted before its Smart Queue Pass is created."
        )

    existing = get_pass_by_booking_id(booking_id)
    if existing is not None:
        return existing

    pass_row = SmartQueuePass(
        booking_id=booking_id,
        secure_pass_id=_generate_unique_pass_id(),
        status=SmartQueuePassStatus.ACTIVE,
    )
    db.session.add(pass_row)

    if not commit:
        # Caller owns the transaction; failures propagate to its error handling.
        db.session.flush()
        return pass_row

    try:
        db.session.commit()
    except IntegrityError as exc:
        # A concurrent request created the pass first - reuse that one.
        db.session.rollback()
        existing = get_pass_by_booking_id(booking_id)
        if existing is not None:
            return existing
        raise SmartQueuePassConflictError(
            f"Could not create Smart Queue Pass for booking {booking_id}: {exc}"
        )
    except Exception as exc:
        db.session.rollback()
        raise SmartQueuePassError(
            f"Database error creating Smart Queue Pass: {exc}"
        )

    return pass_row


def get_or_create_pass_for_booking(
    booking: Booking | None, commit: bool = True
) -> SmartQueuePass | None:
    """Return the pass of a confirmed booking, creating a missing one lazily.

    Bookings that were created before this feature existed (or that were
    inserted directly, e.g. demo/seed data) are back-filled on first read
    instead of being rewritten by a bulk data migration. Non-confirmed
    bookings never get a pass.
    """
    if booking is None:
        return None

    existing = get_pass_by_booking_id(booking.id)
    if existing is not None:
        return existing

    if booking.status != BookingStatus.CONFIRMED:
        return None

    return create_pass_for_booking(booking, commit=commit)


def cancel_pass_for_booking(
    booking: Booking | int | None, commit: bool = True
) -> SmartQueuePass | None:
    """Cancel the ACTIVE pass of a cancelled booking.

    Never creates a pass. A VERIFIED pass is deliberately left untouched: mandi
    entry already happened and stays part of the audit trail.
    """
    booking_id = booking.id if isinstance(booking, Booking) else booking
    pass_row = get_pass_by_booking_id(booking_id)
    if pass_row is None or pass_row.status != SmartQueuePassStatus.ACTIVE:
        return pass_row

    pass_row.status = SmartQueuePassStatus.CANCELLED
    try:
        if commit:
            db.session.commit()
        else:
            db.session.flush()
    except Exception as exc:
        db.session.rollback()
        raise SmartQueuePassError(
            f"Database error cancelling Smart Queue Pass: {exc}"
        )

    _log_pass_event(
        action="CANCEL_SMART_QUEUE_PASS",
        pass_row=pass_row,
        description=(
            f"Cancelled Smart Queue Pass for booking #{pass_row.booking_id} "
            f"because the booking was cancelled."
        ),
        metadata={
            "booking_id": pass_row.booking_id,
            "result": SmartQueuePassStatus.CANCELLED,
        },
    )
    return pass_row


def validate_pass(
    secure_pass_id: str | None, verification_centre_id: int | None = None
) -> SmartQueuePass:
    """Server-side validation of a pass for mandi entry verification.

    Every rule is enforced here (never in the frontend):

    1. the pass exists, 2. its booking exists, 3. its farmer exists,
    4. the booking is still eligible for entry, 5. the pass is not CANCELLED,
    6. the pass is not already VERIFIED, 7. the booking is not COMPLETED,
    8. the booking is not rejected/no-show, 9. the centre exists,
    10. the operating centre matches the booking centre (403),
    11. an existing procurement date matches the scheduled slot date,
    12. the pass belongs to the requested/operating centre.

    Returns the unmodified pass. Raises a SmartQueuePassError subclass which the
    route layer maps to 400/403/404/409/500.
    """
    if not isinstance(secure_pass_id, str) or not secure_pass_id.strip():
        raise SmartQueuePassValidationError("A non-empty pass_id is required.")

    pass_row = get_pass_by_secure_id(secure_pass_id)
    if pass_row is None:
        raise SmartQueuePassNotFoundError("Smart Queue Pass not found.")

    booking = pass_row.booking
    if booking is None:
        raise SmartQueuePassNotFoundError(
            "The booking linked to this Smart Queue Pass no longer exists."
        )
    if booking.farmer is None:
        raise SmartQueuePassConflictError(
            "The farmer linked to this booking no longer exists."
        )

    if pass_row.status == SmartQueuePassStatus.CANCELLED:
        raise SmartQueuePassConflictError(
            "This Smart Queue Pass has been cancelled and cannot be verified."
        )
    if pass_row.status == SmartQueuePassStatus.VERIFIED:
        raise SmartQueuePassConflictError(
            "This Smart Queue Pass has already been verified."
        )
    if pass_row.status != SmartQueuePassStatus.ACTIVE:
        raise SmartQueuePassConflictError(
            f"Smart Queue Pass status '{pass_row.status}' cannot be verified."
        )

    # Completed / rejected / cancelled / no-show bookings are closed for entry.
    if booking.status not in BookingStatus.active_statuses:
        raise SmartQueuePassConflictError(
            f"Booking #{booking.id} is {booking.status} and is no longer eligible "
            "for mandi entry verification."
        )

    procurement = booking.procurement
    if procurement is not None and procurement.procurement_status in (
        ProcurementStatus.COMPLETED,
        ProcurementStatus.REJECTED,
    ):
        raise SmartQueuePassConflictError(
            f"Procurement for booking #{booking.id} is "
            f"{procurement.procurement_status}; entry verification is closed."
        )

    slot = booking.slot
    booking_centre_id = get_booking_centre_id(booking)
    if booking_centre_id is None or slot is None or slot.centre is None:
        raise SmartQueuePassConflictError(
            "The procurement centre linked to this booking no longer exists."
        )

    # Rule 11: a recorded procurement date must match the scheduled queue date.
    if (
        procurement is not None
        and procurement.procurement_date is not None
        and slot.slot_date is not None
        and procurement.procurement_date != slot.slot_date
    ):
        raise SmartQueuePassConflictError(
            "The recorded procurement date does not match the scheduled slot date "
            "for this pass."
        )

    # Rules 10 & 12: the operating centre must own the pass.
    if verification_centre_id is not None and verification_centre_id != booking_centre_id:
        raise SmartQueuePassForbiddenError("Access denied for this centre.")

    return pass_row


def get_pass_for_centre(
    secure_pass_id: str | None, verification_centre_id: int | None = None
) -> SmartQueuePass:
    """Read-only pass lookup for STAFF/ADMIN with centre isolation applied.

    Unlike validate_pass() this returns CANCELLED/VERIFIED passes too, so staff
    can see why a pass cannot be accepted without mutating anything.
    """
    if not isinstance(secure_pass_id, str) or not secure_pass_id.strip():
        raise SmartQueuePassValidationError("A non-empty pass_id is required.")

    pass_row = get_pass_by_secure_id(secure_pass_id)
    if pass_row is None:
        raise SmartQueuePassNotFoundError("Smart Queue Pass not found.")

    booking_centre_id = get_booking_centre_id(pass_row.booking)
    if booking_centre_id is None:
        raise SmartQueuePassNotFoundError(
            "The booking linked to this Smart Queue Pass is no longer available."
        )

    if verification_centre_id is not None and verification_centre_id != booking_centre_id:
        raise SmartQueuePassForbiddenError("Access denied for this centre.")

    return pass_row


def get_pass_context(secure_pass_id) -> tuple[int | None, int | None]:
    """Best-effort (booking_id, centre_id) used for audit context. Never raises."""
    try:
        pass_row = get_pass_by_secure_id(secure_pass_id)
        if pass_row is None:
            return None, None
        return pass_row.booking_id, get_booking_centre_id(pass_row.booking)
    except Exception:
        return None, None


def verify_pass(
    secure_pass_id: str | None,
    actor_user,
    verification_centre_id: int | None = None,
    actor_staff=None,
) -> SmartQueuePass:
    """Verify a Smart Queue Pass at the mandi gate (STAFF/ADMIN only).

    On success the pass becomes VERIFIED with ``verified_at``, ``verified_by``
    and ``verification_centre_id`` recorded. This ONLY confirms mandi entry - no
    procurement (or payment) work is started or completed here.

    STAFF are always pinned to their assigned centre (the centre recorded on the
    pass is derived server-side, never taken from the client). ADMIN may verify
    system-wide and the booking's own centre is recorded.
    """
    if actor_user is None:
        raise SmartQueuePassForbiddenError("Authentication required.")

    role = getattr(actor_user, "role", None)
    if role not in (UserRole.STAFF, UserRole.ADMIN):
        raise SmartQueuePassForbiddenError(
            "Only STAFF or ADMIN users can verify a Smart Queue Pass."
        )

    if role == UserRole.STAFF:
        if actor_staff is None:
            raise SmartQueuePassForbiddenError(
                "No staff profile found for this account."
            )
        if actor_staff.centre_id is None:
            raise SmartQueuePassForbiddenError(
                "No procurement centre has been assigned to your account. "
                "Please contact the administrator."
            )
        # The operating centre always comes from the server-side staff profile.
        verification_centre_id = actor_staff.centre_id

    pass_row = validate_pass(
        secure_pass_id, verification_centre_id=verification_centre_id
    )

    if verification_centre_id is None:
        # ADMIN operating system-wide: record the booking's own centre.
        verification_centre_id = get_booking_centre_id(pass_row.booking)

    pass_row.status = SmartQueuePassStatus.VERIFIED
    pass_row.verified_at = datetime.now(timezone.utc)
    pass_row.verified_by = getattr(actor_user, "id", None)
    pass_row.verification_centre_id = verification_centre_id

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise SmartQueuePassError(
            f"Database error while verifying Smart Queue Pass: {exc}"
        )

    _log_pass_event(
        action="VERIFY_SMART_QUEUE_PASS",
        pass_row=pass_row,
        description=(
            f"Verified Smart Queue Pass for booking #{pass_row.booking_id} at "
            f"centre #{pass_row.verification_centre_id} (mandi entry confirmed)."
        ),
        metadata={
            "booking_id": pass_row.booking_id,
            "centre_id": pass_row.verification_centre_id,
            "result": SmartQueuePassStatus.VERIFIED,
            "actor_role": role,
        },
        user_id=getattr(actor_user, "id", None),
    )
    return pass_row


def _log_pass_event(
    action: str,
    pass_row: SmartQueuePass,
    description: str,
    metadata: dict | None = None,
    user_id: int | None = None,
) -> None:
    """Write a Smart Queue Pass audit entry through the existing audit service.

    Never raises: audit failures must not break the business transaction.
    """
    try:
        from app.services.audit_service import create_audit_log

        create_audit_log(
            action=action,
            entity_type="SMART_QUEUE_PASS",
            entity_id=pass_row.id,
            description=description,
            metadata=metadata,
            user_id=user_id,
        )
    except Exception as exc:
        logger.warning(
            "Failed to write audit log '%s' for Smart Queue Pass %s: %s",
            action,
            pass_row.id,
            exc,
        )


def record_verification_failure(
    actor_user,
    code: str,
    message: str,
    attempted_pass_id=None,
    booking_id: int | None = None,
    centre_id: int | None = None,
) -> None:
    """Audit a rejected entry-verification attempt (best-effort, never raises).

    Only non-sensitive context is stored: no phone numbers, bank details, JWTs
    or passwords. The attempted pass identifier is itself a non-secret QR
    payload, so it is kept (truncated) to make brute-force probing visible.
    """
    metadata = {
        "result": "REJECTED",
        "reason_code": code,
        "reason": message,
        "actor_role": getattr(actor_user, "role", None),
    }
    if booking_id is not None:
        metadata["booking_id"] = booking_id
    if centre_id is not None:
        metadata["centre_id"] = centre_id
    if attempted_pass_id:
        metadata["attempted_pass_id"] = str(attempted_pass_id)[:80]

    try:
        from app.services.audit_service import create_audit_log

        create_audit_log(
            action="FAILED_SMART_QUEUE_PASS_VERIFICATION",
            entity_type="SMART_QUEUE_PASS",
            entity_id=booking_id,
            description=f"Rejected Smart Queue Pass verification attempt ({code}): {message}",
            metadata=metadata,
            user_id=getattr(actor_user, "id", None),
        )
    except Exception as exc:
        logger.warning("Failed to audit rejected Smart Queue Pass verification: %s", exc)