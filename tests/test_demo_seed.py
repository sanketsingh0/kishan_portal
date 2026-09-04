"""Tests for the full SIH demo seeder (``flask seed-demo-full``).

Verifies data creation, idempotency, duplicate protection, staff-centre
assignment, delay ownership, relationship integrity, notification wiring,
audit presence and that the basic ``seed-demo`` command is unchanged.
"""

from datetime import date, time

from app.extensions import db
from app.models import (
    AuditLog,
    Booking,
    Centre,
    Crop,
    Delay,
    Farmer,
    Notification,
    Payment,
    Procurement,
    Slot,
    Staff,
    User,
)
from app.services.full_seed import seed_demo_full
from app.services.seed import seed_demo, DEMO_CENTRES, DEMO_CROPS


TODAY = date.today()


def _counts():
    return {
        "users": User.query.count(),
        "staff": Staff.query.count(),
        "farmers": Farmer.query.count(),
        "centres": Centre.query.count(),
        "crops": Crop.query.count(),
        "slots": Slot.query.count(),
        "bookings": Booking.query.count(),
        "delays": Delay.query.count(),
        "procurements": Procurement.query.count(),
        "payments": Payment.query.count(),
        "notifications": Notification.query.count(),
        "audit_logs": AuditLog.query.count(),
    }


def test_full_seed_creates_required_demo_data(app):
    with app.app_context():
        result = seed_demo_full()
        c = _counts()

        assert c["centres"] == 2
        assert c["crops"] == 6
        assert c["staff"] == 2
        assert c["farmers"] == 5
        assert c["slots"] == 5
        assert c["bookings"] == 5
        assert c["delays"] == 1
        assert c["procurements"] == 5
        assert c["payments"] == 5

        assert result["centres"]["new"] == 2
        assert result["crops"]["new"] == 6
        assert result["staff"]["new"] == 2
        assert result["farmers"]["new"] == 5
        assert result["slots"]["new"] == 5
        assert result["bookings"]["new"] == 5
        assert result["delays"]["new"] == 1
        assert result["procurements"]["new"] == 5
        assert result["payments"]["new"] == 5

        centre_a = Centre.query.filter_by(
            name="KisanProcure Mandi - Ludhiana Grade-A"
        ).first()
        assert centre_a is not None
        assert centre_a.daily_capacity == 200

        centre_b = Centre.query.filter_by(
            name="KisanProcure Mandi - Patiala"
        ).first()
        assert centre_b is not None
        assert centre_b.daily_capacity == 150

        for crop_name in ("Wheat", "Paddy", "Maize", "Gram", "Soybean", "Cotton"):
            assert Crop.query.filter_by(name=crop_name).first() is not None


def test_full_seed_is_idempotent(app):
    with app.app_context():
        seed_demo_full()
        before = _counts()
        seed_demo_full()
        after = _counts()
        assert before == after


def test_no_duplicate_slots(app):
    with app.app_context():
        seed_demo_full()
        total = Slot.query.count()
        distinct = db.session.query(
            Slot.centre_id,
            Slot.crop_id,
            Slot.slot_date,
            Slot.start_time,
            Slot.end_time,
        ).distinct().count()
        assert total == distinct


def test_no_duplicate_bookings_or_tokens(app):
    with app.app_context():
        seed_demo_full()
        total = Booking.query.count()
        distinct_pairs = db.session.query(
            Booking.farmer_id, Booking.slot_id
        ).distinct().count()
        assert total == distinct_pairs

        tokens = [b.token_number for b in Booking.query.all()]
        assert len(tokens) == len(set(tokens))
        assert set(tokens) == {"K-0001", "K-0002", "K-0003", "K-0004", "K-0005"}


def test_staff_assigned_to_correct_centres(app):
    with app.app_context():
        seed_demo_full()
        centre_a = Centre.query.filter_by(
            name="KisanProcure Mandi - Ludhiana Grade-A"
        ).first()
        centre_b = Centre.query.filter_by(
            name="KisanProcure Mandi - Patiala"
        ).first()
        staff_a = Staff.query.filter_by(name="Demo Staff Ludhiana").first()
        staff_b = Staff.query.filter_by(name="Demo Staff Patiala").first()
        assert staff_a.centre_id == centre_a.id
        assert staff_b.centre_id == centre_b.id


def test_delay_belongs_to_centre_a_and_staff(app):
    with app.app_context():
        seed_demo_full()
        centre_a = Centre.query.filter_by(
            name="KisanProcure Mandi - Ludhiana Grade-A"
        ).first()
        staff_a = Staff.query.filter_by(name="Demo Staff Ludhiana").first()
        delay = Delay.query.one()
        assert delay.centre_id == centre_a.id
        assert delay.delay_date == TODAY
        assert delay.delay_minutes == 30
        assert delay.status == "ACTIVE"
        assert delay.created_by == staff_a.user_id


def test_procurement_and_payment_relationships_valid(app):
    with app.app_context():
        seed_demo_full()
        completed = [
            b for b in Booking.query.all() if b.status == "COMPLETED"
        ]
        assert len(completed) == 1
        done_book = completed[0]
        assert done_book.procurement.procurement_status == "COMPLETED"
        assert done_book.procurement.quantity == 22.0
        assert done_book.procurement.unit == "quintal"
        assert done_book.payment.payment_status == "PAID"
        assert done_book.payment.payment_reference == "DEMO-PAY-001"
        assert done_book.payment.payment_date == TODAY

        in_progress = [
            b for b in Booking.query.all()
            if b.procurement.procurement_status == "IN_PROGRESS"
        ]
        assert len(in_progress) == 1
        assert in_progress[0].payment.payment_status == "PROCESSING"

        waiting = [
            b for b in Booking.query.all()
            if b.procurement.procurement_status == "PENDING"
        ]
        assert len(waiting) == 3
        assert all(b.payment.payment_status == "PENDING" for b in waiting)


def test_notifications_belong_to_correct_users(app):
    with app.app_context():
        seed_demo_full()
        farming_users = {
            u.id for u in User.query.filter_by(role="FARMER").all()
        }
        active_bookings = [
            b for b in Booking.query.all() if b.status == "CONFIRMED"
        ]
        for booking in active_bookings:
            all_notifs = Notification.query.filter_by(
                booking_id=booking.id
            ).all()
            assert any(
                n.notification_type == "BOOKING_CONFIRMED" for n in all_notifs
            )
            assert all(n.user_id == booking.farmer.user_id for n in all_notifs)
            assert booking.farmer.user_id in farming_users

        types = {n.notification_type for n in Notification.query.all()}
        assert "BOOKING_CONFIRMED" in types
        assert "QUEUE_UPDATE" in types
        assert "DELAY_UPDATE" in types
        assert "PROCUREMENT_UPDATE" in types
        assert "PAYMENT_UPDATE" in types


def test_audit_records_valid(app):
    with app.app_context():
        seed_demo_full()
        actions = {a.action for a in AuditLog.query.all()}
        assert "CREATE_CENTRE" in actions
        assert "ASSIGN_STAFF" in actions
        assert "CREATE_SLOT" in actions
        assert "CREATE_DELAY" in actions
        assert "CREATE_PROCUREMENT" in actions
        assert "CREATE_PAYMENT" in actions


def test_seed_demo_behavior_unchanged(app):
    with app.app_context():
        stats = seed_demo()
        assert stats["centres"] == len(DEMO_CENTRES)
        assert stats["crops"] == len(DEMO_CROPS)

        names = {c.name for c in Centre.query.all()}
        assert names == {m["name"] for m in DEMO_CENTRES}
        crop_names = {c.name for c in Crop.query.all()}
        assert crop_names == {m["name"] for m in DEMO_CROPS}

        # seed-demo does not create farmers, staff, bookings, etc.
        assert Farmer.query.count() == 0
        assert Staff.query.count() == 0
        assert Booking.query.count() == 0

    # Running full seed after seed-demo still succeeds and reuses crops.
    with app.app_context():
        seed_demo_full()
        assert Crop.query.count() == 6