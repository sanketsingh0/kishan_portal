"""Procurement Slot service layer.

Encapsulates business logic, data validation, interval-overlap checks, and capacity
constraints for procurement slots:
- Active Centre & Crop existence verification
- Operating hours and date bounds checking (no past dates)
- Time interval overlap detection for same centre/crop/date
- Centre daily capacity constraint enforcement
- Slot creation, update, retrieval, and soft cancellation
"""

from datetime import date, time, datetime
from sqlalchemy import or_

from app.extensions import db
from app.models import Slot, SlotStatus, Centre, Crop


class SlotError(Exception):
    """Base exception for slot service errors."""

    def __init__(self, message: str, code: str = "SLOT_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class SlotValidationError(SlotError):
    """Raised when slot validation fails."""

    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message, code="VALIDATION_ERROR")
        self.errors = errors or [message]


class DuplicateSlotError(SlotError):
    """Raised when an exact duplicate slot exists."""

    def __init__(self, message: str = "A slot for this centre, crop, date, and exact time window already exists."):
        super().__init__(message, code="DUPLICATE_SLOT")


class SlotOverlapError(SlotError):
    """Raised when a slot overlaps with an existing slot."""

    def __init__(self, message: str = "Slot overlaps with an existing slot for this centre, crop, and date."):
        super().__init__(message, code="SLOT_OVERLAP")


class DailyCapacityExceededError(SlotError):
    """Raised when total slot capacity exceeds the centre's daily limit."""

    def __init__(self, message: str):
        super().__init__(message, code="DAILY_CAPACITY_EXCEEDED")


def parse_date_string(val) -> date | None:
    """Parse date string (e.g. '2026-09-10') into datetime.date."""
    if isinstance(val, date):
        return val
    if not val or not isinstance(val, str):
        return None
    val = val.strip()
    try:
        return datetime.strptime(val, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse_time_string(val) -> time | None:
    """Parse time string (e.g. '09:00', '09:00:00') into datetime.time."""
    if isinstance(val, time):
        return val
    if not val or not isinstance(val, str):
        return None
    val = val.strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(val, fmt).time()
        except ValueError:
            pass
    return None


def format_date_string(d: date | None) -> str | None:
    """Format datetime.date into 'YYYY-MM-DD' string."""
    if d is None:
        return None
    return d.strftime("%Y-%m-%d")


def format_time_string(t: time | None) -> str | None:
    """Format datetime.time into 'HH:MM' string."""
    if t is None:
        return None
    return t.strftime("%H:%M")


def check_slot_overlap(
    centre_id: int,
    crop_id: int,
    slot_date: date,
    start_time: time,
    end_time: time,
    exclude_slot_id: int | None = None,
):
    """Check if the time window [start_time, end_time] overlaps with existing slots.

    Overlaps if: (new_start < existing_end) and (existing_start < new_end)
    Excludes CANCELLED slots and optionally current slot_id.

    Raises:
        DuplicateSlotError: if exact same time window already exists.
        SlotOverlapError: if time window overlaps with an existing slot.
    """
    query = Slot.query.filter(
        Slot.centre_id == centre_id,
        Slot.crop_id == crop_id,
        Slot.slot_date == slot_date,
        Slot.status != SlotStatus.CANCELLED,
    )
    if exclude_slot_id:
        query = query.filter(Slot.id != exclude_slot_id)

    existing_slots = query.all()

    for s in existing_slots:
        # Check exact duplicate
        if s.start_time == start_time and s.end_time == end_time:
            raise DuplicateSlotError()

        # Check interval overlap: start1 < end2 AND start2 < end1
        if start_time < s.end_time and s.start_time < end_time:
            raise SlotOverlapError()


def check_daily_capacity(
    centre_id: int,
    slot_date: date,
    capacity: int,
    centre_daily_capacity: int,
    exclude_slot_id: int | None = None,
):
    """Ensure total capacity of non-cancelled slots for centre on slot_date does not exceed daily limit.

    Raises:
        DailyCapacityExceededError: if total capacity exceeds limit.
    """
    query = Slot.query.filter(
        Slot.centre_id == centre_id,
        Slot.slot_date == slot_date,
        Slot.status != SlotStatus.CANCELLED,
    )
    if exclude_slot_id:
        query = query.filter(Slot.id != exclude_slot_id)

    existing_slots = query.all()
    current_total = sum(s.capacity for s in existing_slots)

    if current_total + capacity > centre_daily_capacity:
        raise DailyCapacityExceededError(
            f"Total slot capacity for centre on {slot_date} would exceed daily limit of {centre_daily_capacity} "
            f"(Current total: {current_total}, Requested: {capacity}, Maximum allowed: {centre_daily_capacity})."
        )


def get_slots(
    centre_id: int | None = None,
    crop_id: int | None = None,
    slot_date: date | str | None = None,
    status: str | None = None,
    upcoming_only: bool = False,
) -> list[Slot]:
    """Query slots with optional filters.

    Args:
        centre_id: Filter by centre ID.
        crop_id: Filter by crop ID.
        slot_date: Filter by date.
        status: Filter by slot status (e.g. 'OPEN').
        upcoming_only: If True, only returns slots with date >= today and status == 'OPEN'.

    Returns:
        List of Slot instances.
    """
    query = Slot.query

    if centre_id is not None:
        query = query.filter(Slot.centre_id == centre_id)

    if crop_id is not None:
        query = query.filter(Slot.crop_id == crop_id)

    if slot_date is not None:
        parsed_d = parse_date_string(slot_date) if isinstance(slot_date, str) else slot_date
        if parsed_d:
            query = query.filter(Slot.slot_date == parsed_d)

    if status:
        query = query.filter(Slot.status == status.upper())

    if upcoming_only:
        today = date.today()
        query = query.filter(Slot.slot_date >= today, Slot.status == SlotStatus.OPEN)

    return query.order_by(Slot.slot_date.asc(), Slot.start_time.asc()).all()


def get_slot_by_id(slot_id: int, is_admin_or_staff: bool = False) -> Slot | None:
    """Retrieve slot by ID.

    For farmers (is_admin_or_staff=False), returns None if slot is cancelled or date is in the past.
    """
    slot = db.session.get(Slot, slot_id)
    if not slot:
        return None

    if not is_admin_or_staff:
        if slot.status != SlotStatus.OPEN or slot.slot_date < date.today():
            return None

    return slot


def create_slot(data: dict) -> Slot:
    """Create a new procurement slot.

    Raises:
        SlotValidationError: missing or invalid input parameters.
        DuplicateSlotError: exact duplicate slot window.
        SlotOverlapError: overlapping slot window.
        DailyCapacityExceededError: total daily capacity exceeded.
    """
    if not isinstance(data, dict):
        raise SlotValidationError("Invalid request body. Expected JSON object.")

    errors = []

    # Validate centre
    centre_id = data.get("centre_id")
    centre = None
    if not centre_id or not isinstance(centre_id, int):
        errors.append("Valid centre_id is required.")
    else:
        centre = db.session.get(Centre, centre_id)
        if not centre or not centre.is_active:
            errors.append("Centre does not exist or is inactive.")

    # Validate crop
    crop_id = data.get("crop_id")
    crop = None
    if not crop_id or not isinstance(crop_id, int):
        errors.append("Valid crop_id is required.")
    else:
        crop = db.session.get(Crop, crop_id)
        if not crop or not crop.is_active:
            errors.append("Crop does not exist or is inactive.")

    # Validate slot_date
    slot_date = parse_date_string(data.get("slot_date") or data.get("date"))
    if not slot_date:
        errors.append("Valid slot_date is required (format: YYYY-MM-DD).")
    elif slot_date < date.today():
        errors.append("Slot date cannot be in the past.")

    # Validate start_time and end_time
    start_time = parse_time_string(data.get("start_time"))
    if not start_time:
        errors.append("Valid start_time is required (e.g. '09:00').")

    end_time = parse_time_string(data.get("end_time"))
    if not end_time:
        errors.append("Valid end_time is required (e.g. '10:00').")

    if start_time and end_time and start_time >= end_time:
        errors.append("Start time must be strictly earlier than end time.")

    if centre and start_time and end_time:
        is_early = centre.opening_time and start_time < centre.opening_time
        is_late = centre.closing_time and end_time > centre.closing_time
        if is_early or is_late:
            op_str = format_time_string(centre.opening_time) if centre.opening_time else "Any"
            cl_str = format_time_string(centre.closing_time) if centre.closing_time else "Any"
            errors.append(f"Slot time must fall within the centre's operating hours ({op_str}–{cl_str}).")

    # Validate capacity
    capacity = data.get("capacity")
    if capacity is None or not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
        errors.append("Capacity must be a positive integer greater than zero.")

    # Status
    status = str(data.get("status") or SlotStatus.OPEN).upper().strip()
    if status not in SlotStatus.choices:
        errors.append(f"Invalid status. Allowed choices: {', '.join(SlotStatus.choices)}.")

    if errors:
        raise SlotValidationError("Slot creation failed validation.", errors=errors)

    # Check interval overlap
    check_slot_overlap(centre_id, crop_id, slot_date, start_time, end_time)

    # Check centre daily capacity limit
    check_daily_capacity(centre_id, slot_date, capacity, centre.daily_capacity)

    slot = Slot(
        centre_id=centre_id,
        crop_id=crop_id,
        slot_date=slot_date,
        start_time=start_time,
        end_time=end_time,
        capacity=capacity,
        status=status,
    )

    try:
        db.session.add(slot)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise SlotError(f"Database error creating slot: {exc}")

    try:
        from app.services.audit_service import create_audit_log
        create_audit_log(
            action="CREATE_SLOT",
            entity_type="SLOT",
            entity_id=slot.id,
            description=f"Created slot #{slot.id} for centre {slot.centre_id} on {slot.slot_date}",
            metadata={"slot_id": slot.id, "centre_id": slot.centre_id, "slot_date": str(slot.slot_date)},
        )
    except Exception:
        pass

    return slot


def update_slot(slot_id: int, data: dict) -> Slot:
    """Update an existing slot.

    Re-runs overlap and capacity constraints.
    """
    slot = db.session.get(Slot, slot_id)
    if not slot:
        raise SlotValidationError("Slot not found.", errors=["Slot not found."])

    if not isinstance(data, dict):
        raise SlotValidationError("Invalid request body. Expected JSON object.")

    errors = []

    # Check centre update
    centre_id = data.get("centre_id", slot.centre_id)
    centre = db.session.get(Centre, centre_id)
    if not centre or not centre.is_active:
        errors.append("Centre does not exist or is inactive.")

    # Check crop update
    crop_id = data.get("crop_id", slot.crop_id)
    crop = db.session.get(Crop, crop_id)
    if not crop or not crop.is_active:
        errors.append("Crop does not exist or is inactive.")

    # Date update
    slot_date = parse_date_string(data.get("slot_date") or data.get("date")) if ("slot_date" in data or "date" in data) else slot.slot_date
    if not slot_date:
        errors.append("Invalid slot date format.")

    # Time update
    start_time = parse_time_string(data.get("start_time")) if "start_time" in data else slot.start_time
    if not start_time:
        errors.append("Invalid start time format.")

    end_time = parse_time_string(data.get("end_time")) if "end_time" in data else slot.end_time
    if not end_time:
        errors.append("Invalid end time format.")

    if start_time and end_time and start_time >= end_time:
        errors.append("Start time must be strictly earlier than end time.")

    if centre and start_time and end_time:
        is_early = centre.opening_time and start_time < centre.opening_time
        is_late = centre.closing_time and end_time > centre.closing_time
        if is_early or is_late:
            op_str = format_time_string(centre.opening_time) if centre.opening_time else "Any"
            cl_str = format_time_string(centre.closing_time) if centre.closing_time else "Any"
            errors.append(f"Slot time must fall within the centre's operating hours ({op_str}–{cl_str}).")

    # Capacity update
    capacity = data.get("capacity", slot.capacity)
    if capacity is None or not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
        errors.append("Capacity must be a positive integer greater than zero.")

    # Status update
    status = slot.status
    if "status" in data:
        status_val = str(data["status"]).upper().strip()
        if status_val not in SlotStatus.choices:
            errors.append(f"Invalid status. Allowed choices: {', '.join(SlotStatus.choices)}.")
        else:
            status = status_val

    if errors:
        raise SlotValidationError("Slot update failed validation.", errors=errors)

    # Re-verify overlap & capacity if not cancelled
    if status != SlotStatus.CANCELLED:
        check_slot_overlap(centre_id, crop_id, slot_date, start_time, end_time, exclude_slot_id=slot_id)
        check_daily_capacity(centre_id, slot_date, capacity, centre.daily_capacity, exclude_slot_id=slot_id)

    slot.centre_id = centre_id
    slot.crop_id = crop_id
    slot.slot_date = slot_date
    slot.start_time = start_time
    slot.end_time = end_time
    slot.capacity = capacity
    slot.status = status

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise SlotError(f"Database error updating slot: {exc}")

    try:
        from app.services.audit_service import create_audit_log
        create_audit_log(
            action="UPDATE_SLOT",
            entity_type="SLOT",
            entity_id=slot.id,
            description=f"Updated slot #{slot.id}",
            metadata={"slot_id": slot.id, "status": slot.status},
        )
    except Exception:
        pass

    return slot


def cancel_slot(slot_id: int) -> Slot:
    """Soft cancel a slot by setting status = CANCELLED."""
    slot = db.session.get(Slot, slot_id)
    if not slot:
        raise SlotValidationError("Slot not found.", errors=["Slot not found."])

    slot.status = SlotStatus.CANCELLED
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise SlotError(f"Database error cancelling slot: {exc}")

    try:
        from app.services.audit_service import create_audit_log
        create_audit_log(
            action="CANCEL_SLOT",
            entity_type="SLOT",
            entity_id=slot.id,
            description=f"Cancelled slot #{slot.id}",
            metadata={"slot_id": slot.id},
        )
    except Exception:
        pass

    return slot
