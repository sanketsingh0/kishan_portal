"""Procurement Centre service layer.

Encapsulates business logic, data validation, and database operations for centres:
- Retrieval (filtered by active status and permissions)
- Creation with operating hours and capacity validation
- Updates with uniqueness checks
- Soft deletion / deactivation
"""

from datetime import time, datetime
from app.extensions import db
from app.models import Centre


class CentreError(Exception):
    """Base exception for centre service errors."""

    def __init__(self, message: str, code: str = "CENTRE_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class DuplicateCentreNameError(CentreError):
    """Raised when centre name already exists."""

    def __init__(self, message: str = "A centre with this name already exists."):
        super().__init__(message, code="DUPLICATE_CENTRE_NAME")


class CentreValidationError(CentreError):
    """Raised when centre validation fails."""

    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message, code="VALIDATION_ERROR")
        self.errors = errors or [message]


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


def format_time_string(t: time | None) -> str | None:
    """Format datetime.time into 'HH:MM' string."""
    if t is None:
        return None
    return t.strftime("%H:%M")


def get_all_centres(include_inactive: bool = False) -> list[Centre]:
    """Retrieve all centres.

    Args:
        include_inactive: If True, returns both active and inactive centres.
                          If False, returns only active centres.

    Returns:
        List of Centre instances.
    """
    query = Centre.query
    if not include_inactive:
        query = query.filter(Centre.is_active == True)
    return query.order_by(Centre.name.asc()).all()


def get_centre_by_id(centre_id: int, include_inactive: bool = False) -> Centre | None:
    """Retrieve centre by ID.

    Args:
        centre_id: Database ID of the centre.
        include_inactive: If False, returns None if centre is inactive.

    Returns:
        Centre instance or None.
    """
    centre = db.session.get(Centre, centre_id)
    if not centre:
        return None
    if not include_inactive and not centre.is_active:
        return None
    return centre


def create_centre(data: dict) -> Centre:
    """Create a new procurement centre.

    Args:
        data: Dictionary with name, location, opening_time, closing_time,
              daily_capacity, average_processing_minutes, is_active.

    Returns:
        Created Centre instance.

    Raises:
        CentreValidationError: if validation fails.
        DuplicateCentreNameError: if name is duplicate.
    """
    if not isinstance(data, dict):
        raise CentreValidationError("Invalid request body. Expected JSON object.")

    errors = []

    name = str(data.get("name") or "").strip()
    if not name:
        errors.append("Centre name is required.")
    elif len(name) > 150:
        errors.append("Centre name cannot exceed 150 characters.")
    else:
        existing = Centre.query.filter(Centre.name == name).first()
        if existing:
            raise DuplicateCentreNameError()

    location = str(data.get("location") or "").strip()
    if not location:
        errors.append("Centre location is required.")
    elif len(location) > 255:
        errors.append("Location cannot exceed 255 characters.")

    opening_time_val = parse_time_string(data.get("opening_time"))
    if not opening_time_val:
        errors.append("Valid opening time is required (e.g. '09:00').")

    closing_time_val = parse_time_string(data.get("closing_time"))
    if not closing_time_val:
        errors.append("Valid closing time is required (e.g. '17:00').")

    if opening_time_val and closing_time_val and opening_time_val >= closing_time_val:
        errors.append("Opening time must be earlier than closing time.")

    daily_capacity = data.get("daily_capacity")
    if daily_capacity is None or not isinstance(daily_capacity, int) or isinstance(daily_capacity, bool) or daily_capacity <= 0:
        errors.append("Daily capacity must be a positive integer greater than zero.")

    avg_proc = data.get("average_processing_minutes")
    if avg_proc is None or not isinstance(avg_proc, int) or isinstance(avg_proc, bool) or avg_proc <= 0:
        errors.append("Average processing minutes must be a positive integer greater than zero.")

    is_active = data.get("is_active")
    if is_active is None:
        is_active = data.get("active", True)
    is_active = bool(is_active)

    if errors:
        raise CentreValidationError("Centre creation failed validation.", errors=errors)

    centre = Centre(
        name=name,
        location=location,
        opening_time=opening_time_val,
        closing_time=closing_time_val,
        daily_capacity=daily_capacity,
        average_processing_minutes=avg_proc,
        is_active=is_active,
    )

    try:
        db.session.add(centre)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise CentreError(f"Database error creating centre: {exc}")

    try:
        from app.services.audit_service import create_audit_log
        create_audit_log(
            action="CREATE_CENTRE",
            entity_type="CENTRE",
            entity_id=centre.id,
            description=f"Created centre '{centre.name}' at location '{centre.location}'",
            metadata={"centre_id": centre.id, "name": centre.name},
        )
    except Exception:
        pass

    return centre


def update_centre(centre_id: int, data: dict) -> Centre:
    """Update an existing centre.

    Args:
        centre_id: Database ID of centre to update.
        data: Dictionary of fields to update.

    Returns:
        Updated Centre instance.

    Raises:
        CentreValidationError: if centre is missing or fields fail validation.
        DuplicateCentreNameError: if updated name collides with another centre.
    """
    centre = db.session.get(Centre, centre_id)
    if not centre:
        raise CentreValidationError("Centre not found.", errors=["Centre not found."])

    if not isinstance(data, dict):
        raise CentreValidationError("Invalid request body. Expected JSON object.")

    errors = []

    if "name" in data:
        name = str(data["name"] or "").strip()
        if not name:
            errors.append("Centre name cannot be empty.")
        elif len(name) > 150:
            errors.append("Centre name cannot exceed 150 characters.")
        else:
            existing = Centre.query.filter(Centre.name == name, Centre.id != centre_id).first()
            if existing:
                raise DuplicateCentreNameError()
            centre.name = name

    if "location" in data:
        location = str(data["location"] or "").strip()
        if not location:
            errors.append("Centre location cannot be empty.")
        elif len(location) > 255:
            errors.append("Location cannot exceed 255 characters.")
        else:
            centre.location = location

    new_opening = parse_time_string(data.get("opening_time")) if "opening_time" in data else centre.opening_time
    new_closing = parse_time_string(data.get("closing_time")) if "closing_time" in data else centre.closing_time

    if "opening_time" in data and not new_opening:
        errors.append("Invalid opening time format.")
    else:
        centre.opening_time = new_opening

    if "closing_time" in data and not new_closing:
        errors.append("Invalid closing time format.")
    else:
        centre.closing_time = new_closing

    if new_opening and new_closing and new_opening >= new_closing:
        errors.append("Opening time must be earlier than closing time.")

    if "daily_capacity" in data:
        cap = data["daily_capacity"]
        if cap is None or not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0:
            errors.append("Daily capacity must be a positive integer greater than zero.")
        else:
            centre.daily_capacity = cap

    if "average_processing_minutes" in data:
        avg_proc = data["average_processing_minutes"]
        if avg_proc is None or not isinstance(avg_proc, int) or isinstance(avg_proc, bool) or avg_proc <= 0:
            errors.append("Average processing minutes must be a positive integer greater than zero.")
        else:
            centre.average_processing_minutes = avg_proc

    if "is_active" in data:
        centre.is_active = bool(data["is_active"])
    elif "active" in data:
        centre.is_active = bool(data["active"])

    if errors:
        raise CentreValidationError("Centre update failed validation.", errors=errors)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise CentreError(f"Database error updating centre: {exc}")

    try:
        from app.services.audit_service import create_audit_log
        create_audit_log(
            action="UPDATE_CENTRE",
            entity_type="CENTRE",
            entity_id=centre.id,
            description=f"Updated centre '{centre.name}'",
            metadata={"centre_id": centre.id, "is_active": centre.is_active},
        )
    except Exception:
        pass

    return centre


def deactivate_centre(centre_id: int) -> Centre:
    """Soft delete / deactivate a centre.

    Args:
        centre_id: Database ID of centre to deactivate.

    Returns:
        Deactivated Centre instance.
    """
    centre = db.session.get(Centre, centre_id)
    if not centre:
        raise CentreValidationError("Centre not found.", errors=["Centre not found."])

    centre.is_active = False
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise CentreError(f"Database error deactivating centre: {exc}")

    try:
        from app.services.audit_service import create_audit_log
        create_audit_log(
            action="DEACTIVATE_CENTRE",
            entity_type="CENTRE",
            entity_id=centre.id,
            description=f"Deactivated centre '{centre.name}'",
            metadata={"centre_id": centre.id},
        )
    except Exception:
        pass

    return centre
