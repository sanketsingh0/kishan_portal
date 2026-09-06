"""Public read-only API routes for the KisanProcure landing page.

These endpoints expose procurement centre and slot information to
unauthenticated visitors. They reuse the exact same service-layer
functions as the authenticated routes — no business logic is
duplicated here.

Endpoints:
    GET /api/public/centres  -> list active procurement centres
    GET /api/public/slots    -> list upcoming OPEN procurement slots
"""

from flask import Blueprint, jsonify

from app.models import SlotStatus
from app.services.centre_service import get_all_centres, format_time_string
from app.services.slot_service import get_slots, format_date_string as fmt_slot_date, format_time_string as fmt_slot_time

public_bp = Blueprint("public", __name__, url_prefix="/api/public")


def _format_centre(c):
    """Serialize a Centre instance to a clean JSON dictionary."""
    return {
        "id": c.id,
        "name": c.name,
        "location": c.location,
        "opening_time": format_time_string(c.opening_time),
        "closing_time": format_time_string(c.closing_time),
        "daily_capacity": c.daily_capacity,
        "average_processing_minutes": c.average_processing_minutes,
        "is_active": c.is_active,
        "active": c.is_active,
    }


def _format_slot(s):
    """Serialize a Slot instance to a clean JSON dictionary."""
    active_booked = sum(
        1 for b in s.bookings
        if b.status in ("PENDING", "CONFIRMED")
    )
    return {
        "id": s.id,
        "centre_id": s.centre_id,
        "centre_name": s.centre.name if s.centre else None,
        "crop_id": s.crop_id,
        "crop_name": s.crop.name if s.crop else None,
        "slot_date": fmt_slot_date(s.slot_date),
        "start_time": fmt_slot_time(s.start_time),
        "end_time": fmt_slot_time(s.end_time),
        "capacity": s.capacity,
        "booked_count": active_booked,
        "remaining_capacity": max(0, s.capacity - active_booked),
        "status": s.status,
    }


@public_bp.route("/centres", methods=["GET"])
def list_public_centres():
    """List active procurement centres (public, no authentication).

    Returns:
        200 OK: { centres: [...] }
    """
    centres = get_all_centres(include_inactive=False)
    return jsonify({"centres": [_format_centre(c) for c in centres]}), 200


@public_bp.route("/slots", methods=["GET"])
def list_public_slots():
    """List upcoming OPEN procurement slots (public, no authentication).

    Query parameters:
        centre_id: int  — filter by centre
        crop_id:    int  — filter by crop
        date:    YYYY-MM-DD — filter by specific date

    Returns:
        200 OK: { slots: [...] }
    """
    from flask import request

    centre_id = request.args.get("centre_id", type=int)
    crop_id = request.args.get("crop_id", type=int)
    slot_date = request.args.get("date") or request.args.get("slot_date")

    slots = get_slots(
        centre_id=centre_id,
        crop_id=crop_id,
        slot_date=slot_date,
        status=SlotStatus.OPEN,
        upcoming_only=True,
    )
    return jsonify({"slots": [_format_slot(s) for s in slots]}), 200
