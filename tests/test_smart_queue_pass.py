"""Tests for the Smart Queue Pass (SIH 26032 - QR-based digital mandi entry pass).

Stage 1 scope: pass model, secure pass identifier, ACTIVE/VERIFIED/CANCELLED
lifecycle, booking/cancellation integration, staff centre isolation, verification
API, audit logging.

Covered:
A. Pass model can be created.                    N. ACTIVE -> VERIFIED.
B. booking_id uniqueness.                        O. verified_at recorded.
C. Secure pass identifier uniqueness.            P. verified_by recorded.
D. Pass starts ACTIVE.                           Q. verification_centre_id recorded.
E. Confirmed booking creates one pass.           R. Re-verification -> 409.
F. Duplicate creation is idempotent.             S. Cancelled pass rejected.
G. Farmer retrieves own pass.                    T. Completed booking rejected.
H. Farmer cannot read another farmer's pass.     U. Rejected procurement rejected.
I. Farmer cannot verify.                         V. Unknown pass -> 404.
J. Assigned STAFF verifies own centre.           W. Verification does not complete procurement.
K. STAFF cannot verify another centre (403).     X. Cancellation cancels ACTIVE pass.
L. Unassigned STAFF -> 403.                      Y. Audit log written.
M. ADMIN verifies any centre (system-wide).      Z. Cross-centre / role security rules.

All tests run against the isolated in-memory SQLite database from
tests/conftest.py; no real database, no .env access and no seed scripts.
"""

import re
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    AuditLog,
    Booking,
    BookingStatus,
    Centre,
    Crop,
    Farmer,
    Procurement,
    ProcurementStatus,
    Slot,
    SlotStatus,
    SmartQueuePass,
    SmartQueuePassStatus,
    Staff,
    User,
    UserRole,
)
from app.services.smart_queue_pass_service import (
    create_pass_for_booking,
    generate_secure_pass_id,
    get_or_create_pass_for_booking,
)


def make_call(client, method, url, sub_id, json_data=None):
    """Helper to mock Supabase token verification and execute a request."""
    with patch("app.auth.decorators.verify_token") as mock_vt:
        mock_user = MagicMock()
        mock_user.id = sub_id
        mock_vt.return_value = mock_user

        headers = {"Authorization": "Bearer mock-token"}
        if method.upper() == "GET":
            return client.get(url, headers=headers)
        if method.upper() == "POST":
            return client.post(url, json=json_data, headers=headers)
        if method.upper() == "PUT":
            return client.put(url, json=json_data, headers=headers)
        if method.upper() == "DELETE":
            return client.delete(url, headers=headers)
        raise AssertionError(f"Unsupported method {method}")


def pass_snapshot(app, booking_id):
    """Read the pass row of a booking as plain values (fresh from the database)."""
    with app.app_context():
        db.session.expire_all()
        row = SmartQueuePass.query.filter_by(booking_id=booking_id).first()
        if row is None:
            return None
        return {
            "id": row.id,
            "pass_id": row.secure_pass_id,
            "status": row.status,
            "verified_at": row.verified_at,
            "verified_by": row.verified_by,
            "verification_centre_id": row.verification_centre_id,
        }


def pass_count(app):
    """Total number of Smart Queue Pass rows."""
    with app.app_context():
        db.session.expire_all()
        return SmartQueuePass.query.count()


def booking_status(app, booking_id):
    with app.app_context():
        db.session.expire_all()
        booking = db.session.get(Booking, booking_id)
        return booking.status if booking else None


def audit_entries(app, action):
    """Audit log entries for one action, as plain dictionaries."""
    with app.app_context():
        db.session.expire_all()
        return [
            {
                "user_id": log.user_id,
                "entity_type": log.entity_type,
                "entity_id": log.entity_id,
                "description": log.description,
                "metadata": log.metadata_json or {},
            }
            for log in AuditLog.query.filter_by(action=action).all()
        ]


@pytest.fixture
def pass_setup(app):
    """Centre A/B, staff (assigned + unassigned), admin, farmers, slots, bookings.

    Bookings are inserted directly (as demo/seed data is), so the lazy pass
    creation path is exercised too. ``slot_c`` stays unbooked for the
    booking-API test.
    """
    with app.app_context():
        db.session.query(AuditLog).delete()
        db.session.query(SmartQueuePass).delete()
        db.session.query(Procurement).delete()
        db.session.query(Booking).delete()
        db.session.query(Slot).delete()
        db.session.query(Farmer).delete()
        db.session.query(Staff).delete()
        db.session.query(Crop).delete()
        db.session.query(Centre).delete()
        db.session.query(User).delete()
        db.session.commit()

        u_farmer1 = User(supabase_user_id="user-pass-farmer1", role=UserRole.FARMER, is_active=True)
        u_farmer2 = User(supabase_user_id="user-pass-farmer2", role=UserRole.FARMER, is_active=True)
        u_staff_a = User(supabase_user_id="user-pass-staff-a", role=UserRole.STAFF, is_active=True)
        u_staff_b = User(supabase_user_id="user-pass-staff-b", role=UserRole.STAFF, is_active=True)
        u_staff_none = User(supabase_user_id="user-pass-staff-none", role=UserRole.STAFF, is_active=True)
        u_admin = User(supabase_user_id="user-pass-admin", role=UserRole.ADMIN, is_active=True)
        db.session.add_all([u_farmer1, u_farmer2, u_staff_a, u_staff_b, u_staff_none, u_admin])
        db.session.commit()

        c_a = Centre(name="Pass Test Centre A", location="Ludhiana",
                     daily_capacity=100, average_processing_minutes=15, is_active=True)
        c_b = Centre(name="Pass Test Centre B", location="Patiala",
                     daily_capacity=100, average_processing_minutes=15, is_active=True)
        crop = Crop(name="Pass Test Wheat", is_active=True)
        db.session.add_all([c_a, c_b, crop])
        db.session.commit()

        staff_a = Staff(user_id=u_staff_a.id, name="Pass Staff A", centre_id=c_a.id)
        staff_b = Staff(user_id=u_staff_b.id, name="Pass Staff B", centre_id=c_b.id)
        staff_none = Staff(user_id=u_staff_none.id, name="Pass Staff Unassigned", centre_id=None)
        farmer1 = Farmer(user_id=u_farmer1.id, name="Pass Farmer One", phone="9876500101")
        farmer2 = Farmer(user_id=u_farmer2.id, name="Pass Farmer Two", phone="9876500102")
        db.session.add_all([staff_a, staff_b, staff_none, farmer1, farmer2])
        db.session.commit()

        slot_date = date.today() + timedelta(days=1)
        slot_a = Slot(centre_id=c_a.id, crop_id=crop.id, slot_date=slot_date,
                      start_time=time(9, 0), end_time=time(10, 0),
                      capacity=10, status=SlotStatus.OPEN)
        slot_b = Slot(centre_id=c_b.id, crop_id=crop.id, slot_date=slot_date,
                      start_time=time(9, 0), end_time=time(10, 0),
                      capacity=10, status=SlotStatus.OPEN)
        slot_c = Slot(centre_id=c_a.id, crop_id=crop.id, slot_date=slot_date,
                      start_time=time(11, 0), end_time=time(12, 0),
                      capacity=10, status=SlotStatus.OPEN)
        db.session.add_all([slot_a, slot_b, slot_c])
        db.session.commit()

        b_a1 = Booking(farmer_id=farmer1.id, slot_id=slot_a.id,
                       status=BookingStatus.CONFIRMED, token_number="K-0001")
        b_b1 = Booking(farmer_id=farmer2.id, slot_id=slot_b.id,
                       status=BookingStatus.CONFIRMED, token_number="K-0002")
        db.session.add_all([b_a1, b_b1])
        db.session.commit()

        yield {
            "centre_a_id": c_a.id,
            "centre_b_id": c_b.id,
            "slot_a_id": slot_a.id,
            "slot_c_id": slot_c.id,
            "booking_a1_id": b_a1.id,
            "booking_b1_id": b_b1.id,
            "slot_date": slot_date,
            "farmer1_sub": u_farmer1.supabase_user_id,
            "farmer2_sub": u_farmer2.supabase_user_id,
            "farmer1_user_id": u_farmer1.id,
            "staff_a_sub": u_staff_a.supabase_user_id,
            "staff_a_user_id": u_staff_a.id,
            "staff_b_sub": u_staff_b.supabase_user_id,
            "staff_none_sub": u_staff_none.supabase_user_id,
            "admin_sub": u_admin.supabase_user_id,
            "admin_user_id": u_admin.id,
        }


def create_pass_directly(app, booking_id) -> str:
    """Create the pass for a booking through the service and return its pass id.

    The booking fixtures are inserted directly (as demo/seed data is), so this
    mirrors the pass that the booking flow would already have created.
    """
    with app.app_context():
        booking = db.session.get(Booking, booking_id)
        return create_pass_for_booking(booking).secure_pass_id


def set_booking_status(booking_id, status) -> None:
    """Update a booking status on the active session.

    The `app` fixture keeps an application context (and therefore the session
    that also serves the test request) alive, so the mutation must be made
    through that session - otherwise the request would read a stale,
    identity-mapped booking.
    """
    booking = db.session.get(Booking, booking_id)
    booking.status = status
    db.session.commit()


def set_pass_status(booking_id, status) -> None:
    """Update a pass status on the active session (see set_booking_status)."""
    row = SmartQueuePass.query.filter_by(booking_id=booking_id).first()
    row.status = status
    db.session.commit()


# --- A/B/C/D: model, constraints and initial state --------------------------


def test_a_pass_model_can_be_created(app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]
    with app.app_context():
        booking = db.session.get(Booking, booking_id)
        pass_row = create_pass_for_booking(booking)

        assert isinstance(pass_row, SmartQueuePass)
        assert pass_row.id is not None
        assert pass_row.booking_id == booking.id
        assert pass_row.secure_pass_id.startswith("kp_pass_")
        assert pass_row.created_at is not None
        assert pass_row.updated_at is not None

        db.session.expire_all()
        stored = db.session.get(SmartQueuePass, pass_row.id)
        # Booking 1 --- 1 SmartQueuePass (both directions)
        assert stored.booking.id == booking_id
        assert stored.booking.smart_queue_pass.id == stored.id


def test_b_booking_id_must_be_unique(app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]
    with app.app_context():
        create_pass_for_booking(db.session.get(Booking, booking_id))
        # A second pass row for the same booking must be rejected by the database.
        db.session.add(
            SmartQueuePass(
                booking_id=booking_id,
                secure_pass_id=generate_secure_pass_id(),
                status=SmartQueuePassStatus.ACTIVE,
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    assert pass_count(app) == 1


def test_c_secure_pass_identifier_must_be_unique(app, pass_setup):
    with app.app_context():
        first = create_pass_for_booking(db.session.get(Booking, pass_setup["booking_a1_id"]))
        duplicate_identifier = first.secure_pass_id
        db.session.add(
            SmartQueuePass(
                booking_id=pass_setup["booking_b1_id"],
                secure_pass_id=duplicate_identifier,
                status=SmartQueuePassStatus.ACTIVE,
            )
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

    assert pass_count(app) == 1


def test_d_pass_starts_active(app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]
    create_pass_directly(app, booking_id)

    snapshot = pass_snapshot(app, booking_id)
    assert snapshot["status"] == SmartQueuePassStatus.ACTIVE
    assert snapshot["verified_at"] is None
    assert snapshot["verified_by"] is None
    assert snapshot["verification_centre_id"] is None


def test_pass_identifier_is_random_url_safe_and_non_sequential(app):
    with app.app_context():
        identifiers = [generate_secure_pass_id() for _ in range(25)]

    assert len(set(identifiers)) == 25  # never repeats
    for value in identifiers:
        assert re.fullmatch(r"kp_pass_[A-Za-z0-9_\-]{40,}", value)
        # Not a queue token, not a raw numeric id, no embedded separators.
        assert not re.fullmatch(r"K-\d+", value)
        assert not value.removeprefix("kp_pass_").isdigit()


# --- E/F: booking integration and idempotency -------------------------------


def test_e_confirmed_booking_creates_exactly_one_pass(client, app, pass_setup):
    res = make_call(
        client, "POST", "/api/bookings",
        pass_setup["farmer1_sub"], {"slot_id": pass_setup["slot_c_id"]},
    )
    assert res.status_code == 201
    booking = res.get_json()["booking"]
    assert booking["status"] == BookingStatus.CONFIRMED

    snapshot = pass_snapshot(app, booking["id"])
    assert snapshot is not None
    assert snapshot["status"] == SmartQueuePassStatus.ACTIVE
    assert pass_count(app) == 1


def test_f_pass_creation_is_idempotent(app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]
    with app.app_context():
        booking = db.session.get(Booking, booking_id)
        first = create_pass_for_booking(booking)
        first_identifier = first.secure_pass_id

        second = create_pass_for_booking(booking)
        third = get_or_create_pass_for_booking(booking)

        assert second.secure_pass_id == first_identifier
        assert third.secure_pass_id == first_identifier

    assert pass_count(app) == 1


# --- G/H/I: farmer access rules ---------------------------------------------


def test_g_farmer_can_retrieve_own_pass(client, app, pass_setup):
    assert pass_count(app) == 0  # booking inserted directly: pass created lazily

    res = make_call(
        client, "GET", f"/api/queue-pass/my/{pass_setup['booking_a1_id']}",
        pass_setup["farmer1_sub"],
    )
    assert res.status_code == 200

    payload = res.get_json()["smart_queue_pass"]
    assert payload["pass_id"].startswith("kp_pass_")
    assert payload["status"] == SmartQueuePassStatus.ACTIVE
    assert payload["entry_verified"] is False
    assert payload["booking"]["id"] == pass_setup["booking_a1_id"]
    assert payload["booking"]["token_number"] == "K-0001"
    assert payload["farmer"]["name"] == "Pass Farmer One"
    assert payload["centre"]["id"] == pass_setup["centre_a_id"]
    assert payload["crop"]["name"] == "Pass Test Wheat"
    assert payload["slot"]["slot_date"] == pass_setup["slot_date"].isoformat()
    assert payload["slot"]["start_time"] == "09:00"
    assert payload["slot"]["end_time"] == "10:00"
    assert pass_count(app) == 1  # exactly one pass, created on demand


def test_h_farmer_cannot_retrieve_another_farmers_pass(client, app, pass_setup):
    res = make_call(
        client, "GET", f"/api/queue-pass/my/{pass_setup['booking_a1_id']}",
        pass_setup["farmer2_sub"],
    )
    assert res.status_code == 404
    assert "smart_queue_pass" not in res.get_json()
    # No pass is created or disclosed for another farmer's booking.
    assert pass_count(app) == 0


def test_i_farmer_cannot_verify_a_pass(client, app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]
    secure_id = create_pass_directly(app, booking_id)

    res = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["farmer1_sub"], {"pass_id": secure_id},
    )
    assert res.status_code == 403

    snapshot = pass_snapshot(app, booking_id)
    assert snapshot["status"] == SmartQueuePassStatus.ACTIVE
    assert snapshot["verified_at"] is None


def test_farmer_cannot_lookup_passes(client, app, pass_setup):
    secure_id = create_pass_directly(app, pass_setup["booking_a1_id"])
    res = make_call(
        client, "GET", f"/api/queue-pass/lookup/{secure_id}", pass_setup["farmer1_sub"]
    )
    assert res.status_code == 403


# --- J/K/L/M: staff centre isolation, unassigned staff and admin -------------


def test_j_assigned_staff_can_verify_pass_of_own_centre(client, app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]
    secure_id = create_pass_directly(app, booking_id)

    res = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_a_sub"], {"pass_id": secure_id},
    )
    assert res.status_code == 200

    payload = res.get_json()["smart_queue_pass"]
    assert payload["status"] == SmartQueuePassStatus.VERIFIED
    assert payload["entry_verified"] is True
    assert payload["verification_centre_id"] == pass_setup["centre_a_id"]

    snapshot = pass_snapshot(app, booking_id)
    assert snapshot["status"] == SmartQueuePassStatus.VERIFIED


def test_k_staff_cannot_verify_pass_of_another_centre(client, app, pass_setup):
    booking_id = pass_setup["booking_b1_id"]
    secure_id = create_pass_directly(app, booking_id)

    # STAFF of centre A -> centre B pass: forbidden, nothing is written.
    denied = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_a_sub"], {"pass_id": secure_id},
    )
    assert denied.status_code == 403
    snapshot = pass_snapshot(app, booking_id)
    assert snapshot["status"] == SmartQueuePassStatus.ACTIVE
    assert snapshot["verified_by"] is None
    assert snapshot["verification_centre_id"] is None

    # The centre B staff member may verify it.
    allowed = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_b_sub"], {"pass_id": secure_id},
    )
    assert allowed.status_code == 200
    assert pass_snapshot(app, booking_id)["status"] == SmartQueuePassStatus.VERIFIED


def test_l_unassigned_staff_cannot_verify_or_lookup(client, app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]
    secure_id = create_pass_directly(app, booking_id)

    verify = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_none_sub"], {"pass_id": secure_id},
    )
    assert verify.status_code == 403

    lookup = make_call(
        client, "GET", f"/api/queue-pass/lookup/{secure_id}", pass_setup["staff_none_sub"]
    )
    assert lookup.status_code == 403

    assert pass_snapshot(app, booking_id)["status"] == SmartQueuePassStatus.ACTIVE


def test_m_admin_can_verify_any_centre(client, app, pass_setup):
    booking_id = pass_setup["booking_b1_id"]
    secure_id = create_pass_directly(app, booking_id)

    res = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["admin_sub"], {"pass_id": secure_id},
    )
    assert res.status_code == 200

    snapshot = pass_snapshot(app, booking_id)
    assert snapshot["status"] == SmartQueuePassStatus.VERIFIED
    assert snapshot["verified_by"] == pass_setup["admin_user_id"]
    assert snapshot["verification_centre_id"] == pass_setup["centre_b_id"]


# --- N/O/P/Q: recorded verification data ------------------------------------


def test_n_to_q_verification_records_status_time_actor_and_centre(client, app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]
    secure_id = create_pass_directly(app, booking_id)

    before = datetime.now(timezone.utc)
    res = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_a_sub"], {"pass_id": secure_id},
    )
    after = datetime.now(timezone.utc)
    assert res.status_code == 200

    snapshot = pass_snapshot(app, booking_id)

    # N: ACTIVE -> VERIFIED
    assert snapshot["status"] == SmartQueuePassStatus.VERIFIED
    # O: verified_at is recorded (SQLite stores it without a tz label)
    assert snapshot["verified_at"] is not None
    verified_at = snapshot["verified_at"]
    if verified_at.tzinfo is not None:
        assert before <= verified_at <= after
    else:
        assert before.replace(tzinfo=None) <= verified_at <= after.replace(tzinfo=None)
    # P: verified_by is the authenticated STAFF user
    assert snapshot["verified_by"] == pass_setup["staff_a_user_id"]
    # Q: verification_centre_id is the operating centre
    assert snapshot["verification_centre_id"] == pass_setup["centre_a_id"]


# --- R/S/T/U/V/W/X/Y/Z: lifecycle guard rails -------------------------------


def test_r_already_verified_pass_cannot_be_verified_again(client, app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]
    secure_id = create_pass_directly(app, booking_id)

    first = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_a_sub"], {"pass_id": secure_id},
    )
    assert first.status_code == 200
    verified_at_before = pass_snapshot(app, booking_id)["verified_at"]

    second = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_a_sub"], {"pass_id": secure_id},
    )
    assert second.status_code == 409
    assert second.get_json()["code"] == "PASS_CONFLICT"

    snapshot = pass_snapshot(app, booking_id)
    assert snapshot["status"] == SmartQueuePassStatus.VERIFIED
    assert snapshot["verified_at"] == verified_at_before  # untouched
    assert snapshot["verified_by"] == pass_setup["staff_a_user_id"]


def test_s_cancelled_pass_cannot_be_verified(client, app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]
    secure_id = create_pass_directly(app, booking_id)

    set_pass_status(booking_id, SmartQueuePassStatus.CANCELLED)

    res = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_a_sub"], {"pass_id": secure_id},
    )
    assert res.status_code == 409
    assert pass_snapshot(app, booking_id)["status"] == SmartQueuePassStatus.CANCELLED


def test_t_completed_booking_cannot_be_verified(client, app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]
    secure_id = create_pass_directly(app, booking_id)

    set_booking_status(booking_id, BookingStatus.COMPLETED)

    res = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_a_sub"], {"pass_id": secure_id},
    )
    assert res.status_code == 409
    assert pass_snapshot(app, booking_id)["status"] == SmartQueuePassStatus.ACTIVE


def test_u_rejected_procurement_booking_cannot_be_verified(client, app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]
    secure_id = create_pass_directly(app, booking_id)

    db.session.add(Procurement(
        booking_id=booking_id,
        procurement_status=ProcurementStatus.REJECTED,
        procurement_date=pass_setup["slot_date"],
    ))
    db.session.commit()

    res = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_a_sub"], {"pass_id": secure_id},
    )
    assert res.status_code == 409
    assert pass_snapshot(app, booking_id)["status"] == SmartQueuePassStatus.ACTIVE


def test_cancelled_booking_pass_cannot_be_verified(client, app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]
    secure_id = create_pass_directly(app, booking_id)

    set_booking_status(booking_id, BookingStatus.CANCELLED)

    res = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_a_sub"], {"pass_id": secure_id},
    )
    assert res.status_code == 409


def test_v_unknown_pass_identifier_returns_404_without_leakage(client, app, pass_setup):
    res = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_a_sub"],
        {"pass_id": "kp_pass_invalididentifiertryingtoguessapassvalue"},
    )
    assert res.status_code == 404
    payload = res.get_json()
    assert payload["code"] == "NOT_FOUND"
    assert "smart_queue_pass" not in payload
    assert "booking" not in payload
    assert "K-" not in res.get_data(as_text=True)


def test_w_verification_does_not_start_or_complete_procurement(client, app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]
    secure_id = create_pass_directly(app, booking_id)

    res = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_a_sub"], {"pass_id": secure_id},
    )
    assert res.status_code == 200
    payload = res.get_json()["smart_queue_pass"]
    # Entry only: no procurement record exists or was created.
    assert payload["procurement"] is None
    assert booking_status(app, booking_id) == BookingStatus.CONFIRMED

    with app.app_context():
        db.session.expire_all()
        assert Procurement.query.count() == 0


def test_x_booking_cancellation_cancels_the_active_pass(client, app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]

    got = make_call(
        client, "GET", f"/api/queue-pass/my/{booking_id}", pass_setup["farmer1_sub"]
    )
    assert got.status_code == 200
    assert pass_snapshot(app, booking_id)["status"] == SmartQueuePassStatus.ACTIVE

    cancelled = make_call(
        client, "PUT", f"/api/bookings/{booking_id}/cancel", pass_setup["farmer1_sub"]
    )
    assert cancelled.status_code == 200
    assert booking_status(app, booking_id) == BookingStatus.CANCELLED

    # ACTIVE -> CANCELLED, and no additional pass was created.
    assert pass_snapshot(app, booking_id)["status"] == SmartQueuePassStatus.CANCELLED
    assert pass_count(app) == 1


def test_y_audit_log_written_for_successful_verification(client, app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]
    secure_id = create_pass_directly(app, booking_id)

    res = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_a_sub"], {"pass_id": secure_id},
    )
    assert res.status_code == 200

    entries = audit_entries(app, "VERIFY_SMART_QUEUE_PASS")
    assert len(entries) == 1
    entry = entries[0]
    assert entry["entity_type"] == "SMART_QUEUE_PASS"
    assert entry["user_id"] == pass_setup["staff_a_user_id"]
    assert entry["metadata"]["booking_id"] == booking_id
    assert entry["metadata"]["centre_id"] == pass_setup["centre_a_id"]
    assert entry["metadata"]["result"] == SmartQueuePassStatus.VERIFIED
    assert entry["metadata"]["actor_role"] == UserRole.STAFF
    # No sensitive data is stored in the audit trail.
    audit_blob = str(entry).lower()
    # Check for actual JWT patterns rather than just the literal substring "jwt".
    assert "eyJ" not in audit_blob  # JWT header prefix
    for forbidden in ("9876500101", "phone", "ifsc", "password", "authorization"):
        assert forbidden not in audit_blob


def test_z_cross_centre_lookup_forbidden_but_admin_lookup_allowed_and_read_only(
    client, app, pass_setup
):
    booking_id = pass_setup["booking_b1_id"]
    secure_id = create_pass_directly(app, booking_id)

    denied = make_call(
        client, "GET", f"/api/queue-pass/lookup/{secure_id}", pass_setup["staff_a_sub"]
    )
    assert denied.status_code == 403

    allowed = make_call(
        client, "GET", f"/api/queue-pass/lookup/{secure_id}", pass_setup["admin_sub"]
    )
    assert allowed.status_code == 200
    payload = allowed.get_json()["smart_queue_pass"]
    assert payload["status"] == SmartQueuePassStatus.ACTIVE
    assert payload["centre"]["id"] == pass_setup["centre_b_id"]

    # A lookup must never verify the pass.
    assert pass_snapshot(app, booking_id)["status"] == SmartQueuePassStatus.ACTIVE


def test_failed_verification_attempt_is_audited(client, app, pass_setup):
    secure_id = create_pass_directly(app, pass_setup["booking_b1_id"])

    res = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_a_sub"], {"pass_id": secure_id},
    )
    assert res.status_code == 403

    entries = audit_entries(app, "FAILED_SMART_QUEUE_PASS_VERIFICATION")
    assert len(entries) == 1
    entry = entries[0]
    assert entry["user_id"] == pass_setup["staff_a_user_id"]
    assert entry["entity_type"] == "SMART_QUEUE_PASS"
    assert entry["metadata"]["result"] == "REJECTED"
    assert entry["metadata"]["reason_code"] == "FORBIDDEN"
    assert entry["metadata"]["centre_id"] == pass_setup["centre_a_id"]


# --- Additional API / security / regression checks --------------------------


def test_verification_endpoint_requires_authentication(client, pass_setup):
    res = client.post("/api/queue-pass/verify", json={"pass_id": "kp_pass_anonymous"})
    assert res.status_code == 401


def test_verify_endpoint_validates_the_request_body(client, pass_setup):
    no_body = make_call(
        client, "POST", "/api/queue-pass/verify", pass_setup["staff_a_sub"], None
    )
    assert no_body.status_code == 400

    blank = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_a_sub"], {"pass_id": "   "},
    )
    assert blank.status_code == 400

    wrong_type = make_call(
        client, "POST", "/api/queue-pass/verify",
        pass_setup["staff_a_sub"], {"pass_id": 12345},
    )
    assert wrong_type.status_code == 400


def test_lookup_of_unknown_pass_returns_404(client, pass_setup):
    res = make_call(
        client, "GET", "/api/queue-pass/lookup/kp_pass_does_not_exist",
        pass_setup["admin_sub"],
    )
    assert res.status_code == 404


def test_farmer_pass_unavailable_for_unconfirmed_booking(client, app, pass_setup):
    booking_id = pass_setup["booking_a1_id"]
    set_booking_status(booking_id, BookingStatus.PENDING)

    res = make_call(
        client, "GET", f"/api/queue-pass/my/{booking_id}", pass_setup["farmer1_sub"]
    )
    assert res.status_code == 409
    assert pass_count(app) == 0  # no pass is created for a non-confirmed booking


def test_staff_cannot_read_a_farmers_pass_through_the_farmer_endpoint(client, pass_setup):
    res = make_call(
        client, "GET", f"/api/queue-pass/my/{pass_setup['booking_a1_id']}",
        pass_setup["staff_a_sub"],
    )
    assert res.status_code == 403


def test_pass_response_contains_no_sensitive_personal_data(client, app, pass_setup):
    res = make_call(
        client, "GET", f"/api/queue-pass/my/{pass_setup['booking_a1_id']}",
        pass_setup["farmer1_sub"],
    )
    assert res.status_code == 200

    body = res.get_data(as_text=True).lower()
    assert "9876500101" not in body  # farmer phone number
    # Check for actual JWT patterns (base64-encoded JSON starting with eyJ) rather
    # than just the literal substring "jwt" which may appear in random pass IDs.
    assert "eyJ" not in body  # JWT header prefix
    for forbidden in ("phone", "ifsc", "bank_account", "password",
                      "authorization", "secret"):
        assert forbidden not in body

    pass_id = res.get_json()["smart_queue_pass"]["pass_id"]
    # The QR payload never embeds internal identifiers or the queue token:
    # it is not the booking id, not the farmer id and not the K-#### token.
    assert pass_id != str(pass_setup["booking_a1_id"])
    assert "K-0001" not in pass_id
    assert not pass_id.removeprefix("kp_pass_").isdigit()
    assert "user-pass-farmer1" not in pass_id


def test_existing_booking_flow_still_works_with_pass_creation(client, app, pass_setup):
    first = make_call(
        client, "POST", "/api/bookings",
        pass_setup["farmer1_sub"], {"slot_id": pass_setup["slot_c_id"]},
    )
    assert first.status_code == 201
    booking_id = first.get_json()["booking"]["id"]
    assert pass_count(app) == 1

    # Duplicate booking protection is untouched.
    duplicate = make_call(
        client, "POST", "/api/bookings",
        pass_setup["farmer1_sub"], {"slot_id": pass_setup["slot_c_id"]},
    )
    assert duplicate.status_code == 409
    assert pass_count(app) == 1  # no extra pass was created

    listing = make_call(client, "GET", "/api/bookings/my", pass_setup["farmer1_sub"])
    assert listing.status_code == 200
    assert any(b["id"] == booking_id for b in listing.get_json()["bookings"])


# =============================================================================
# STAGE 2 TESTS: Smart Queue Pass UI, QR Code, and Staff Scanner
# =============================================================================


class TestStage2QRNaSecurity:
    """Stage 2: Verify QR code generation uses only secure_pass_id."""

    def test_qr_generation_uses_secure_pass_id(self, app):
        """A. QR generation uses secure_pass_id."""
        from app.services.smart_queue_pass_service import generate_qr_code_base64, generate_secure_pass_id

        secure_id = generate_secure_pass_id()
        qr_base64 = generate_qr_code_base64(secure_id)

        # The QR code should be a valid base64-encoded PNG
        assert qr_base64
        assert len(qr_base64) > 100  # Reasonable size for a QR PNG

        # Decode and verify it's a PNG
        import base64
        img_data = base64.b64decode(qr_base64)
        assert img_data.startswith(b"\x89PNG")  # PNG magic bytes

    def test_qr_payload_does_not_contain_sensitive_data(self, app, pass_setup):
        """B. QR payload does not contain sensitive data."""
        from app.services.smart_queue_pass_service import generate_qr_code_base64, create_pass_for_booking
        from app.extensions import db

        with app.app_context():
            booking = db.session.get(Booking, pass_setup["booking_a1_id"])
            pass_row = create_pass_for_booking(booking)
            secure_id = pass_row.secure_pass_id

        qr_base64 = generate_qr_code_base64(secure_id)

        # Decode QR and verify payload is just the secure_pass_id
        import base64
        from pyzbar import pyzbar
        from PIL import Image
        import io

        img_data = base64.b64decode(qr_base64)
        img = Image.open(io.BytesIO(img_data))
        decoded = pyzbar.decode(img)

        assert len(decoded) == 1
        qr_payload = decoded[0].data.decode("utf-8")

        # QR payload must be exactly the secure_pass_id
        assert qr_payload == secure_id

        # QR payload must NOT contain any obvious sensitive patterns:
        # It should be just the secure_pass_id (kp_pass_<random>)
        assert qr_payload.startswith("kp_pass_")
        assert len(qr_payload) > 20  # Reasonable length for secure random ID

        # Verify the QR payload is exactly the secure_pass_id
        assert qr_payload == secure_id

        # The QR payload must NOT be any of these sensitive identifiers:
        assert qr_payload != "9876500101"  # phone
        assert "IFSC" not in qr_payload
        assert "bank_account" not in qr_payload
        assert "eyJ" not in qr_payload  # JWT header
        assert "password" not in qr_payload
        assert qr_payload != str(pass_setup["farmer1_sub"])  # farmer ID
        assert qr_payload != str(pass_setup["booking_a1_id"])  # booking ID
        assert "K-0001" not in qr_payload  # queue token


class TestStage2QRProductionBackendRegression:
    """Stage 2 production regression: QR rendering without the Pillow backend.

    Production (Render) installed ``qrcode`` without its ``[pil]`` extra, so
    ``qrcode.QRCode.make_image()`` fell back to the pure-python ``PyPNGImage``
    backend. That backend's signature is ``save(stream, kind=None)`` - it has no
    ``format`` keyword - so the service's ``img.save(buffer, format="PNG")``
    raised::

        TypeError: PyPNGImage.save() got an unexpected keyword argument 'format'

    which turned ``GET /api/queue-pass/my/<booking_id>/display`` into HTTP 500.

    The fix is backend-agnostic: ``img.save(buffer)``. ``PilImage.save()``
    defaults its format to ``self.kind`` (``"PNG"``) and ``PyPNGImage`` always
    writes PNG, so both backends keep producing a valid PNG.

    How the production condition is reproduced without uninstalling Pillow:
    ``QRCode.make_image()`` chooses ``image_factory = PilImage if Image else
    PyPNGImage``, where ``Image`` is the ``qrcode.image.pil`` module attribute
    (``None`` when Pillow is missing). Patching that attribute to ``None``
    therefore selects the real ``PyPNGImage`` code path - the exact production
    behaviour - while Pillow stays installed for the other tests.
    """

    @staticmethod
    def _record_backends():
        """Spy returning (list of backends used, patch of ``make_image``)."""
        import qrcode

        recorded = []
        real_make_image = qrcode.QRCode.make_image

        def recording_make_image(self, *args, **kwargs):
            image = real_make_image(self, *args, **kwargs)
            recorded.append(type(image))
            return image

        return recorded, patch.object(qrcode.QRCode, "make_image", recording_make_image)

    @staticmethod
    def _record_payloads():
        """Spy capturing every payload handed to ``QRCode.add_data``."""
        import qrcode

        recorded = []
        real_add_data = qrcode.QRCode.add_data

        def recording_add_data(self, data, *args, **kwargs):
            recorded.append(data)
            return real_add_data(self, data, *args, **kwargs)

        return recorded, patch.object(qrcode.QRCode, "add_data", recording_add_data)

    @staticmethod
    def _png_size(png_bytes):
        """Validate the PNG signature/IHDR and return its (width, height)."""
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic bytes
        assert png_bytes[12:16] == b"IHDR"
        return (
            int.from_bytes(png_bytes[16:20], "big"),
            int.from_bytes(png_bytes[20:24], "big"),
        )

    def test_qr_generation_works_without_pillow_pure_png_backend(self, app):
        """A. The production backend (PyPNGImage) renders a valid base64 PNG."""
        import base64

        from qrcode.image.pure import PyPNGImage

        from app.services.smart_queue_pass_service import (
            generate_qr_code_base64,
            generate_secure_pass_id,
        )

        secure_id = generate_secure_pass_id()
        backends, backend_patch = self._record_backends()

        with patch("qrcode.image.pil.Image", None), backend_patch:
            qr_base64 = generate_qr_code_base64(secure_id)

        # qrcode really did take its no-Pillow fallback branch.
        assert backends == [PyPNGImage]

        png_bytes = base64.b64decode(qr_base64)
        width, height = self._png_size(png_bytes)
        assert width > 0 and height > 0
        assert base64.b64encode(png_bytes).decode("utf-8") == qr_base64
        assert len(qr_base64) > 100

    def test_qr_generation_still_works_with_pillow_backend(self, app):
        """B. With Pillow available the PilImage backend keeps working."""
        import base64

        import qrcode.image.pil

        from app.services.smart_queue_pass_service import (
            generate_qr_code_base64,
            generate_secure_pass_id,
        )

        if qrcode.image.pil.Image is None:  # Pillow is genuinely not installed
            pytest.skip("Pillow not installed - covered by the PyPNGImage test.")

        from qrcode.image.pil import PilImage

        secure_id = generate_secure_pass_id()
        backends, backend_patch = self._record_backends()

        with backend_patch:
            qr_base64 = generate_qr_code_base64(secure_id)

        assert backends == [PilImage]
        width, height = self._png_size(base64.b64decode(qr_base64))
        assert width > 0 and height > 0

    def test_qr_save_call_stays_backend_agnostic(self, app):
        """C. ``img.save()`` is never called with a ``format`` keyword.

        A strict stand-in for ``PyPNGImage`` (``save(stream, kind=None)`` only)
        fails the moment the service passes ``format=`` again - the exact
        production regression.
        """
        import base64

        import qrcode

        class PurePngLikeImage:
            """Same save() contract as ``qrcode.image.pure.PyPNGImage``."""

            kind = "PNG"

            def __init__(self):
                self.saved = False

            def save(self, stream, kind=None):
                if kind is not None and kind != self.kind:
                    raise ValueError(f"Unknown image kind: {kind}")
                self.saved = True
                stream.write(b"\x89PNG\r\n\x1a\n")

        rendered = PurePngLikeImage()

        from app.services.smart_queue_pass_service import (
            generate_qr_code_base64,
            generate_secure_pass_id,
        )

        with patch.object(qrcode.QRCode, "make_image", lambda *a, **k: rendered):
            qr_base64 = generate_qr_code_base64(generate_secure_pass_id())

        assert rendered.saved is True
        assert base64.b64decode(qr_base64) == b"\x89PNG\r\n\x1a\n"

    # --- payload security (the QR must never carry personal data) -----------

    def test_qr_payload_is_exactly_the_secure_pass_id(self, app, pass_setup):
        """D. The QR encodes exactly one value: the pass's secure_pass_id."""
        from app.services.smart_queue_pass_service import (
            create_pass_for_booking,
            generate_qr_code_base64,
        )

        with app.app_context():
            booking = db.session.get(Booking, pass_setup["booking_a1_id"])
            secure_id = create_pass_for_booking(booking).secure_pass_id

        payloads, payload_patch = self._record_payloads()
        with payload_patch, patch("qrcode.image.pil.Image", None):
            generate_qr_code_base64(secure_id)

        assert payloads == [secure_id]

    def test_qr_decodes_back_to_the_secure_pass_id_on_both_backends(
        self, app, pass_setup
    ):
        """E. A real decoder reads back exactly the secure_pass_id."""
        import base64
        import io

        Image = pytest.importorskip("PIL.Image")
        pyzbar = pytest.importorskip("pyzbar.pyzbar")

        import qrcode.image.pil

        from app.services.smart_queue_pass_service import (
            create_pass_for_booking,
            generate_qr_code_base64,
        )

        with app.app_context():
            booking = db.session.get(Booking, pass_setup["booking_a1_id"])
            secure_id = create_pass_for_booking(booking).secure_pass_id

        pillow_available = qrcode.image.pil.Image
        decoded_payloads = []
        for no_pillow in (False, True):
            with patch.object(
                qrcode.image.pil, "Image", None if no_pillow else pillow_available
            ):
                qr_base64 = generate_qr_code_base64(secure_id)

            png_bytes = base64.b64decode(qr_base64)
            self._png_size(png_bytes)
            decoded = pyzbar.decode(Image.open(io.BytesIO(png_bytes)))
            assert len(decoded) == 1
            decoded_payloads.append(decoded[0].data.decode("utf-8"))

        assert decoded_payloads == [secure_id, secure_id]

    def test_qr_never_carries_sensitive_data(self, app, pass_setup):
        """F. No phone/token/booking id/identity/JWT/bank data enters the QR."""
        import base64

        from app.services.smart_queue_pass_service import (
            create_pass_for_booking,
            generate_qr_code_base64,
        )

        with app.app_context():
            booking = db.session.get(Booking, pass_setup["booking_a1_id"])
            secure_id = create_pass_for_booking(booking).secure_pass_id

        payloads, payload_patch = self._record_payloads()
        with payload_patch, patch("qrcode.image.pil.Image", None):
            qr_base64 = generate_qr_code_base64(secure_id)

        # Exactly one payload - and it is the non-secret pass identifier.
        assert payloads == [secure_id]
        payload = payloads[0]
        assert payload == secure_id
        assert payload.startswith("kp_pass_")
        assert len(payload) > 20
        assert not payload.removeprefix("kp_pass_").isdigit()

        # It is never an internal identifier or the queue token.
        assert payload != str(pass_setup["booking_a1_id"])
        assert payload != str(pass_setup["farmer1_user_id"])
        assert payload != pass_setup["farmer1_sub"]

        secrets = (
            "9876500101",          # farmer phone number
            "K-0001",              # queue token number
            "Pass Farmer One",     # farmer name
            "Pass Test Centre A",  # centre name
            "Ludhiana",            # centre location
            "user-pass-farmer1",   # Supabase subject (farmer identity)
            "eyJ",                 # JWT header prefix
            "IFSC",
            "bank_account",
            "password",
        )
        png_bytes = base64.b64decode(qr_base64)
        for secret in secrets:
            assert secret not in payload
            assert secret.encode("utf-8") not in png_bytes

    # --- the reported production failure: display endpoint ------------------

    def test_display_endpoint_returns_a_png_qr_without_pillow(
        self, app, client, pass_setup
    ):
        """G. Regression: the display API no longer answers HTTP 500."""
        import base64

        secure_id = create_pass_directly(app, pass_setup["booking_a1_id"])

        with patch("qrcode.image.pil.Image", None):
            res = make_call(
                client, "GET",
                f"/api/queue-pass/my/{pass_setup['booking_a1_id']}/display",
                pass_setup["farmer1_sub"],
            )

        assert res.status_code == 200
        pass_data = res.get_json()["pass_data"]
        assert pass_data["pass_id"] == secure_id
        qr_base64 = pass_data["qr_code_base64"]
        assert isinstance(qr_base64, str)
        assert len(qr_base64) > 100
        assert base64.b64decode(qr_base64).startswith(b"\x89PNG\r\n\x1a\n")

    def test_display_endpoint_works_with_the_pillow_backend(
        self, app, client, pass_setup
    ):
        """H. The same endpoint with Pillow present (the standard install)."""
        import base64

        secure_id = create_pass_directly(app, pass_setup["booking_a1_id"])

        res = make_call(
            client, "GET",
            f"/api/queue-pass/my/{pass_setup['booking_a1_id']}/display",
            pass_setup["farmer1_sub"],
        )

        assert res.status_code == 200
        pass_data = res.get_json()["pass_data"]
        assert pass_data["pass_id"] == secure_id
        self._png_size(base64.b64decode(pass_data["qr_code_base64"]))

    def test_farmer_ownership_of_the_qr_pass_remains_intact(
        self, app, client, pass_setup
    ):
        """I. Farmer ownership rules around the QR pass are unchanged."""
        secure_id = create_pass_directly(app, pass_setup["booking_a1_id"])
        create_pass_directly(app, pass_setup["booking_b1_id"])

        # 1. Plain browser navigation (no Bearer header) still cannot read it.
        anon = client.get(f"/api/queue-pass/my/{pass_setup['booking_a1_id']}/display")
        assert anon.status_code == 401

        # 2. The owner receives the QR of their own booking.
        owner = make_call(
            client, "GET",
            f"/api/queue-pass/my/{pass_setup['booking_a1_id']}/display",
            pass_setup["farmer1_sub"],
        )
        assert owner.status_code == 200
        assert owner.get_json()["pass_data"]["pass_id"] == secure_id

        # 3. Another farmer's booking id discloses neither pass nor QR data.
        foreign = make_call(
            client, "GET",
            f"/api/queue-pass/my/{pass_setup['booking_a1_id']}/display",
            pass_setup["farmer2_sub"],
        )
        assert foreign.status_code == 404
        assert "pass_data" not in foreign.get_json()
        assert secure_id not in foreign.get_data(as_text=True)

        # 4. ... while farmer 2 still reaches their own pass.
        own = make_call(
            client, "GET",
            f"/api/queue-pass/my/{pass_setup['booking_b1_id']}/display",
            pass_setup["farmer2_sub"],
        )
        assert own.status_code == 200
        assert own.get_json()["pass_data"]["pass_id"].startswith("kp_pass_")

    def test_stage1_security_and_qr_payload_survive_verification(
        self, app, client, pass_setup
    ):
        """J. Stage 1 rules hold and verification never changes the payload."""
        secure_id = create_pass_directly(app, pass_setup["booking_a1_id"])
        payloads, payload_patch = self._record_payloads()

        with payload_patch:
            before = make_call(
                client, "GET",
                f"/api/queue-pass/my/{pass_setup['booking_a1_id']}/display",
                pass_setup["farmer1_sub"],
            )
            assert before.status_code == 200

            verified = make_call(
                client, "POST", "/api/queue-pass/verify",
                pass_setup["staff_a_sub"], {"pass_id": secure_id},
            )
            assert verified.status_code == 200
            assert verified.get_json()["smart_queue_pass"]["status"] == "VERIFIED"

            after = make_call(
                client, "GET",
                f"/api/queue-pass/my/{pass_setup['booking_a1_id']}/display",
                pass_setup["farmer1_sub"],
            )
            assert after.status_code == 200

        # Both renditions encoded exactly the same, non-secret payload.
        assert payloads == [secure_id, secure_id]
        assert after.get_json()["pass_data"]["pass_status"] == "VERIFIED"

        # Stage 1 centre isolation and role rules are untouched.
        assert make_call(
            client, "GET", f"/api/queue-pass/lookup/{secure_id}",
            pass_setup["staff_a_sub"],
        ).status_code == 200
        assert make_call(
            client, "GET", f"/api/queue-pass/lookup/{secure_id}",
            pass_setup["staff_b_sub"],
        ).status_code == 403
        assert make_call(
            client, "GET", f"/api/queue-pass/lookup/{secure_id}",
            pass_setup["staff_none_sub"],
        ).status_code == 403
        assert make_call(
            client, "POST", "/api/queue-pass/verify",
            pass_setup["farmer1_sub"], {"pass_id": secure_id},
        ).status_code == 403


class TestStage2FarmerPassDisplay:
    """Stage 2: Verify farmer pass display endpoint and UI."""

    def test_farmer_pass_display_endpoint_works(self, app, client, pass_setup):
        """C. Farmer pass display endpoint works."""
        # Create the pass first (it's created on-demand for confirmed bookings)
        create_pass_directly(app, pass_setup["booking_a1_id"])

        res = make_call(
            client, "GET",
            f"/api/queue-pass/my/{pass_setup['booking_a1_id']}/display",
            pass_setup["farmer1_sub"],
        )
        assert res.status_code == 200
        data = res.get_json()
        assert "pass_data" in data
        pass_data = data["pass_data"]

        # Must contain required fields
        required_fields = [
            "pass_id", "pass_status", "booking_id", "booking_status",
            "token_number", "booking_date", "farmer_name", "centre_name",
            "centre_location", "crop_name", "slot_date", "start_time",
            "end_time", "qr_code_base64",
        ]
        for field in required_fields:
            assert field in pass_data, f"Missing field: {field}"

    def test_farmer_can_only_access_own_pass(self, app, client, pass_setup):
        """D. Farmer can only access their own pass."""
        # Create both passes first
        create_pass_directly(app, pass_setup["booking_a1_id"])
        create_pass_directly(app, pass_setup["booking_b1_id"])

        # Farmer1 tries to access Farmer2's pass - should get 404 (not disclose ownership)
        res = make_call(
            client, "GET",
            f"/api/queue-pass/my/{pass_setup['booking_b1_id']}/display",
            pass_setup["farmer1_sub"],
        )
        assert res.status_code == 404
        # Verify no pass data is leaked
        assert "pass_data" not in res.get_json()

    def test_pass_view_page_renders(self, app, client, pass_setup):
        """Verify the /view endpoint renders the queue_pass.html template."""
        create_pass_directly(app, pass_setup["booking_a1_id"])

        res = make_call(
            client, "GET",
            f"/api/queue-pass/my/{pass_setup['booking_a1_id']}/view",
            pass_setup["farmer1_sub"],
        )
        assert res.status_code == 200
        assert b"KISANPROCURE" in res.data
        assert b"SMART QUEUE PASS" in res.data
        assert b"Print / Download" in res.data  # Accurate button wording

    def test_pass_view_page_contains_no_sensitive_data(self, app, client, pass_setup):
        """Verify rendered pass page contains no sensitive data."""
        create_pass_directly(app, pass_setup["booking_a1_id"])

        res = make_call(
            client, "GET",
            f"/api/queue-pass/my/{pass_setup['booking_a1_id']}/view",
            pass_setup["farmer1_sub"],
        )
        body = res.get_data(as_text=True).lower()
        assert "9876500101" not in body  # phone
        assert "ifsc" not in body
        assert "bank_account" not in body
        assert "eyJ" not in body  # JWT


class TestStage2StaffScanner:
    """Stage 2: Verify staff scanner functionality and authorization."""

    def test_staff_scanner_present_in_staff_dashboard(self, client, pass_setup):
        """E. Staff scanner is present in staff dashboard."""
        res = make_call(
            client, "GET", "/staff/dashboard",
            pass_setup["staff_a_sub"],
        )
        assert res.status_code == 200
        body = res.get_data(as_text=True)
        assert "Smart Queue Pass Scanner" in body
        assert "Scan Queue Pass" in body
        assert "html5-qrcode" in body  # Scanner library

    def test_farmer_cannot_access_staff_scanner(self, client, pass_setup):
        """F. Farmer cannot access staff scanner."""
        res = make_call(
            client, "GET", "/staff/dashboard",
            pass_setup["farmer1_sub"],
        )
        assert res.status_code == 403

    def test_scanner_sends_only_pass_id_to_verify(self, app, client, pass_setup):
        """G. Scanner sends only pass_id to verify endpoint."""
        # The verify endpoint should only require pass_id
        secure_id = create_pass_directly(app, pass_setup["booking_a1_id"])
        res = make_call(
            client, "POST", "/api/queue-pass/verify",
            pass_setup["staff_a_sub"],
            {"pass_id": secure_id},
        )
        assert res.status_code in (200, 409)  # 200 if first verification, 409 if already verified

    def test_scanner_does_not_send_centre_id(self, app, client, pass_setup):
        """H. Scanner does not send centre_id."""
        # The verify endpoint should work without centre_id in request
        secure_id = create_pass_directly(app, pass_setup["booking_a1_id"])
        res = make_call(
            client, "POST", "/api/queue-pass/verify",
            pass_setup["staff_a_sub"],
            {"pass_id": secure_id},
        )
        # Should not require centre_id - it's derived from staff assignment
        assert res.status_code in (200, 409)

    def test_verification_response_reflected_in_ui(self, app, client, pass_setup):
        """I. Successful backend verification is reflected in UI."""
        # Verify the pass first
        secure_id = create_pass_directly(app, pass_setup["booking_a1_id"])
        verify_res = make_call(
            client, "POST", "/api/queue-pass/verify",
            pass_setup["staff_a_sub"],
            {"pass_id": secure_id},
        )
        assert verify_res.status_code == 200
        data = verify_res.get_json()
        assert data["smart_queue_pass"]["status"] == "VERIFIED"
        assert data["smart_queue_pass"]["verified_at"] is not None
        assert data["smart_queue_pass"]["verified_by"] is not None

    def test_error_responses_handled(self, app, client, pass_setup):
        """J. 403/404/409 responses are handled."""
        secure_id = create_pass_directly(app, pass_setup["booking_a1_id"])

        # 404 - unknown pass
        res_404 = make_call(
            client, "POST", "/api/queue-pass/verify",
            pass_setup["staff_a_sub"],
            {"pass_id": "kp_pass_nonexistent"},
        )
        assert res_404.status_code == 404

        # First verification should succeed
        res_first = make_call(
            client, "POST", "/api/queue-pass/verify",
            pass_setup["staff_a_sub"],
            {"pass_id": secure_id},
        )
        assert res_first.status_code == 200

        # 409 - already verified (verify again)
        res_409 = make_call(
            client, "POST", "/api/queue-pass/verify",
            pass_setup["staff_a_sub"],
            {"pass_id": secure_id},
        )
        assert res_409.status_code == 409

        # 403 - staff from different centre
        # Use booking_b1 (at centre_b) and try to verify with staff_a (at centre_a)
        secure_id_b = create_pass_directly(app, pass_setup["booking_b1_id"])
        res_403 = make_call(
            client, "POST", "/api/queue-pass/verify",
            pass_setup["staff_a_sub"],
            {"pass_id": secure_id_b},
        )
        assert res_403.status_code == 403

    def test_procurement_not_completed_by_qr_scanning(self, app, client, pass_setup):
        """K. Procurement is NOT completed by QR scanning."""
        from app.models import Procurement, ProcurementStatus

        # Verify the pass via scanner
        secure_id = create_pass_directly(app, pass_setup["booking_a1_id"])
        make_call(
            client, "POST", "/api/queue-pass/verify",
            pass_setup["staff_a_sub"],
            {"pass_id": secure_id},
        )

        # Check procurement status after verification
        with app.app_context():
            procurement = Procurement.query.filter(
                Procurement.booking_id == pass_setup["booking_a1_id"]
            ).first()

        # Procurement should NOT be in a completed state
        assert procurement is None or procurement.status != ProcurementStatus.COMPLETED

    def test_stage1_security_remains_intact(self, app, client, pass_setup):
        """L. Existing Stage 1 security remains intact."""
        # This test verifies that Stage 2 changes didn't break Stage 1 security
        secure_id = create_pass_directly(app, pass_setup["booking_a1_id"])

        # 1. Farmer can still retrieve own pass
        res = make_call(
            client, "GET", f"/api/queue-pass/my/{pass_setup['booking_a1_id']}",
            pass_setup["farmer1_sub"],
        )
        assert res.status_code == 200

        # 2. Farmer cannot retrieve another farmer's pass
        res = make_call(
            client, "GET", f"/api/queue-pass/my/{pass_setup['booking_b1_id']}",
            pass_setup["farmer1_sub"],
        )
        assert res.status_code == 404  # Returns 404 to not disclose ownership

        # 3. Staff can only verify passes for their own centre
        res = make_call(
            client, "POST", "/api/queue-pass/verify",
            pass_setup["staff_b_sub"],
            {"pass_id": secure_id},
        )
        assert res.status_code == 403  # staff_b is at centre_b, pass is for centre_a

        # 4. Admin can verify any pass
        res = make_call(
            client, "POST", "/api/queue-pass/verify",
            pass_setup["admin_sub"],
            {"pass_id": secure_id},
        )
        assert res.status_code == 200

        # 5. Unassigned staff cannot verify
        res = make_call(
            client, "POST", "/api/queue-pass/verify",
            pass_setup["staff_none_sub"],
            {"pass_id": secure_id},
        )
        assert res.status_code == 403
# =============================================================================
# STAGE 2 REGRESSION: Farmer Dashboard -> Smart Queue Pass page navigation
# =============================================================================
#
# Production bug: the "View Smart Queue Pass" button did
#     window.open('/api/queue-pass/my/<booking_id>/view')
# A plain browser navigation cannot send the application's Bearer token, so the
# protected API answered 401 {"error": "Authentication required"}.
#
# Fixed flow (covered below):
#     Farmer Dashboard -> /farmer/queue-pass/<booking_id> (HTML page)
#         -> window.KP.authFetch('/api/queue-pass/my/<booking_id>/display')
#         -> render pass + QR
# =============================================================================

PASS_PAGE_ROUTE = "/farmer/queue-pass/{}"
PASS_API_PREFIX = "/api/queue-pass/my/"


def dashboard_view_queue_pass_source(client) -> str:
    """Return the JS source of the Farmer Dashboard's viewQueuePass handler.

    /farmer/dashboard is a public HTML shell (like every other page route in
    this app), so no Authorization header is required to read it.
    """
    res = client.get("/farmer/dashboard")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    match = re.search(r"function viewQueuePass\(bookingId\)\s*\{(.*?)\}", html, re.S)
    assert match is not None, "Farmer Dashboard has no viewQueuePass handler"
    return match.group(1)


class TestStage2FarmerDashboardPassNavigation:
    """Stage 2 regression: the button must open the HTML page, not the API."""

    def test_dashboard_button_does_not_navigate_to_protected_api(self, client):
        """The reported bug: the button must NOT navigate to the API route."""
        handler = dashboard_view_queue_pass_source(client)

        assert PASS_API_PREFIX not in handler
        assert "/api/queue-pass" not in handler
        assert "window.open" in handler
        assert "/farmer/queue-pass/" in handler
        # The booking id is URL-encoded and no token ever appears in the URL.
        assert "encodeURIComponent(bookingId)" in handler
        assert "token" not in handler.lower()
        assert "bearer" not in handler.lower()

    def test_dashboard_button_is_wired_to_the_handler(self, client):
        res = client.get("/farmer/dashboard")
        html = res.get_data(as_text=True)
        assert "View Smart Queue Pass" in html
        assert "viewQueuePass(${b.id})" in html

    def test_dashboard_page_never_references_the_queue_pass_api(self, client):
        """Defence in depth: no dashboard link points at /api/queue-pass."""
        res = client.get("/farmer/dashboard")
        assert "/api/queue-pass" not in res.get_data(as_text=True)

    def test_pass_page_route_serves_html_without_an_auth_header(self, client, app, pass_setup):
        """B. The pass page is a normal HTML page (no Bearer header needed)."""
        create_pass_directly(app, pass_setup["booking_a1_id"])

        res = client.get(PASS_PAGE_ROUTE.format(pass_setup["booking_a1_id"]))
        assert res.status_code == 200

        body = res.get_data(as_text=True)
        assert "KISANPROCURE" in body
        assert "SMART QUEUE PASS" in body
        assert "Print / Download" in body

    def test_pass_page_route_rejects_invalid_booking_ids(self, client):
        """Only integer booking ids reach the page (no path traversal)."""
        assert client.get("/farmer/queue-pass/not-a-number").status_code == 404
        assert client.get("/farmer/queue-pass/../../etc/passwd").status_code == 404

    def test_pass_page_uses_the_authenticated_stage2_request(self, client, pass_setup):
        """C. The page reuses window.KP.authFetch() + the /display endpoint."""
        res = client.get(PASS_PAGE_ROUTE.format(pass_setup["booking_a1_id"]))
        body = res.get_data(as_text=True)

        assert "/static/js/auth.js" in body  # Stage 2 auth mechanism
        assert "window.KP.authFetch" in body
        assert PASS_API_PREFIX in body       # /api/queue-pass/my/
        assert "/display" in body

        # The Bearer token must come from the shared helper (header), never
        # from a URL query parameter or an embedded token value.
        assert "token=" not in body
        assert "access_token" not in body
        assert "mock-token" not in body
        assert "eyJ" not in body  # no JWT anywhere in the page

    def test_pass_page_html_embeds_no_pass_or_personal_data(self, client, app, pass_setup):
        """D. The server-rendered shell exposes no sensitive information."""
        secure_id = create_pass_directly(app, pass_setup["booking_a1_id"])

        res = client.get(PASS_PAGE_ROUTE.format(pass_setup["booking_a1_id"]))
        body = res.get_data(as_text=True)
        lowered = body.lower()

        # No pass identifier / QR image / booking or farmer data at all.
        assert secure_id not in body
        assert "kp_pass_" not in body
        # No QR image is embedded: the src is only built at runtime from the
        # authenticated API response (the endpoint string below is just JS).
        assert "data:image/png;base64,iVBOR" not in body
        assert "data:image/png;base64,' + passData.qr_code_base64" in body
        assert "K-0001" not in body
        assert "9876500101" not in body  # farmer phone
        assert "ifsc" not in lowered
        assert "bank_account" not in lowered

    def test_authenticated_display_api_still_works(self, client, app, pass_setup):
        """E. The authenticated API request behind the page still works."""
        create_pass_directly(app, pass_setup["booking_a1_id"])

        res = make_call(
            client, "GET",
            f"{PASS_API_PREFIX}{pass_setup['booking_a1_id']}/display",
            pass_setup["farmer1_sub"],
        )
        assert res.status_code == 200

        payload = res.get_json()["pass_data"]
        assert payload["pass_id"].startswith("kp_pass_")
        assert payload["booking_id"] == pass_setup["booking_a1_id"]
        assert payload["token_number"] == "K-0001"
        assert payload["qr_code_base64"]
        # No personal/financial data in the display payload.
        assert "9876500101" not in res.get_data(as_text=True)
        assert "ifsc" not in res.get_data(as_text=True).lower()

    def test_display_api_remains_protected(self, client, app, pass_setup):
        """F. Authentication was not weakened: no header -> 401 JSON."""
        create_pass_directly(app, pass_setup["booking_a1_id"])

        res = client.get(f"{PASS_API_PREFIX}{pass_setup['booking_a1_id']}/display")
        assert res.status_code == 401
        payload = res.get_json()
        assert payload["error"] == "Authentication required"
        assert "pass_data" not in payload

    def test_another_farmer_cannot_load_the_pass(self, client, app, pass_setup):
        """G. Farmer ownership checks are preserved end to end."""
        secure_id = create_pass_directly(app, pass_setup["booking_a1_id"])

        # The HTML shell is data-free, so even a foreign booking id leaks nothing.
        shell = client.get(PASS_PAGE_ROUTE.format(pass_setup["booking_a1_id"]))
        assert shell.status_code == 200
        assert secure_id not in shell.get_data(as_text=True)

        # The API still hides the pass from every other farmer.
        res = make_call(
            client, "GET",
            f"{PASS_API_PREFIX}{pass_setup['booking_a1_id']}/display",
            pass_setup["farmer2_sub"],
        )
        assert res.status_code == 404
        assert "pass_data" not in res.get_json()
        assert secure_id not in res.get_data(as_text=True)

    def test_qr_from_display_endpoint_is_only_the_secure_pass_id(self, client, app, pass_setup):
        """H. QR security is preserved: the payload is only secure_pass_id."""
        import base64
        import io

        from PIL import Image
        from pyzbar import pyzbar

        secure_id = create_pass_directly(app, pass_setup["booking_a1_id"])

        res = make_call(
            client, "GET",
            f"{PASS_API_PREFIX}{pass_setup['booking_a1_id']}/display",
            pass_setup["farmer1_sub"],
        )
        qr_base64 = res.get_json()["pass_data"]["qr_code_base64"]

        decoded = pyzbar.decode(Image.open(io.BytesIO(base64.b64decode(qr_base64))))
        assert len(decoded) == 1
        payload = decoded[0].data.decode("utf-8")

        assert payload == secure_id
        assert payload.startswith("kp_pass_")
        assert "9876500101" not in payload  # phone
        assert "K-0001" not in payload  # queue token
        assert "eyJ" not in payload  # JWT

    def test_legacy_view_route_stays_protected_and_data_free(self, client, app, pass_setup):
        """I. The old API-namespaced path is neither public nor leaking data."""
        secure_id = create_pass_directly(app, pass_setup["booking_a1_id"])
        legacy = f"{PASS_API_PREFIX}{pass_setup['booking_a1_id']}/view"

        # 1. Browser navigation (no Bearer header) still cannot read it - which
        #    is exactly why the dashboard must not navigate here.
        anon = client.get(legacy)
        assert anon.status_code == 401
        assert anon.get_json()["error"] == "Authentication required"

        # 2. Authenticated but data-free: even another farmer's booking id only
        #    yields the shell, never pass/QR/personal data.
        res = make_call(client, "GET", legacy, pass_setup["farmer2_sub"])
        assert res.status_code == 200
        body = res.get_data(as_text=True)
        assert "SMART QUEUE PASS" in body
        assert secure_id not in body
        assert "kp_pass_" not in body
        assert "K-0001" not in body
        assert "9876500101" not in body