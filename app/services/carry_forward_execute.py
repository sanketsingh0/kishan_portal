"""Staff-Controlled Next-Day Carry-Forward execution (bulk operation)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Booking, BookingStatus, BookingCarryForward, Centre
from app.models import Slot, SlotStatus
from app.services.booking_service import (
    generate_token_for_booking,
    get_active_bookings_count_for_slot,
)
from app.services.carry_forward_service import (
    CarryForwardError,
    CarryForwardValidationError,
    _normalize_reason,
    _parse_target_date,
    check_booking_eligibility,
)


def _resolve_target_slot(booking, centre_id, target_date, requested_slot_id):
    if requested_slot_id is not None:
        target = db.session.get(Slot, requested_slot_id)
        if target is None:
            raise CarryForwardValidationError(
                f"Target slot {requested_slot_id} not found.",
                errors=[f"Target slot {requested_slot_id} not found."],
            )
        if target.centre_id != centre_id:
            raise CarryForwardValidationError(
                "Target slot belongs to a different centre.",
                errors=["Target slot belongs to a different centre."],
            )
        if target.slot_date != target_date:
            raise CarryForwardValidationError(
                "Target slot date does not match target_date.",
                errors=["Target slot date does not match target_date."],
            )
        if target.status != SlotStatus.OPEN:
            raise CarryForwardValidationError(
                "Target slot is not open for booking.",
                errors=["Target slot is not open for booking."],
            )
        return target
    source_slot = booking.slot
    db.session.expire_all()
    candidates = (
        Slot.query.filter(
            Slot.centre_id == centre_id,
            Slot.slot_date == target_date,
            Slot.status == SlotStatus.OPEN,
        )
        .order_by(Slot.start_time.asc())
        .all()
    )
    if not candidates:
        raise CarryForwardValidationError(
            f"No open slots on {target_date.isoformat()}.",
            errors=["No open slots available on the target date."],
        )
    if source_slot is not None:
        same_time = [
            s for s in candidates
            if s.crop_id == source_slot.crop_id
            and s.start_time == source_slot.start_time
        ]
        if same_time:
            return same_time[0]
        same_crop = [s for s in candidates if s.crop_id == source_slot.crop_id]
        if same_crop:
            return same_crop[0]
    return candidates[0]


def _farmer_has_overlap(farmer_id, target):
    rows = (
        Booking.query.join(Slot)
        .filter(
            Booking.farmer_id == farmer_id,
            Slot.slot_date == target.slot_date,
            Booking.status.in_(BookingStatus.active_statuses),
        )
        .all()
    )
    for row in rows:
        other = row.slot
        if other is None:
            continue
        if target.start_time < other.end_time and other.start_time < target.end_time:
            return True
    return False


def _post_commit_side_effects(actor_user, centre_id, target, reason, links):
    for original, new in links:
        try:
            from app.services.smart_queue_pass_service import (
                cancel_pass_for_booking,
                create_pass_for_booking,
            )
            cancel_pass_for_booking(original)
            if new.status == BookingStatus.CONFIRMED:
                create_pass_for_booking(new)
        except Exception:
            pass
        try:
            from app.queue.events import emit_queue_update
            if original.slot is not None:
                emit_queue_update(centre_id=centre_id,
                                  slot_date=original.slot.slot_date,
                                  booking_id=original.id,
                                  reason="BOOKING_CARRIED_FORWARD")
            emit_queue_update(centre_id=centre_id, slot_date=target,
                              booking_id=new.id,
                              reason="BOOKING_CARRIED_FORWARD_CREATED")
        except Exception:
            pass
        try:
            from app.models import NotificationType
            from app.services.notification_service import create_notification
            if original.farmer is not None and original.farmer.user_id:
                create_notification(
                    user_id=original.farmer.user_id,
                    notification_type=NotificationType.BOOKING_CONFIRMED,
                    title="Booking carried forward",
                    message=("Your procurement booking has been carried "
                             f"forward to {target.isoformat()}. "
                             f"New token: {new.token_number}."),
                    booking_id=new.id,
                )
        except Exception:
            pass
        try:
            from app.services.audit_service import create_audit_log
            create_audit_log(
                action="CARRY_FORWARD_BOOKING",
                entity_type="BOOKING",
                entity_id=original.id,
                description=(f"Carried booking #{original.id} forward to "
                             f"{target.isoformat()} as booking #{new.id} "
                             f"({reason})."),
                metadata={
                    "original_booking_id": original.id,
                    "new_booking_id": new.id,
                    "centre_id": centre_id,
                    "original_date": (original.slot.slot_date.isoformat()
                                      if original.slot and original.slot.slot_date
                                      else None),
                    "new_date": target.isoformat(),
                    "reason": reason,
                    "new_token": new.token_number,
                },
                user_id=actor_user.id,
            )
        except Exception:
            pass

def carry_forward_bookings(actor_user, centre_id, booking_ids, target_date,
                           reason, target_slot_id=None):
    from app.models import UserRole
    if actor_user is None or actor_user.role not in (UserRole.STAFF,
                                                     UserRole.ADMIN):
        raise CarryForwardValidationError(
            "Only STAFF or ADMIN may carry bookings forward.",
            errors=["Only STAFF or ADMIN may carry bookings forward."],
        )
    canonical_reason = _normalize_reason(reason)
    target = _parse_target_date(target_date)
    if not isinstance(booking_ids, list) or not booking_ids:
        raise CarryForwardValidationError(
            "booking_ids must be a non-empty list.",
            errors=["booking_ids must be a non-empty list."],
        )
    seen = []
    for raw in booking_ids:
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise CarryForwardValidationError(
                "Each booking_id must be an integer.",
                errors=["Each booking_id must be an integer."],
            )
        if raw not in seen:
            seen.append(raw)
    if target_slot_id is not None and (
        isinstance(target_slot_id, bool) or not isinstance(target_slot_id, int)
    ):
        raise CarryForwardValidationError(
            "target_slot_id must be an integer when provided.",
            errors=["target_slot_id must be an integer when provided."],
        )
    centre = db.session.get(Centre, centre_id)
    if centre is None:
        raise CarryForwardValidationError(
            f"Centre {centre_id} not found.",
            errors=[f"Centre {centre_id} not found."],
        )
    if not centre.is_active:
        raise CarryForwardValidationError(
            "Centre is inactive.", errors=["Centre is inactive."]
        )
    loaded = {}
    for bid in seen:
        booking = db.session.get(Booking, bid)
        if booking is None:
            continue
        slot = booking.slot
        if slot is None or slot.centre_id != centre_id:
            raise CarryForwardValidationError(
                f"Booking {bid} does not belong to centre {centre_id}.",
                errors=[f"Booking {bid} does not belong to centre {centre_id}."],
            )
        loaded[bid] = booking


    src_dates = {b.slot.slot_date for b in loaded.values()
                 if b.slot is not None}
    if len(src_dates) > 1:
        raise CarryForwardValidationError(
            "All bookings must share one procurement date.",
            errors=["All bookings must share one procurement date."],
        )
    src_date = next(iter(src_dates)) if src_dates else None
    if src_date is not None and target != src_date + timedelta(days=1):
        raise CarryForwardValidationError(
            "target_date must be the next day after the original date.",
            errors=["target_date must be the next day after the original date."],
        )
    ok_list = []
    fail_list = []
    links = []
    for bid in seen:
        booking = db.session.get(Booking, bid)
        if booking is None:
            fail_list.append({"booking_id": bid,
                              "reason": "Booking not found.",
                              "code": "NOT_FOUND"})
            continue
        ok, why = check_booking_eligibility(booking, src_date, centre_id)
        if not ok:
            fail_list.append({"booking_id": bid, "reason": why,
                              "code": "NOT_ELIGIBLE"})
            continue
        if src_date is None or target != src_date + timedelta(days=1):
            fail_list.append({"booking_id": bid,
                              "reason": "target_date must be the next day after origin.",
                              "code": "INVALID_TARGET_DATE"})
            continue
        try:
            tgt = _resolve_target_slot(booking, centre_id, target,
                                       target_slot_id)
        except CarryForwardValidationError as exc:
            fail_list.append({"booking_id": bid, "reason": exc.message,
                              "code": "INVALID_TARGET_SLOT"})
            continue
        remain = tgt.capacity - get_active_bookings_count_for_slot(tgt.id)
        if remain <= 0:
            fail_list.append({"booking_id": bid,
                              "reason": (f"Target slot {tgt.id} is full."),
                              "code": "TARGET_SLOT_FULL"})
            continue
        dup = Booking.query.filter(
            Booking.farmer_id == booking.farmer_id,
            Booking.slot_id == tgt.id,
            Booking.status.in_(BookingStatus.active_statuses)).first()
        if dup is not None:
            fail_list.append({"booking_id": bid,
                              "reason": "Farmer already booked target slot.",
                              "code": "DUPLICATE_BOOKING"})
            continue
        if _farmer_has_overlap(booking.farmer_id, tgt):
            fail_list.append({"booking_id": bid,
                              "reason": "Overlapping booking on target date.",
                              "code": "TIME_CONFLICT"})
            continue
        if BookingCarryForward.query.filter_by(
                original_booking_id=booking.id).first() is not None:
            fail_list.append({"booking_id": bid,
                              "reason": "Already carried forward.",
                              "code": "DUPLICATE_CARRY_FORWARD"})
            continue
        sp = db.session.begin_nested()
        try:
            tkn, tkn_now = generate_token_for_booking(tgt)
            new_b = Booking(farmer_id=booking.farmer_id, slot_id=tgt.id,
                            booking_date=datetime.now(timezone.utc),
                            status=BookingStatus.CONFIRMED,
                            token_number=tkn, token_generated_at=tkn_now)
            db.session.add(new_b)
            db.session.flush()
            booking.status = BookingStatus.CARRIED_FORWARD
            rec = BookingCarryForward(
                original_booking_id=booking.id, new_booking_id=new_b.id,
                farmer_id=booking.farmer_id, centre_id=centre_id,
                original_procurement_date=src_date,
                new_procurement_date=target, reason=canonical_reason,
                carried_forward_by=actor_user.id)
            db.session.add(rec)
            db.session.flush()
            sp.commit()
        except IntegrityError:
            sp.rollback()
            fail_list.append({"booking_id": bid,
                              "reason": "Already carried forward.",
                              "code": "DUPLICATE_CARRY_FORWARD"})
            continue
        except Exception as exc:
            sp.rollback()
            fail_list.append({"booking_id": bid,
                              "reason": f"Carry-forward failed: {exc}",
                              "code": "CARRY_FORWARD_FAILED"})
            continue
        ok_list.append({"original_booking_id": booking.id,
                        "new_booking_id": new_b.id, "new_token": tkn,
                        "target_slot_id": tgt.id})
        links.append((booking, new_b))
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise CarryForwardError(f"DB error finalizing: {exc}")
    _post_commit_side_effects(actor_user, centre_id, target, canonical_reason,
                              links)
    return {"source_date": src_date.isoformat() if src_date else None,
            "target_date": target.isoformat(), "reason": canonical_reason,
            "successful": ok_list, "failed": fail_list,
            "successful_count": len(ok_list), "failed_count": len(fail_list)}

