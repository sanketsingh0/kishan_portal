"""Staff-Controlled Next-Day Carry-Forward service (part 1: helpers)."""

import logging
from datetime import date, datetime

from app.extensions import db
from app.models import (
    Booking,
    BookingStatus,
    BookingCarryForward,
    CarryForwardReason,
    ProcurementStatus,
    Slot,
    SlotStatus,
)

logger = logging.getLogger(__name__)


class CarryForwardError(Exception):
    def __init__(self, message: str, code: str = "CARRY_FORWARD_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class CarryForwardValidationError(CarryForwardError):
    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message, code="VALIDATION_ERROR")
        self.errors = errors or [message]


_NON_ELIGIBLE_STATUS_REASONS = {
    BookingStatus.COMPLETED: "Booking is already COMPLETED.",
    BookingStatus.CANCELLED: "Booking is already CANCELLED.",
    BookingStatus.NO_SHOW: "Booking is marked NO_SHOW.",
    BookingStatus.CARRIED_FORWARD: "Booking was already carried forward.",
}


def _normalize_reason(reason) -> str:
    if not isinstance(reason, str) or not reason.strip():
        raise CarryForwardValidationError(
            "A carry-forward reason is required.",
            errors=["A carry-forward reason is required."],
        )
    cleaned = reason.strip()
    for choice in CarryForwardReason.choices:
        if cleaned.lower() == choice.lower():
            return choice
    raise CarryForwardValidationError(
        f"Invalid reason '{cleaned}'.",
        errors=[f"Invalid reason '{cleaned}'."],
    )


def _parse_source_date(value) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except (ValueError, AttributeError):
            pass
    raise CarryForwardValidationError(
        "Invalid source date. Expected YYYY-MM-DD.",
        errors=["Invalid source date. Expected YYYY-MM-DD."],
    )


def _parse_target_date(value) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except (ValueError, AttributeError):
            pass
    raise CarryForwardValidationError(
        "Invalid target_date. Expected YYYY-MM-DD.",
        errors=["Invalid target_date. Expected YYYY-MM-DD."],
    )


def check_booking_eligibility(booking: Booking, source_date: date, centre_id: int):
    if booking is None:
        return False, "Booking not found."
    slot = booking.slot
    if slot is None or slot.centre_id != centre_id:
        return False, "Booking does not belong to this centre."
    if slot.slot_date != source_date:
        return False, "Booking is not scheduled for the selected procurement date."
    if booking.status not in (BookingStatus.PENDING, BookingStatus.CONFIRMED):
        reason = _NON_ELIGIBLE_STATUS_REASONS.get(
            booking.status, f"Booking status '{booking.status}' is not eligible."
        )
        return False, reason
    procurement = booking.procurement
    if procurement is not None:
        if procurement.procurement_status in (
            ProcurementStatus.COMPLETED,
            ProcurementStatus.REJECTED,
        ):
            return False, (
                f"Procurement is already {procurement.procurement_status}."
            )
        if procurement.procurement_status == ProcurementStatus.IN_PROGRESS:
            return False, (
                "Procurement is IN_PROGRESS (active weighment/payment state); "
                "complete or reject it first. Excluded so no duplicate "
                "procurement record is created."
            )
    existing = BookingCarryForward.query.filter_by(
        original_booking_id=booking.id
    ).first()
    if existing is not None:
        return False, "Booking was already carried forward."
    return True, None


def get_eligible_bookings(centre_id: int, source_date: date):
    candidates = (
        Booking.query.join(Slot)
        .filter(Slot.centre_id == centre_id, Slot.slot_date == source_date)
        .all()
    )
    eligible = []
    for booking in candidates:
        ok, _ = check_booking_eligibility(booking, source_date, centre_id)
        if ok:
            eligible.append(booking)
    eligible.sort(key=lambda b: (b.token_number or "", b.id))
    return eligible
