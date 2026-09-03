"""
Analytics Service.

Provides optimized aggregate queries for admin dashboard and system analytics.
"""

from datetime import datetime, date, time, timedelta, timezone
from sqlalchemy import func, case
from app.extensions import db
from app.models import (
    User, UserRole, Centre, Crop, Slot, Booking, BookingStatus,
    Procurement, ProcurementStatus, Payment, PaymentStatus, Delay, DelayStatus
)


class AnalyticsValidationError(Exception):
    """Exception raised for invalid analytics query parameters."""
    pass


def parse_date_range(start_date_str: str | None, end_date_str: str | None) -> tuple[datetime | None, datetime | None]:
    """Parse and validate date string inputs.

    Returns:
        tuple of (start_datetime, end_datetime)
    Raises:
        AnalyticsValidationError: if date format is invalid or start_date > end_date.
    """
    start_dt = None
    end_dt = None

    if start_date_str:
        try:
            d = datetime.strptime(start_date_str.strip(), "%Y-%m-%d").date()
            start_dt = datetime.combine(d, time.min).replace(tzinfo=timezone.utc)
        except ValueError:
            raise AnalyticsValidationError("Invalid start_date format. Expected YYYY-MM-DD.")

    if end_date_str:
        try:
            d = datetime.strptime(end_date_str.strip(), "%Y-%m-%d").date()
            end_dt = datetime.combine(d, time.max).replace(tzinfo=timezone.utc)
        except ValueError:
            raise AnalyticsValidationError("Invalid end_date format. Expected YYYY-MM-DD.")

    if start_dt and end_dt and start_dt > end_dt:
        raise AnalyticsValidationError("start_date cannot be after end_date.")

    return start_dt, end_dt


def get_overview_analytics() -> dict:
    """Retrieve top-level KPI metrics for the admin overview dashboard."""
    today = date.today()
    today_start = datetime.combine(today, time.min).replace(tzinfo=timezone.utc)
    today_end = datetime.combine(today, time.max).replace(tzinfo=timezone.utc)

    # Farmers count
    total_farmers = db.session.query(func.count(User.id)).filter(User.role == UserRole.FARMER).scalar() or 0
    active_farmers = db.session.query(func.count(User.id)).filter(User.role == UserRole.FARMER, User.is_active.is_(True)).scalar() or 0

    # Centres count
    total_centres = db.session.query(func.count(Centre.id)).scalar() or 0
    active_centres = db.session.query(func.count(Centre.id)).filter(Centre.is_active.is_(True)).scalar() or 0

    # Today's bookings
    todays_bookings = db.session.query(func.count(Booking.id)).join(Slot).filter(
        Slot.slot_date == today
    ).scalar() or 0

    # Today's completed procurements
    todays_completed_procurements = db.session.query(func.count(Procurement.id)).join(Booking).join(Slot).filter(
        Slot.slot_date == today,
        Procurement.procurement_status == ProcurementStatus.COMPLETED
    ).scalar() or 0

    # Today's active queue
    todays_active_queue = db.session.query(func.count(Booking.id)).join(Slot).filter(
        Slot.slot_date == today,
        Booking.status.in_(BookingStatus.active_statuses)
    ).scalar() or 0

    # Today's estimated delay (sum of active delay minutes for today)
    todays_delay_minutes = db.session.query(func.sum(Delay.delay_minutes)).filter(
        Delay.delay_date == today,
        Delay.status == DelayStatus.ACTIVE
    ).scalar() or 0

    return {
        "total_farmers": total_farmers,
        "active_farmers": active_farmers,
        "total_centres": total_centres,
        "active_centres": active_centres,
        "todays_bookings": todays_bookings,
        "todays_completed_procurements": todays_completed_procurements,
        "todays_active_queue": todays_active_queue,
        "todays_delay_minutes": todays_delay_minutes,
    }


def get_booking_analytics(
    start_date: str | None = None,
    end_date: str | None = None,
    centre_id: int | None = None,
    crop_id: int | None = None,
) -> dict:
    """Retrieve filtered booking statistics and daily trends."""
    start_dt, end_dt = parse_date_range(start_date, end_date)

    query = db.session.query(Booking).join(Slot)

    if start_dt:
        query = query.filter(Booking.created_at >= start_dt)
    if end_dt:
        query = query.filter(Booking.created_at <= end_dt)
    if centre_id:
        query = query.filter(Slot.centre_id == centre_id)
    if crop_id:
        query = query.filter(Slot.crop_id == crop_id)

    # Status counts aggregation
    status_counts_raw = (
        db.session.query(Booking.status, func.count(Booking.id))
        .join(Slot)
    )
    if start_dt:
        status_counts_raw = status_counts_raw.filter(Booking.created_at >= start_dt)
    if end_dt:
        status_counts_raw = status_counts_raw.filter(Booking.created_at <= end_dt)
    if centre_id:
        status_counts_raw = status_counts_raw.filter(Slot.centre_id == centre_id)
    if crop_id:
        status_counts_raw = status_counts_raw.filter(Slot.crop_id == crop_id)

    status_dict = dict(status_counts_raw.group_by(Booking.status).all())

    # Daily trend calculation (last 7 days if no date range specified)
    trend_start = start_dt.date() if start_dt else (date.today() - timedelta(days=6))
    trend_end = end_dt.date() if end_dt else date.today()

    trend_raw = (
        db.session.query(Slot.slot_date, func.count(Booking.id))
        .join(Slot)
        .filter(Slot.slot_date >= trend_start, Slot.slot_date <= trend_end)
    )
    if centre_id:
        trend_raw = trend_raw.filter(Slot.centre_id == centre_id)
    if crop_id:
        trend_raw = trend_raw.filter(Slot.crop_id == crop_id)

    trend_map = dict(trend_raw.group_by(Slot.slot_date).all())

    # Build daily trend list for all dates in range
    daily_trends = []
    curr = trend_start
    while curr <= trend_end:
        daily_trends.append({
            "date": curr.isoformat(),
            "count": trend_map.get(curr, 0)
        })
        curr += timedelta(days=1)

    total_bookings = sum(status_dict.values())

    return {
        "total_bookings": total_bookings,
        "by_status": {
            "CONFIRMED": status_dict.get(BookingStatus.CONFIRMED, 0),
            "PENDING": status_dict.get(BookingStatus.PENDING, 0),
            "CANCELLED": status_dict.get(BookingStatus.CANCELLED, 0),
            "COMPLETED": status_dict.get(BookingStatus.COMPLETED, 0),
            "NO_SHOW": status_dict.get(BookingStatus.NO_SHOW, 0),
        },
        "daily_trends": daily_trends,
    }


def get_procurement_analytics(
    start_date: str | None = None,
    end_date: str | None = None,
    centre_id: int | None = None,
    crop_id: int | None = None,
) -> dict:
    """Retrieve filtered procurement statistics and breakdowns."""
    start_dt, end_dt = parse_date_range(start_date, end_date)

    query = db.session.query(Procurement).join(Booking).join(Slot)

    if start_dt:
        query = query.filter(Procurement.created_at >= start_dt)
    if end_dt:
        query = query.filter(Procurement.created_at <= end_dt)
    if centre_id:
        query = query.filter(Slot.centre_id == centre_id)
    if crop_id:
        query = query.filter(Slot.crop_id == crop_id)

    # Status distribution
    status_raw = dict(
        query.with_entities(Procurement.procurement_status, func.count(Procurement.id))
        .group_by(Procurement.procurement_status)
        .all()
    )

    # Total quantity
    total_quantity = float(
        query.with_entities(func.coalesce(func.sum(Procurement.quantity), 0.0)).scalar() or 0.0
    )

    # Quantity by Crop
    crop_raw = (
        db.session.query(Crop.name, func.coalesce(func.sum(Procurement.quantity), 0.0))
        .select_from(Procurement)
        .join(Booking)
        .join(Slot)
        .join(Crop)
    )
    if start_dt:
        crop_raw = crop_raw.filter(Procurement.created_at >= start_dt)
    if end_dt:
        crop_raw = crop_raw.filter(Procurement.created_at <= end_dt)
    if centre_id:
        crop_raw = crop_raw.filter(Slot.centre_id == centre_id)
    if crop_id:
        crop_raw = crop_raw.filter(Slot.crop_id == crop_id)

    by_crop = [
        {"crop_name": name, "total_quantity": float(qty)}
        for name, qty in crop_raw.group_by(Crop.name).all()
    ]

    # Quantity by Centre
    centre_raw = (
        db.session.query(Centre.name, func.coalesce(func.sum(Procurement.quantity), 0.0))
        .select_from(Procurement)
        .join(Booking)
        .join(Slot)
        .join(Centre)
    )
    if start_dt:
        centre_raw = centre_raw.filter(Procurement.created_at >= start_dt)
    if end_dt:
        centre_raw = centre_raw.filter(Procurement.created_at <= end_dt)
    if centre_id:
        centre_raw = centre_raw.filter(Slot.centre_id == centre_id)
    if crop_id:
        centre_raw = centre_raw.filter(Slot.crop_id == crop_id)

    by_centre = [
        {"centre_name": name, "total_quantity": float(qty)}
        for name, qty in centre_raw.group_by(Centre.name).all()
    ]

    total_records = sum(status_raw.values())

    return {
        "total_records": total_records,
        "total_quantity": round(total_quantity, 2),
        "by_status": {
            "PENDING": status_raw.get(ProcurementStatus.PENDING, 0),
            "IN_PROGRESS": status_raw.get(ProcurementStatus.IN_PROGRESS, 0),
            "COMPLETED": status_raw.get(ProcurementStatus.COMPLETED, 0),
            "REJECTED": status_raw.get(ProcurementStatus.REJECTED, 0),
        },
        "by_crop": by_crop,
        "by_centre": by_centre,
    }


def get_payment_analytics(start_date: str | None = None, end_date: str | None = None) -> dict:
    """Retrieve high-level payment status statistics."""
    start_dt, end_dt = parse_date_range(start_date, end_date)

    query = db.session.query(Payment)

    if start_dt:
        query = query.filter(Payment.created_at >= start_dt)
    if end_dt:
        query = query.filter(Payment.created_at <= end_dt)

    status_raw = dict(
        query.with_entities(Payment.payment_status, func.count(Payment.id))
        .group_by(Payment.payment_status)
        .all()
    )

    paid_sum_query = query.filter(Payment.payment_status == PaymentStatus.PAID)
    total_paid_amount = float(
        paid_sum_query.with_entities(func.coalesce(func.sum(Payment.amount), 0.0)).scalar() or 0.0
    )

    total_payments = sum(status_raw.values())

    return {
        "total_payments": total_payments,
        "total_paid_amount": round(total_paid_amount, 2),
        "by_status": {
            "PENDING": status_raw.get(PaymentStatus.PENDING, 0),
            "PROCESSING": status_raw.get(PaymentStatus.PROCESSING, 0),
            "PAID": status_raw.get(PaymentStatus.PAID, 0),
            "FAILED": status_raw.get(PaymentStatus.FAILED, 0),
        },
    }


def get_queue_analytics(
    start_date: str | None = None,
    end_date: str | None = None,
    centre_id: int | None = None,
) -> dict:
    """Retrieve queue statistics grouped by centre."""
    target_date = date.today()
    if start_date:
        try:
            target_date = datetime.strptime(start_date.strip(), "%Y-%m-%d").date()
        except ValueError:
            raise AnalyticsValidationError("Invalid start_date format. Expected YYYY-MM-DD.")

    query_centres = db.session.query(Centre)
    if centre_id:
        query_centres = query_centres.filter(Centre.id == centre_id)

    centres = query_centres.all()
    centre_analytics = []

    for c in centres:
        active_bookings_cnt = (
            db.session.query(func.count(Booking.id))
            .join(Slot)
            .filter(
                Slot.centre_id == c.id,
                Slot.slot_date == target_date,
                Booking.status.in_(BookingStatus.active_statuses)
            )
            .scalar() or 0
        )

        completed_cnt = (
            db.session.query(func.count(Booking.id))
            .join(Slot)
            .filter(
                Slot.centre_id == c.id,
                Slot.slot_date == target_date,
                Booking.status == BookingStatus.COMPLETED
            )
            .scalar() or 0
        )

        # Calculate active delays for this centre and date
        active_delay_minutes = (
            db.session.query(func.coalesce(func.sum(Delay.delay_minutes), 0))
            .filter(
                Delay.centre_id == c.id,
                Delay.delay_date == target_date,
                Delay.status == DelayStatus.ACTIVE
            )
            .scalar() or 0
        )

        base_wait = active_bookings_cnt * c.average_processing_minutes
        estimated_wait = base_wait + active_delay_minutes

        centre_analytics.append({
            "centre_id": c.id,
            "centre_name": c.name,
            "date": target_date.isoformat(),
            "active_queue": active_bookings_cnt,
            "completed_procurements": completed_cnt,
            "average_processing_minutes": c.average_processing_minutes,
            "active_delay_minutes": active_delay_minutes,
            "estimated_wait_minutes": estimated_wait,
        })

    return {
        "date": target_date.isoformat(),
        "centres": centre_analytics,
    }


def get_delay_analytics(
    start_date: str | None = None,
    end_date: str | None = None,
    centre_id: int | None = None,
) -> dict:
    """Retrieve procurement delay breakdown statistics."""
    start_dt, end_dt = parse_date_range(start_date, end_date)

    query = db.session.query(Delay)

    if start_dt:
        query = query.filter(Delay.created_at >= start_dt)
    if end_dt:
        query = query.filter(Delay.created_at <= end_dt)
    if centre_id:
        query = query.filter(Delay.centre_id == centre_id)

    status_raw = dict(
        query.with_entities(Delay.status, func.count(Delay.id))
        .group_by(Delay.status)
        .all()
    )

    active_delay_mins = (
        query.filter(Delay.status == DelayStatus.ACTIVE)
        .with_entities(func.coalesce(func.sum(Delay.delay_minutes), 0))
        .scalar() or 0
    )

    by_centre_raw = (
        db.session.query(Centre.name, func.count(Delay.id), func.coalesce(func.sum(Delay.delay_minutes), 0))
        .join(Delay, Delay.centre_id == Centre.id)
    )
    if start_dt:
        by_centre_raw = by_centre_raw.filter(Delay.created_at >= start_dt)
    if end_dt:
        by_centre_raw = by_centre_raw.filter(Delay.created_at <= end_dt)
    if centre_id:
        by_centre_raw = by_centre_raw.filter(Delay.centre_id == centre_id)

    by_centre = [
        {"centre_name": name, "delay_count": cnt, "total_delay_minutes": mins}
        for name, cnt, mins in by_centre_raw.group_by(Centre.name).all()
    ]

    total_delays = sum(status_raw.values())

    return {
        "total_delays": total_delays,
        "active_delay_minutes": active_delay_mins,
        "by_status": {
            "ACTIVE": status_raw.get(DelayStatus.ACTIVE, 0),
            "RESOLVED": status_raw.get(DelayStatus.RESOLVED, 0),
            "CANCELLED": status_raw.get(DelayStatus.CANCELLED, 0),
        },
        "by_centre": by_centre,
    }
