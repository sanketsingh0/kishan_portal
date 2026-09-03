"""Procurement service layer.

Handles business logic and database operations for Procurement status tracking.
"""

from datetime import datetime, date
from app.extensions import db
from app.models import Booking, Procurement, ProcurementStatus
from app.services.farmer_service import get_farmer_by_user_id
from app.queue.events import emit_procurement_update


class ProcurementError(Exception):
    """Base exception for procurement operations."""

    def __init__(self, message="Procurement operation failed"):
        self.message = message
        super().__init__(self.message)


class ProcurementNotFoundError(ProcurementError):
    """Raised when a requested procurement or booking record is not found."""

    def __init__(self, message="Procurement record not found"):
        super().__init__(message)


class ProcurementConflictError(ProcurementError):
    """Raised when attempting to create a duplicate procurement record."""

    def __init__(self, message="Procurement record already exists for this booking"):
        super().__init__(message)


class ProcurementValidationError(ProcurementError):
    """Raised when validation of procurement fields fails."""

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
            raise ProcurementValidationError(["Invalid procurement_date format. Expected YYYY-MM-DD."])
    raise ProcurementValidationError(["Invalid procurement_date type."])


def get_procurement_by_booking(booking_id: int, user_id: str | None = None) -> Procurement | None:
    """Retrieve procurement record for a booking.

    If user_id is provided, verifies that the booking belongs to the farmer.
    """
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return None

    if user_id is not None:
        farmer = get_farmer_by_user_id(user_id)
        if not farmer or booking.farmer_id != farmer.id:
            return None

    return booking.procurement


def create_procurement(booking_id: int, data: dict) -> Procurement:
    """Create a new procurement record for a booking (STAFF/ADMIN)."""
    if not isinstance(data, dict):
        raise ProcurementValidationError(["Request body must be a JSON object."])

    booking = db.session.get(Booking, booking_id)
    if not booking:
        raise ProcurementNotFoundError(f"Booking {booking_id} not found.")

    if booking.procurement:
        raise ProcurementConflictError(f"Procurement record already exists for booking {booking_id}.")

    errors = []
    status = data.get("procurement_status", ProcurementStatus.PENDING)
    if status not in ProcurementStatus.choices:
        errors.append(f"Invalid procurement_status '{status}'. Choices: {', '.join(ProcurementStatus.choices)}.")

    quantity = data.get("quantity")
    if quantity is not None:
        try:
            quantity = float(quantity)
            if quantity <= 0:
                errors.append("quantity must be a positive number (> 0).")
        except (ValueError, TypeError):
            errors.append("quantity must be a valid numeric value.")

    unit = data.get("unit", "quintal")
    if unit is not None:
        if not isinstance(unit, str) or len(unit.strip()) == 0 or len(unit) > 20:
            errors.append("unit must be a string up to 20 characters.")
        else:
            unit = unit.strip()

    procurement_date = None
    if "procurement_date" in data and data["procurement_date"]:
        try:
            procurement_date = parse_date_value(data["procurement_date"])
        except ProcurementValidationError as pve:
            errors.extend(pve.errors)

    remarks = data.get("remarks")
    if remarks is not None:
        if not isinstance(remarks, str) or len(remarks) > 255:
            errors.append("remarks must be a string up to 255 characters.")

    if errors:
        raise ProcurementValidationError(errors)

    procurement = Procurement(
        booking_id=booking.id,
        procurement_status=status,
        quantity=quantity,
        unit=unit,
        procurement_date=procurement_date,
        remarks=remarks,
    )

    try:
        db.session.add(procurement)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise ProcurementError(f"Database error while saving procurement: {exc}")

    # Emit realtime event post-commit
    centre_id = booking.slot.centre_id if booking.slot else None
    slot_date = booking.slot.slot_date if booking.slot else None
    emit_procurement_update(booking.id, centre_id, slot_date, reason="PROCUREMENT_CREATED")

    try:
        if booking.farmer and booking.farmer.user_id:
            from app.services.notification_service import create_notification
            from app.models import NotificationType

            create_notification(
                user_id=booking.farmer.user_id,
                notification_type=NotificationType.PROCUREMENT_UPDATE,
                title=f"Procurement Status: {status}",
                message=f"Procurement status for token {booking.token_number or ''} updated to {status.replace('_', ' ')}.",
                booking_id=booking.id,
            )
    except Exception:
        pass

    return procurement


def update_procurement(booking_id: int, data: dict) -> Procurement:
    """Update an existing procurement record for a booking (STAFF/ADMIN)."""
    if not isinstance(data, dict):
        raise ProcurementValidationError(["Request body must be a JSON object."])

    booking = db.session.get(Booking, booking_id)
    if not booking:
        raise ProcurementNotFoundError(f"Booking {booking_id} not found.")

    procurement = booking.procurement
    if not procurement:
        raise ProcurementNotFoundError(f"No procurement record exists for booking {booking_id}.")

    old_status = procurement.procurement_status
    errors = []

    if "procurement_status" in data:
        status = data["procurement_status"]
        if status not in ProcurementStatus.choices:
            errors.append(f"Invalid procurement_status '{status}'. Choices: {', '.join(ProcurementStatus.choices)}.")
        else:
            procurement.procurement_status = status

    if "quantity" in data:
        quantity = data["quantity"]
        if quantity is not None:
            try:
                quantity = float(quantity)
                if quantity <= 0:
                    errors.append("quantity must be a positive number (> 0).")
                else:
                    procurement.quantity = quantity
            except (ValueError, TypeError):
                errors.append("quantity must be a valid numeric value.")
        else:
            procurement.quantity = None

    if "unit" in data:
        unit = data["unit"]
        if unit is not None:
            if not isinstance(unit, str) or len(unit.strip()) == 0 or len(unit) > 20:
                errors.append("unit must be a string up to 20 characters.")
            else:
                procurement.unit = unit.strip()
        else:
            procurement.unit = None

    if "procurement_date" in data:
        if data["procurement_date"]:
            try:
                procurement.procurement_date = parse_date_value(data["procurement_date"])
            except ProcurementValidationError as pve:
                errors.extend(pve.errors)
        else:
            procurement.procurement_date = None

    if "remarks" in data:
        remarks = data["remarks"]
        if remarks is not None:
            if not isinstance(remarks, str) or len(remarks) > 255:
                errors.append("remarks must be a string up to 255 characters.")
            else:
                procurement.remarks = remarks
        else:
            procurement.remarks = None

    if errors:
        raise ProcurementValidationError(errors)

    new_status = procurement.procurement_status
    status_changed = old_status != new_status

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise ProcurementError(f"Database error while updating procurement: {exc}")

    # Emit realtime event post-commit
    centre_id = booking.slot.centre_id if booking.slot else None
    slot_date = booking.slot.slot_date if booking.slot else None
    emit_procurement_update(booking.id, centre_id, slot_date, reason="PROCUREMENT_UPDATED")

    try:
        if status_changed and booking.farmer and booking.farmer.user_id:
            from app.services.notification_service import create_notification
            from app.models import NotificationType

            create_notification(
                user_id=booking.farmer.user_id,
                notification_type=NotificationType.PROCUREMENT_UPDATE,
                title=f"Procurement Status: {new_status}",
                message=f"Procurement status for token {booking.token_number or ''} updated to {new_status.replace('_', ' ')}.",
                booking_id=booking.id,
            )
    except Exception:
        pass

    return procurement
