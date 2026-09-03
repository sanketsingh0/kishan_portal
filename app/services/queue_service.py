"""Procurement Queue Management Service.

Encapsulates dynamic queue calculations, token-ordered positions, farmers-ahead tracking,
and estimated waiting time calculations per centre and date scope.
"""

from datetime import date
from app.extensions import db
from app.models import Booking, BookingStatus, Slot, Centre
from app.services.farmer_service import get_farmer_by_user_id
from app.services.slot_service import format_date_string, format_time_string


class QueueError(Exception):
    """Base exception for queue service errors."""
    pass


def parse_token_sequence(token_str: str | None) -> int:
    """Extract numeric integer from formatted token string (e.g. K-0005 -> 5).
    
    If token is missing or malformed, returns a large integer so it sorts last.
    """
    if not token_str or not token_str.startswith("K-"):
        return 999999999
    try:
        return int(token_str.split("-")[1])
    except (IndexError, ValueError):
        return 999999999


def get_active_queue_bookings_for_scope(centre_id: int, slot_date: date) -> list[Booking]:
    """Retrieve active queue bookings for a given centre and date ordered by token number integer."""
    active_bookings = (
        Booking.query.join(Slot)
        .filter(
            Slot.centre_id == centre_id,
            Slot.slot_date == slot_date,
            Booking.status.in_(BookingStatus.active_statuses)
        )
        .all()
    )

    # Sort ascending by token integer sequence, breaking ties with booking ID
    active_bookings.sort(key=lambda b: (parse_token_sequence(b.token_number), b.id))
    return active_bookings


def get_booking_queue_status(booking_id: int, user_id: int | None = None, is_staff_or_admin: bool = False) -> dict | None:
    """Calculate and return dynamic queue status for a specific booking.

    Args:
        booking_id: Booking ID to inspect.
        user_id: Local user ID of the requesting user (for farmer ownership check).
        is_staff_or_admin: If True, bypasses farmer ownership check.

    Returns:
        Dictionary containing queue position, farmers ahead, estimated wait minutes, and context,
        or None if booking not found / access denied.
    """
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return None

    # Ownership check for farmers
    if not is_staff_or_admin:
        if not user_id:
            return None
        farmer = get_farmer_by_user_id(user_id)
        if not farmer or booking.farmer_id != farmer.id:
            return None

    slot = booking.slot
    if not slot or not slot.centre:
        return None

    centre = slot.centre
    avg_minutes = centre.average_processing_minutes or 15

    # Inactive booking check (CANCELLED, COMPLETED, NO_SHOW)
    if booking.status not in BookingStatus.active_statuses:
        return {
            "booking_id": booking.id,
            "token_number": booking.token_number,
            "status": booking.status,
            "queue_position": None,
            "farmers_ahead": 0,
            "estimated_wait_minutes": 0,
            "is_active_queue": False,
            "centre": centre.name,
            "centre_id": centre.id,
            "crop": slot.crop.name if slot.crop else None,
            "slot_date": format_date_string(slot.slot_date),
            "start_time": format_time_string(slot.start_time),
            "end_time": format_time_string(slot.end_time),
            "average_processing_time": avg_minutes,
        }

    # Retrieve sorted active queue for centre + date scope
    active_queue = get_active_queue_bookings_for_scope(slot.centre_id, slot.slot_date)

    # Locate booking in active queue
    queue_position = None
    farmers_ahead = 0
    estimated_wait_minutes = 0
    is_active_queue = False

    for idx, b in enumerate(active_queue):
        if b.id == booking.id:
            queue_position = idx + 1
            farmers_ahead = idx
            estimated_wait_minutes = farmers_ahead * avg_minutes
            is_active_queue = True
            break

    return {
        "booking_id": booking.id,
        "token_number": booking.token_number,
        "status": booking.status,
        "queue_position": queue_position,
        "farmers_ahead": farmers_ahead,
        "estimated_wait_minutes": estimated_wait_minutes,
        "is_active_queue": is_active_queue,
        "centre": centre.name,
        "centre_id": centre.id,
        "crop": slot.crop.name if slot.crop else None,
        "slot_date": format_date_string(slot.slot_date),
        "start_time": format_time_string(slot.start_time),
        "end_time": format_time_string(slot.end_time),
        "average_processing_time": avg_minutes,
    }


def get_centre_queue(centre_id: int, target_date: date | None = None) -> dict | None:
    """Retrieve full active queue list for a procurement centre and target date (Staff/Admin).

    Args:
        centre_id: ID of the centre.
        target_date: Date to inspect (defaults to today's date if None).

    Returns:
        Dictionary containing centre details, total waiting, and ordered queue entries,
        or None if centre not found.
    """
    centre = db.session.get(Centre, centre_id)
    if not centre:
        return None

    if target_date is None:
        target_date = date.today()

    avg_minutes = centre.average_processing_minutes or 15
    active_queue = get_active_queue_bookings_for_scope(centre.id, target_date)

    queue_entries = []
    for idx, b in enumerate(active_queue):
        farmers_ahead = idx
        wait_mins = farmers_ahead * avg_minutes
        queue_entries.append({
            "booking_id": b.id,
            "token_number": b.token_number,
            "queue_position": idx + 1,
            "farmers_ahead": farmers_ahead,
            "estimated_wait_minutes": wait_mins,
            "status": b.status,
            "crop": b.slot.crop.name if b.slot and b.slot.crop else None,
            "slot_time": f"{format_time_string(b.slot.start_time)} - {format_time_string(b.slot.end_time)}" if b.slot else None,
        })

    return {
        "centre_id": centre.id,
        "centre_name": centre.name,
        "date": format_date_string(target_date),
        "average_processing_time": avg_minutes,
        "total_waiting": len(queue_entries),
        "queue": queue_entries,
    }
