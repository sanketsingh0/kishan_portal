"""Full SIH demo seed (flask seed-demo-full).

Creates a complete fictional demo dataset. Idempotent, non-destructive.
No passwords stored, no Supabase Auth contacted, no external services.
"""

from datetime import date, time

from app.extensions import db
from app.models import (
    AuditLog,
    Booking,
    BookingStatus,
    Centre,
    Crop,
    Delay,
    DelayStatus,
    Farmer,
    Notification,
    NotificationType,
    Payment,
    PaymentStatus,
    Procurement,
    ProcurementStatus,
    Slot,
    SlotStatus,
    Staff,
    User,
    UserRole,
)
from app.services.centre_service import create_centre
from app.services.slot_service import create_slot
from app.services.booking_service import create_booking
from app.services.procurement_service import create_procurement
from app.services.payment_service import create_payment
from app.services.delay_service import create_delay
from app.services.notification_service import create_notification

T0800 = time(8, 0)
T0900 = time(9, 0)
T1000 = time(10, 0)
T1100 = time(11, 0)
T1200 = time(12, 0)
T1300 = time(13, 0)
T1700 = time(17, 0)
T1800 = time(18, 0)

CENTRE_A = {
    "name": "KisanProcure Mandi - Ludhiana Grade-A",
    "location": "Focal Point Road, Ludhiana, Punjab (demo)",
    "opening_time": T0800,
    "closing_time": T1700,
    "daily_capacity": 200,
    "average_processing_minutes": 15,
    "is_active": True,
}

CENTRE_B = {
    "name": "KisanProcure Mandi - Patiala",
    "location": "Demo Agricultural Yard, Patiala, Punjab (demo)",
    "opening_time": T0900,
    "closing_time": T1800,
    "daily_capacity": 150,
    "average_processing_minutes": 15,
    "is_active": True,
}

FULL_DEMO_CROPS = (
    {"name": "Wheat", "category": "Cereals"},
    {"name": "Paddy", "category": "Cereals"},
    {"name": "Maize", "category": "Cereals"},
    {"name": "Gram", "category": "Pulses"},
    {"name": "Soybean", "category": "Oilseeds"},
    {"name": "Cotton", "category": "Fibre"},
)

STAFF_A = {"name": "Demo Staff Ludhiana", "phone": "9990000001", "centre": "A"}
STAFF_B = {"name": "Demo Staff Patiala", "phone": "9990000002", "centre": "B"}

DEMO_FARMERS = (
    {
        "name": "Ravinder Singh",
        "phone": "9999900001",
        "address": "Village Rampur, Ludhiana (demo)",
        "city": "Ludhiana",
        "state": "Punjab",
        "pincode": "141001",
    },
    {
        "name": "Amarjeet Kaur",
        "phone": "9999900002",
        "address": "Village Dhaula, Ludhiana (demo)",
        "city": "Ludhiana",
        "state": "Punjab",
        "pincode": "141001",
    },
    {
        "name": "Gurpreet Sandhu",
        "phone": "9999900003",
        "address": "Village Kila Raipur (demo)",
        "city": "Ludhiana",
        "state": "Punjab",
        "pincode": "141008",
    },
    {
        "name": "Manjeet Gill",
        "phone": "9999900004",
        "address": "Village Mullanpur (demo)",
        "city": "Ludhiana",
        "state": "Punjab",
        "pincode": "141101",
    },
    {
        "name": "Harpreet Brar",
        "phone": "9999900005",
        "address": "Village Talwandi (demo)",
        "city": "Ludhiana",
        "state": "Punjab",
        "pincode": "141202",
    },
)

SLOT_SPECS = (
    {"centre": "A", "crop": "Wheat", "start": T0800, "end": T1000, "capacity": 50},
    {"centre": "A", "crop": "Wheat", "start": T1000, "end": T1200, "capacity": 50},
    {"centre": "A", "crop": "Paddy", "start": T0900, "end": T1100, "capacity": 40},
    {"centre": "A", "crop": "Gram", "start": T1100, "end": T1300, "capacity": 30},
    {"centre": "B", "crop": "Soybean", "start": T1000, "end": T1200, "capacity": 40},
)

BOOKING_PLAN = (
    {
        "farmer": 0,
        "crop": "Wheat",
        "slot": "T0800_T1000",
        "booking_status": BookingStatus.CONFIRMED,
        "procurement_status": ProcurementStatus.PENDING,
        "payment_status": PaymentStatus.PENDING,
    },
    {
        "farmer": 1,
        "crop": "Wheat",
        "slot": "T0800_T1000",
        "booking_status": BookingStatus.CONFIRMED,
        "procurement_status": ProcurementStatus.PENDING,
        "payment_status": PaymentStatus.PENDING,
    },
    {
        "farmer": 2,
        "crop": "Wheat",
        "slot": "T1000_T1200",
        "booking_status": BookingStatus.CONFIRMED,
        "procurement_status": ProcurementStatus.PENDING,
        "payment_status": PaymentStatus.PENDING,
    },
    {
        "farmer": 3,
        "crop": "Paddy",
        "slot": "T0900_T1100",
        "booking_status": BookingStatus.CONFIRMED,
        "procurement_status": ProcurementStatus.IN_PROGRESS,
        "payment_status": PaymentStatus.PROCESSING,
    },
    {
        "farmer": 4,
        "crop": "Gram",
        "slot": "T1100_T1300",
        "booking_status": BookingStatus.COMPLETED,
        "procurement_status": ProcurementStatus.COMPLETED,
        "quantity": 22.0,
        "unit": "quintal",
        "remarks": "Quality checked at weighbridge - demo procurement",
        "payment_status": PaymentStatus.PAID,
        "amount": 38500.00,
        "payment_reference": "DEMO-PAY-001",
        "payment_remarks": "Demo settlement - no real gateway used",
    },
)

DELAY_REASON = "Weighbridge calibration - demonstration delay"
DELAY_MINUTES = 30

QUEUE_UPDATE_TITLE = "Queue Updated"
QUEUE_UPDATE_MESSAGE = "Your queue position has been updated. Keep your token handy."


def _empty_stats():
    return {
        "centres": {"new": 0, "existing": 0},
        "crops": {"new": 0, "existing": 0},
        "staff": {"new": 0, "existing": 0},
        "farmers": {"new": 0, "existing": 0},
        "slots": {"new": 0, "existing": 0},
        "bookings": {"new": 0, "existing": 0},
        "delays": {"new": 0, "existing": 0},
        "procurements": {"new": 0, "existing": 0},
        "payments": {"new": 0, "existing": 0},
    }


def seed_demo_full():
    stats = _empty_stats()
    today = date.today()

    notif_before = Notification.query.count()
    audit_before = AuditLog.query.count()

    crops = {}
    for payload in FULL_DEMO_CROPS:
        crop = Crop.query.filter_by(name=payload["name"]).first()
        if crop is None:
            crop = Crop(
                name=payload["name"],
                category=payload["category"],
                is_active=True,
            )
            db.session.add(crop)
            db.session.flush()
            stats["crops"]["new"] += 1
        else:
            stats["crops"]["existing"] += 1
        crops[payload["name"]] = crop
    db.session.commit()

    centres = {}
    for key, payload in (("A", CENTRE_A), ("B", CENTRE_B)):
        centre = Centre.query.filter_by(name=payload["name"]).first()
        if centre is None:
            centre = create_centre(payload)
            stats["centres"]["new"] += 1
        else:
            stats["centres"]["existing"] += 1
        centres[key] = centre

    staff_records = {}
    for key, payload in (("A", STAFF_A), ("B", STAFF_B)):
        staff = Staff.query.filter_by(name=payload["name"]).first()
        centre_id = centres[payload["centre"]].id
        if staff is None:
            user = User(
                supabase_user_id=None,
                role=UserRole.STAFF,
                is_active=True,
            )
            db.session.add(user)
            db.session.flush()
            staff = Staff(
                user_id=user.id,
                name=payload["name"],
                phone=payload["phone"],
                centre_id=centre_id,
            )
            db.session.add(staff)
            db.session.flush()
            db.session.add(
                AuditLog(
                    user_id=user.id,
                    action="ASSIGN_STAFF",
                    entity_type="STAFF",
                    entity_id=staff.id,
                    description="Assigned demo staff",
                    metadata_json={"centre_id": centre_id},
                )
            )
            db.session.commit()
            stats["staff"]["new"] += 1
        else:
            stats["staff"]["existing"] += 1
        staff_records[key] = staff

    farmers = []
    for payload in DEMO_FARMERS:
        farmer = Farmer.query.filter_by(phone=payload["phone"]).first()
        if farmer is None:
            user = User(
                supabase_user_id=None,
                role=UserRole.FARMER,
                is_active=True,
            )
            db.session.add(user)
            db.session.flush()
            farmer = Farmer(
                user_id=user.id,
                name=payload["name"],
                phone=payload["phone"],
                address=payload.get("address"),
                city=payload.get("city"),
                state=payload.get("state"),
                pincode=payload.get("pincode"),
            )
            db.session.add(farmer)
            db.session.commit()
            stats["farmers"]["new"] += 1
        else:
            stats["farmers"]["existing"] += 1
        farmers.append(farmer)

    slots_by_spec = {}
    for spec in SLOT_SPECS:
        centre = centres[spec["centre"]]
        crop = crops[spec["crop"]]
        slot = Slot.query.filter_by(
            centre_id=centre.id,
            crop_id=crop.id,
            slot_date=today,
            start_time=spec["start"],
            end_time=spec["end"],
        ).first()
        if slot is None:
            slot = create_slot(
                {
                    "centre_id": centre.id,
                    "crop_id": crop.id,
                    "slot_date": today.isoformat(),
                    "start_time": spec["start"].strftime("%H:%M"),
                    "end_time": spec["end"].strftime("%H:%M"),
                    "capacity": spec["capacity"],
                    "status": SlotStatus.OPEN,
                }
            )
            stats["slots"]["new"] += 1
        else:
            stats["slots"]["existing"] += 1
        slots_by_spec[(spec["centre"], spec["crop"], spec["start"], spec["end"])] = slot

    time_by_name = {
        "T0800": T0800,
        "T0900": T0900,
        "T1000": T1000,
        "T1100": T1100,
        "T1200": T1200,
        "T1300": T1300,
    }

    bookings = []
    for plan in BOOKING_PLAN:
        farmer = farmers[plan["farmer"]]
        start_key = plan["slot"].split("_")[0]
        end_key = plan["slot"].split("_")[1]
        slot = slots_by_spec[("A", plan["crop"], time_by_name[start_key], time_by_name[end_key])]

        booking = Booking.query.filter_by(farmer_id=farmer.id, slot_id=slot.id).first()
        if booking is None:
            booking = create_booking(farmer.user_id, slot.id)
            stats["bookings"]["new"] += 1
        else:
            stats["bookings"]["existing"] += 1

        if booking.status != plan["booking_status"]:
            booking.status = plan["booking_status"]
            db.session.commit()

        bookings.append(booking)

        if booking.procurement is None:
            create_procurement(
                booking.id,
                {
                    "procurement_status": plan["procurement_status"],
                    "quantity": plan.get("quantity"),
                    "unit": plan.get("unit", "quintal"),
                    "procurement_date": today.isoformat(),
                    "remarks": plan.get("remarks"),
                },
            )
            stats["procurements"]["new"] += 1
        else:
            stats["procurements"]["existing"] += 1

        if booking.payment is None:
            create_payment(
                booking.id,
                {
                    "payment_status": plan["payment_status"],
                    "amount": plan.get("amount"),
                    "payment_reference": plan.get("payment_reference"),
                    "payment_date": today.isoformat(),
                    "remarks": plan.get("payment_remarks"),
                },
            )
            stats["payments"]["new"] += 1
        else:
            stats["payments"]["existing"] += 1

    existing_delay = Delay.query.filter_by(
        centre_id=centres["A"].id,
        delay_date=today,
        status=DelayStatus.ACTIVE,
        delay_minutes=DELAY_MINUTES,
    ).first()
    if existing_delay is None:
        create_delay(
            {
                "centre_id": centres["A"].id,
                "delay_date": today.isoformat(),
                "delay_minutes": DELAY_MINUTES,
                "reason": DELAY_REASON,
                "status": DelayStatus.ACTIVE,
            },
            current_user_id=staff_records["A"].user_id,
        )
        stats["delays"]["new"] += 1
    else:
        stats["delays"]["existing"] += 1

    for booking in bookings:
        if booking.status not in BookingStatus.active_statuses:
            continue
        user_id = booking.farmer.user_id if booking.farmer else None
        if not user_id:
            continue
        exists = Notification.query.filter_by(
            user_id=user_id,
            notification_type=NotificationType.QUEUE_UPDATE,
            title=QUEUE_UPDATE_TITLE,
            message=QUEUE_UPDATE_MESSAGE,
            booking_id=booking.id,
        ).first()
        if exists is None:
            create_notification(
                user_id=user_id,
                notification_type=NotificationType.QUEUE_UPDATE,
                title=QUEUE_UPDATE_TITLE,
                message=QUEUE_UPDATE_MESSAGE,
                booking_id=booking.id,
            )

    notif_after = Notification.query.count()
    audit_after = AuditLog.query.count()
    stats["notifications"] = {
        "new": notif_after - notif_before,
        "existing": notif_before,
        "total": notif_after,
    }
    stats["audit_logs"] = {
        "new": audit_after - audit_before,
        "existing": audit_before,
        "total": audit_after,
    }

    for label in (
        "centres",
        "crops",
        "staff",
        "farmers",
        "slots",
        "bookings",
        "delays",
        "procurements",
        "payments",
    ):
        stats[label]["total"] = stats[label]["new"] + stats[label]["existing"]

    return stats