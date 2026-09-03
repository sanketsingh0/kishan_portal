"""Delay service layer.

Handles business logic and database operations for procurement delay management.
"""

from datetime import datetime, date
from app.extensions import db
from app.models import Centre, Slot, Delay, DelayStatus
from app.queue.events import emit_delay_update


class DelayError(Exception):
    """Base exception for delay operations."""

    def __init__(self, message="Delay operation failed"):
        self.message = message
        super().__init__(self.message)


class DelayNotFoundError(DelayError):
    """Raised when a requested delay record is not found."""

    def __init__(self, message="Delay record not found"):
        super().__init__(message)


class DelayValidationError(DelayError):
    """Raised when validation of delay fields fails."""

    def __init__(self, errors):
        self.errors = errors
        message = "; ".join(errors) if isinstance(errors, list) else str(errors)
        super().__init__(message)


def parse_date_value(val):
    """Parse date string (YYYY-MM-DD) or date object."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d").date()
        except ValueError:
            raise DelayValidationError(["Invalid delay_date format. Expected YYYY-MM-DD."])
    raise DelayValidationError(["Invalid delay_date type."])


def get_delay_by_id(delay_id: int) -> Delay | None:
    """Retrieve delay by primary key."""
    return db.session.get(Delay, delay_id)


def get_delays(
    centre_id: int | None = None,
    slot_id: int | None = None,
    delay_date=None,
    status: str | None = None,
) -> list[Delay]:
    """Retrieve delays with optional filters."""
    query = Delay.query

    if centre_id is not None:
        query = query.filter(Delay.centre_id == centre_id)

    if slot_id is not None:
        query = query.filter(Delay.slot_id == slot_id)

    if delay_date is not None:
        parsed_date = parse_date_value(delay_date)
        if parsed_date:
            query = query.filter(Delay.delay_date == parsed_date)

    if status is not None:
        query = query.filter(Delay.status == status)

    return query.order_by(Delay.created_at.desc()).all()


def get_active_delays_for_scope(centre_id: int, delay_date: date, slot_id: int | None = None) -> list[Delay]:
    """Retrieve ACTIVE delays affecting a specific centre, date, and optional slot."""
    query = Delay.query.filter(
        Delay.centre_id == centre_id,
        Delay.delay_date == delay_date,
        Delay.status == DelayStatus.ACTIVE,
    )

    if slot_id is not None:
        query = query.filter((Delay.slot_id == None) | (Delay.slot_id == slot_id))
    else:
        query = query.filter(Delay.slot_id == None)

    return query.all()


def calculate_active_delay_minutes(centre_id: int, delay_date: date, slot_id: int | None = None) -> int:
    """Calculate total active delay minutes for a given centre, date, and optional slot."""
    active_delays = get_active_delays_for_scope(centre_id, delay_date, slot_id)
    return sum(d.delay_minutes for d in active_delays)


def _notify_affected_farmers_for_delay(centre_id: int, delay_date, slot_id: int | None = None):
    """Notify farmers with active bookings affected by a procurement delay."""
    try:
        from app.models import Booking, BookingStatus, Slot
        from app.services.notification_service import create_notification
        from app.models import NotificationType

        query = Booking.query.join(Slot).filter(
            Slot.centre_id == centre_id,
            Slot.slot_date == delay_date,
            Booking.status.in_(BookingStatus.active_statuses),
        )
        if slot_id is not None:
            query = query.filter(Slot.id == slot_id)

        affected_bookings = query.all()
        notified_users = set()

        for b in affected_bookings:
            if b.farmer and b.farmer.user_id and b.farmer.user_id not in notified_users:
                notified_users.add(b.farmer.user_id)
                create_notification(
                    user_id=b.farmer.user_id,
                    notification_type=NotificationType.DELAY_UPDATE,
                    title="Procurement Delay Updated",
                    message="A delay has affected today's procurement schedule. Your estimated wait time has been updated.",
                    booking_id=b.id,
                )
    except Exception:
        pass


def create_delay(data: dict, current_user_id: int) -> Delay:
    """Create a new delay record (STAFF/ADMIN)."""
    if not isinstance(data, dict):
        raise DelayValidationError(["Request body must be a JSON object."])

    errors = []

    # Centre validation
    centre_id = data.get("centre_id")
    if not centre_id:
        errors.append("centre_id is required.")
    else:
        try:
            centre_id = int(centre_id)
            centre = db.session.get(Centre, centre_id)
            if not centre:
                errors.append(f"Centre {centre_id} not found.")
        except (ValueError, TypeError):
            errors.append("centre_id must be a valid integer.")
            centre = None

    # Date validation
    delay_date_raw = data.get("delay_date")
    delay_date = None
    if not delay_date_raw:
        errors.append("delay_date is required.")
    else:
        try:
            delay_date = parse_date_value(delay_date_raw)
        except DelayValidationError as dve:
            errors.extend(dve.errors)

    # Slot validation (optional)
    slot_id = data.get("slot_id")
    slot = None
    if slot_id is not None and slot_id != "":
        try:
            slot_id = int(slot_id)
            slot = db.session.get(Slot, slot_id)
            if not slot:
                errors.append(f"Slot {slot_id} not found.")
            elif centre_id and slot.centre_id != centre_id:
                errors.append(f"Slot {slot_id} does not belong to centre {centre_id}.")
        except (ValueError, TypeError):
            errors.append("slot_id must be a valid integer.")
            slot_id = None
    else:
        slot_id = None

    # Delay minutes validation
    delay_minutes = data.get("delay_minutes")
    if delay_minutes is None:
        errors.append("delay_minutes is required.")
    else:
        if isinstance(delay_minutes, bool) or not isinstance(delay_minutes, (int, float)):
            errors.append("delay_minutes must be a valid integer.")
        else:
            try:
                # Check for floating point inputs (e.g. 15.5)
                val_float = float(delay_minutes)
                if val_float != int(val_float):
                    errors.append("delay_minutes must be an integer.")
                else:
                    delay_minutes = int(val_float)
                    if delay_minutes <= 0:
                        errors.append("delay_minutes must be an integer > 0.")
                    elif delay_minutes > 1440:
                        errors.append("delay_minutes cannot exceed 1440 (24 hours).")
            except (ValueError, TypeError):
                errors.append("delay_minutes must be a valid integer.")

    # Status validation
    status = data.get("status", DelayStatus.ACTIVE)
    if status not in DelayStatus.choices:
        errors.append(f"Invalid status '{status}'. Allowed choices: {', '.join(DelayStatus.choices)}.")

    # Reason validation
    reason = data.get("reason")
    if reason is not None:
        if not isinstance(reason, str) or len(reason) > 500:
            errors.append("reason must be a string up to 500 characters.")
        else:
            reason = reason.strip()

    if errors:
        raise DelayValidationError(errors)

    delay = Delay(
        centre_id=centre_id,
        slot_id=slot_id,
        delay_date=delay_date,
        delay_minutes=delay_minutes,
        reason=reason,
        status=status,
        created_by=current_user_id,
    )

    try:
        db.session.add(delay)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise DelayError(f"Database error while creating delay: {exc}")

    # Emit Socket.IO event post-commit
    emit_delay_update(centre_id, delay_date, reason="DELAY_CREATED")
    _notify_affected_farmers_for_delay(centre_id, delay_date, slot_id)

    return delay


def update_delay(delay_id: int, data: dict) -> Delay:
    """Update delay attributes (STAFF/ADMIN)."""
    if not isinstance(data, dict):
        raise DelayValidationError(["Request body must be a JSON object."])

    delay = db.session.get(Delay, delay_id)
    if not delay:
        raise DelayNotFoundError(f"Delay {delay_id} not found.")

    errors = []

    if "delay_minutes" in data:
        dm = data["delay_minutes"]
        if dm is None or isinstance(dm, bool) or not isinstance(dm, (int, float)):
            errors.append("delay_minutes must be a valid integer.")
        else:
            try:
                val_float = float(dm)
                if val_float != int(val_float):
                    errors.append("delay_minutes must be an integer.")
                else:
                    dm_int = int(val_float)
                    if dm_int <= 0:
                        errors.append("delay_minutes must be an integer > 0.")
                    elif dm_int > 1440:
                        errors.append("delay_minutes cannot exceed 1440 (24 hours).")
                    else:
                        delay.delay_minutes = dm_int
            except (ValueError, TypeError):
                errors.append("delay_minutes must be a valid integer.")

    if "status" in data:
        status = data["status"]
        if status not in DelayStatus.choices:
            errors.append(f"Invalid status '{status}'. Allowed choices: {', '.join(DelayStatus.choices)}.")
        else:
            delay.status = status

    if "reason" in data:
        reason = data["reason"]
        if reason is not None:
            if not isinstance(reason, str) or len(reason) > 500:
                errors.append("reason must be a string up to 500 characters.")
            else:
                delay.reason = reason.strip()
        else:
            delay.reason = None

    if errors:
        raise DelayValidationError(errors)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise DelayError(f"Database error while updating delay: {exc}")

    # Emit Socket.IO event post-commit
    emit_delay_update(delay.centre_id, delay.delay_date, reason="DELAY_UPDATED")
    _notify_affected_farmers_for_delay(delay.centre_id, delay.delay_date, delay.slot_id)

    return delay


def cancel_delay(delay_id: int) -> Delay:
    """Soft-cancel a delay by setting status = CANCELLED (STAFF/ADMIN)."""
    delay = db.session.get(Delay, delay_id)
    if not delay:
        raise DelayNotFoundError(f"Delay {delay_id} not found.")

    delay.status = DelayStatus.CANCELLED

    return delay
