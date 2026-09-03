"""Procurement Slot Booking service layer.

Encapsulates business logic, validations, capacity constraints, duplicate booking checks,
and time-conflict prevention for farmer slot bookings.
"""

from datetime import date, datetime, timezone
from app.extensions import db
from app.models import Booking, BookingStatus, Slot, SlotStatus, Farmer, Centre
from app.services.farmer_service import get_farmer_by_user_id


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


def get_active_bookings_count_for_slot(slot_id: int) -> int:
    """Return total active (PENDING or CONFIRMED) bookings for a given slot."""
    return Booking.query.filter(
        Booking.slot_id == slot_id,
        Booking.status.in_(BookingStatus.active_statuses)
    ).count()


def get_slot_remaining_capacity(slot: Slot) -> int:
    """Calculate remaining capacity for a slot."""
    booked_count = get_active_bookings_count_for_slot(slot.id)
    return max(0, slot.capacity - booked_count)


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

    return booking


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

    return booking
