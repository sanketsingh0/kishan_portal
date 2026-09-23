"""Procurement Slot Booking service layer.

Encapsulates business logic, validations, capacity constraints, duplicate booking checks,
and time-conflict prevention for farmer slot bookings.

A confirmed booking also receives exactly one Smart Queue Pass (SIH 26032 stage 1);
the pass lifecycle is kept in sync with the booking here.
"""

import logging
from datetime import date, datetime, timezone
from sqlalchemy.exc import IntegrityError
from app.extensions import db
from app.models import Booking, BookingStatus, Slot, SlotStatus, Farmer, Centre
from app.services.farmer_service import get_farmer_by_user_id

logger = logging.getLogger(__name__)


class BookingError(Exception):
    """Base exception for booking service errors."""

    def __init__(self, message: str, code: str = "BOOKING_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class BookingValidationError(BookingError):
    """Raised when booking validation fails."""

    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message, code="VALIDATION_ERROR")
        self.errors = errors or [message]


class BookingNotFoundError(BookingError):
    """Raised when a booking is not found or inaccessible."""

    def __init__(self, message: str = "Booking not found."):
        super().__init__(message, code="NOT_FOUND")


class BookingConflictError(BookingError):
    """Raised when capacity, duplicate, or time conflict occurs."""

    def __init__(self, message: str, code: str = "BOOKING_CONFLICT"):
        super().__init__(message, code=code)


LOCATION_MISMATCH_MESSAGE = (
    "Booking not allowed: farmer district/tehsil does not match the centre. "
    "Farmer district or tehsil must match the centre district or tehsil."
)


def normalize_location(value) -> str | None:
    """Normalize one location level for exact comparison.

    Trims surrounding whitespace and lowercases. Returns None for
    missing/empty values so that level simply cannot match.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    cleaned = value.strip().lower()
    return cleaned or None


def is_location_eligible(farmer, centre) -> bool:
    """Return True when farmer tehsil OR district exactly matches centre.

    Exact normalized equality only (no partial/fuzzy matching). If both
    values for a level are missing that level does not match. Booking is
    allowed ONLY when normalized tehsil matches OR normalized district
    matches; when farmer and centre have no usable matching location data
    the booking is rejected (the legacy both-sides-unconfigured allowance
    was removed deliberately).
    """
    farmer_tehsil = normalize_location(getattr(farmer, "tehsil", None))
    farmer_district = normalize_location(getattr(farmer, "district", None))
    centre_tehsil = normalize_location(getattr(centre, "tehsil", None))
    centre_district = normalize_location(getattr(centre, "district", None))
    tehsil_match = bool(
        farmer_tehsil and centre_tehsil and farmer_tehsil == centre_tehsil
    )
    district_match = bool(
        farmer_district and centre_district and farmer_district == centre_district
    )
    return tehsil_match or district_match


def check_location_eligibility(farmer, centre) -> None:
    """Enforce farmer booking location rule; raises on mismatch."""
    if not is_location_eligible(farmer, centre):
        raise BookingValidationError(
            LOCATION_MISMATCH_MESSAGE,
            errors=[LOCATION_MISMATCH_MESSAGE],
        )


def get_active_bookings_count_for_slot(slot_id: int) -> int:
    """Return total active (PENDING or CONFIRMED) bookings for a slot.

    Uses a fresh COUNT query that bypasses the session identity map so a
    capacity change committed by another request/session is always visible.
    """
    from sqlalchemy import func
    count = (
        db.session.query(func.count(Booking.id))
        .filter(
            Booking.slot_id == slot_id,
            Booking.status.in_(BookingStatus.active_statuses),
        )
        .scalar()
    )
    return int(count or 0)


def get_slot_remaining_capacity(slot: Slot) -> int:
    """Calculate remaining capacity for a slot (fresh read, no stale ORM)."""
    fresh_capacity = db.session.query(Slot.capacity).filter(
        Slot.id == slot.id).scalar()
    if fresh_capacity is None:
        return 0
    booked_count = get_active_bookings_count_for_slot(slot.id)
    return max(0, int(fresh_capacity) - booked_count)


def generate_token_for_booking(slot: Slot) -> tuple[str, datetime]:
    """Generate a unique sequential procurement token for a slot's centre + date scope."""
    existing_tokens = (
        db.session.query(Booking.token_number)
        .join(Slot)
        .filter(
            Slot.centre_id == slot.centre_id,
            Slot.slot_date == slot.slot_date,
            Booking.token_number.isnot(None)
        )
        .all()
    )

    numbers = []
    for (token_str,) in existing_tokens:
        if token_str and token_str.startswith("K-"):
            try:
                numbers.append(int(token_str.split("-")[1]))
            except (IndexError, ValueError):
                pass

    next_seq = max(numbers, default=0) + 1
    token_number = f"K-{next_seq:04d}"
    now = datetime.now(timezone.utc)
    return token_number, now


def create_booking(user_id: int, slot_id: int) -> Booking:
    """Create a new slot booking for an authenticated farmer.

    Args:
        user_id: Local user ID of the authenticated farmer.
        slot_id: Slot ID to book.

    Returns:
        Created Booking instance with assigned token.

    Raises:
        BookingValidationError: missing farmer profile or invalid slot state.
        BookingConflictError: slot full, duplicate booking, or time conflict.
    """
    farmer = get_farmer_by_user_id(user_id)
    if not farmer:
        raise BookingValidationError("Farmer profile record not found.")

    if not slot_id or not isinstance(slot_id, int):
        raise BookingValidationError("Valid slot_id is required.")

    # 1. Retrieve slot entity first to determine parent centre_id
    slot_pre = db.session.get(Slot, slot_id)
    if not slot_pre:
        raise BookingValidationError("Slot not found.")

    # 2. Lock parent Centre row with pessimistic lock if supported by DB backend (PostgreSQL/Supabase).
    # Locking Centre row serializes token allocation across all slots belonging to the same centre/date scope.
    # On SQLite (used in test suite), with_for_update() is compiled safely as a no-op / table lock.
    if slot_pre.centre_id:
        db.session.query(Centre).filter(Centre.id == slot_pre.centre_id).with_for_update().first()

    # 3. Retrieve slot with pessimistic row lock
    slot = db.session.query(Slot).filter(Slot.id == slot_id).with_for_update().first()
    if not slot:
        raise BookingValidationError("Slot not found.")

    # 2. Slot status check
    if slot.status != SlotStatus.OPEN:
        raise BookingValidationError("Slot is not open for booking.")

    # 3. Past date check
    if slot.slot_date < date.today():
        raise BookingValidationError("Cannot book slots in the past.")

    # 4. Active Centre check
    if not slot.centre or not slot.centre.is_active:
        raise BookingValidationError("Procurement centre is inactive or unavailable.")

    # 4b. Farmer location eligibility (FARMER bookings only):
    # farmer tehsil == centre tehsil OR farmer district == centre district
    # (normalized exact match). Uses authenticated farmer + slot's centre.
    check_location_eligibility(farmer, slot.centre)

    # 5. Active Crop check
    if not slot.crop or not slot.crop.is_active:
        raise BookingValidationError("Crop is inactive or unavailable.")

    # 6. Capacity check
    active_count = get_active_bookings_count_for_slot(slot.id)
    if active_count >= slot.capacity:
        raise BookingConflictError(
            "Slot is fully booked. No remaining capacity.",
            code="CAPACITY_EXCEEDED"
        )

    # 7. Duplicate booking check (same farmer, same slot)
    existing_duplicate = Booking.query.filter(
        Booking.farmer_id == farmer.id,
        Booking.slot_id == slot.id,
        Booking.status.in_(BookingStatus.active_statuses)
    ).first()
    if existing_duplicate:
        raise BookingConflictError(
            "You already have a booking for this slot.",
            code="DUPLICATE_BOOKING"
        )

    # 8. Time conflict check (overlapping booking for same farmer on same date)
    farmer_active_bookings = (
        Booking.query.join(Slot)
        .filter(
            Booking.farmer_id == farmer.id,
            Slot.slot_date == slot.slot_date,
            Booking.status.in_(BookingStatus.active_statuses)
        )
        .all()
    )

    for b in farmer_active_bookings:
        existing_slot = b.slot
        # Interval overlap logic: new_start < existing_end AND existing_start < new_end
        if slot.start_time < existing_slot.end_time and existing_slot.start_time < slot.end_time:
            raise BookingConflictError(
                "You already have an active booking overlapping with this time slot.",
                code="TIME_CONFLICT"
            )

    token_number, token_now = generate_token_for_booking(slot)

    booking = Booking(
        farmer_id=farmer.id,
        slot_id=slot.id,
        booking_date=datetime.now(timezone.utc),
        status=BookingStatus.CONFIRMED,
        token_number=token_number,
        token_generated_at=token_now,
    )

    try:
        db.session.add(booking)
        db.session.commit()
    except IntegrityError as exc:
        db.session.rollback()
        err_msg = str(exc).lower()
        if "uq_active_booking_farmer_slot" in err_msg or "unique constraint" in err_msg or "unique" in err_msg:
            raise BookingConflictError(
                "You already have a booking for this slot.",
                code="DUPLICATE_BOOKING"
            )
        raise BookingError(f"Database error creating booking: {exc}")
    except Exception as exc:
        db.session.rollback()
        raise BookingError(f"Database error creating booking: {exc}")

    # Emit realtime queue update post-commit
    try:
        from app.queue.events import emit_queue_update
        from app.services.notification_service import create_notification
        from app.models import NotificationType

        if slot and slot.centre_id and slot.slot_date:
            emit_queue_update(
                centre_id=slot.centre_id,
                slot_date=slot.slot_date,
                booking_id=booking.id,
                reason="BOOKING_CREATED"
            )

        create_notification(
            user_id=farmer.user_id,
            notification_type=NotificationType.BOOKING_CONFIRMED,
            title="Booking Confirmed",
            message=f"Your procurement booking has been confirmed. Token: {token_number}.",
            booking_id=booking.id,
        )
    except Exception:
        pass

    # --- Smart Queue Pass (SIH 26032 stage 1) -----------------------------------
    # Every confirmed booking gets exactly one secure digital mandi entry pass.
    # Created AFTER the booking transaction committed and isolated from it, so a
    # pass problem can never block or roll back a booking; creation is idempotent
    # and never produces a second pass for the same booking.
    _create_smart_queue_pass(booking)

    return booking


def _create_smart_queue_pass(booking: Booking) -> None:
    """Best-effort creation of the booking's Smart Queue Pass (never raises)."""
    try:
        from app.services.smart_queue_pass_service import create_pass_for_booking

        create_pass_for_booking(booking)
    except Exception as exc:
        logger.warning(
            "Smart Queue Pass creation failed for booking %s: %s", booking.id, exc
        )


def get_farmer_bookings(user_id: int, status: str | None = None) -> list[Booking]:
    """Retrieve all bookings for a farmer with optional status filter."""
    farmer = get_farmer_by_user_id(user_id)
    if not farmer:
        return []

    query = Booking.query.filter(Booking.farmer_id == farmer.id)
    if status:
        query = query.filter(Booking.status == status.upper().strip())

    return query.order_by(Booking.created_at.desc()).all()


def get_booking_by_id(booking_id: int, user_id: int | None = None, is_staff_or_admin: bool = False) -> Booking | None:
    """Retrieve a booking by ID with ownership verification."""
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return None

    if not is_staff_or_admin:
        if not user_id:
            return None
        farmer = get_farmer_by_user_id(user_id)
        if not farmer or booking.farmer_id != farmer.id:
            return None

    return booking


def cancel_booking(booking_id: int, user_id: int, is_staff_or_admin: bool = False) -> Booking:
    """Cancel an active booking for a farmer."""
    booking = get_booking_by_id(booking_id, user_id=user_id, is_staff_or_admin=is_staff_or_admin)
    if not booking:
        raise BookingNotFoundError("Booking not found or access denied.")

    if booking.status == BookingStatus.CANCELLED:
        raise BookingValidationError("Booking is already cancelled.")

    if booking.status in (BookingStatus.COMPLETED, BookingStatus.NO_SHOW):
        raise BookingValidationError("Completed or no-show bookings cannot be cancelled.")

    booking.status = BookingStatus.CANCELLED
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise BookingError(f"Database error cancelling booking: {exc}")

    # Emit realtime queue update post-commit
    try:
        from app.queue.events import emit_queue_update
        from app.services.notification_service import create_notification
        from app.models import NotificationType

        if booking.slot and booking.slot.centre_id and booking.slot.slot_date:
            emit_queue_update(
                centre_id=booking.slot.centre_id,
                slot_date=booking.slot.slot_date,
                booking_id=booking.id,
                reason="BOOKING_CANCELLED"
            )

        if booking.farmer and booking.farmer.user_id:
            create_notification(
                user_id=booking.farmer.user_id,
                notification_type=NotificationType.BOOKING_CANCELLED,
                title="Booking Cancelled",
                message=f"Your booking {booking.token_number or ''} has been cancelled.",
                booking_id=booking.id,
            )
    except Exception:
        pass

    # --- Smart Queue Pass (SIH 26032 stage 1) -----------------------------------
    # An ACTIVE pass is cancelled together with its booking. Runs after the
    # existing cancellation commit and is fully isolated, so existing
    # cancellation / capacity-release behaviour is never affected. A pass that
    # cannot be cancelled stays rejected at verification time anyway, because
    # booking eligibility is validated server-side.
    try:
        from app.services.smart_queue_pass_service import cancel_pass_for_booking

        cancel_pass_for_booking(booking)
    except Exception as exc:
        logger.warning(
            "Smart Queue Pass cancellation failed for booking %s: %s", booking.id, exc
        )

    return booking
