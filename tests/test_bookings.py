"""Tests for Farmer Slot Booking API (/api/bookings) and Booking Service.

Covers:
- Authentication & RBAC (FARMER allowed, STAFF/ADMIN forbidden, unauthenticated 401)
- Valid booking creation & response structure
- Slot state validations (nonexistent, CLOSED, CANCELLED, past dates, inactive centre/crop)
- Capacity limits & remaining capacity calculations
- Duplicate booking prevention (same farmer + same slot)
- Time conflict prevention (overlapping active bookings on same date)
- Ownership & Security checks (cannot view/cancel another farmer's booking)
- Booking cancellation & capacity release
"""

import pytest
from datetime import date, time, timedelta
from unittest.mock import MagicMock, patch

from app.extensions import db
from app.models import (
    User,
    Farmer,
    Centre,
    Crop,
    Slot,
    SlotStatus,
    Booking,
    BookingStatus,
    UserRole,
)


def make_mock_user(user_id="user-uuid-1", email="user@example.com"):
    u = MagicMock()
    u.id = user_id
    u.email = email
    return u


def auth_header(token="valid-token"):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def farmer_user(app):
    with app.app_context():
        u = User(supabase_user_id="farmer-uuid-1", role=UserRole.FARMER, is_active=True)
        db.session.add(u)
        db.session.flush()
        f = Farmer(user_id=u.id, name="Ramesh Kumar", phone="9876543210")
        db.session.add(f)
        db.session.commit()
        yield u


@pytest.fixture
def farmer_user_2(app):
    with app.app_context():
        u = User(supabase_user_id="farmer-uuid-2", role=UserRole.FARMER, is_active=True)
        db.session.add(u)
        db.session.flush()
        f = Farmer(user_id=u.id, name="Suresh Patel", phone="9876543211")
        db.session.add(f)
        db.session.commit()
        yield u


@pytest.fixture
def staff_user(app):
    with app.app_context():
        u = User(supabase_user_id="staff-uuid-1", role=UserRole.STAFF, is_active=True)
        db.session.add(u)
        db.session.commit()
        yield u


@pytest.fixture
def admin_user(app):
    with app.app_context():
        u = User(supabase_user_id="admin-uuid-1", role=UserRole.ADMIN, is_active=True)
        db.session.add(u)
        db.session.commit()
        yield u


@pytest.fixture
def base_booking_data(app):
    """Fixture providing active centre, active crop, and valid future open slots."""
    with app.app_context():
        c_active = Centre(
            name="Central Mandi",
            location="Karnal",
            opening_time=time(9, 0),
            closing_time=time(17, 0),
            daily_capacity=100,
            is_active=True,
        )
        c_inactive = Centre(
            name="Inactive Mandi",
            location="Old Town",
            is_active=False,
        )
        cr_active = Crop(name="Wheat", category="Cereal", is_active=True)
        cr_inactive = Crop(name="Discontinued Crop", category="Other", is_active=False)

        db.session.add_all([c_active, c_inactive, cr_active, cr_inactive])
        db.session.commit()

        tomorrow = date.today() + timedelta(days=1)

        # Slot 1: Open slot, capacity = 2
        s1 = Slot(
            centre_id=c_active.id,
            crop_id=cr_active.id,
            slot_date=tomorrow,
            start_time=time(9, 0),
            end_time=time(10, 0),
            capacity=2,
            status=SlotStatus.OPEN,
        )

        # Slot 2: Adjacent slot on same day
        s2 = Slot(
            centre_id=c_active.id,
            crop_id=cr_active.id,
            slot_date=tomorrow,
            start_time=time(10, 0),
            end_time=time(11, 0),
            capacity=5,
            status=SlotStatus.OPEN,
        )

        # Slot 3: Overlapping slot (09:30 - 10:30)
        s3 = Slot(
            centre_id=c_active.id,
            crop_id=cr_active.id,
            slot_date=tomorrow,
            start_time=time(9, 30),
            end_time=time(10, 30),
            capacity=5,
            status=SlotStatus.OPEN,
        )

        # Slot 4: Closed slot
        s_closed = Slot(
            centre_id=c_active.id,
            crop_id=cr_active.id,
            slot_date=tomorrow,
            start_time=time(11, 0),
            end_time=time(12, 0),
            capacity=5,
            status=SlotStatus.CLOSED,
        )

        # Slot 5: Inactive centre slot
        s_inact_centre = Slot(
            centre_id=c_inactive.id,
            crop_id=cr_active.id,
            slot_date=tomorrow,
            start_time=time(9, 0),
            end_time=time(10, 0),
            capacity=5,
            status=SlotStatus.OPEN,
        )

        # Slot 6: Inactive crop slot
        s_inact_crop = Slot(
            centre_id=c_active.id,
            crop_id=cr_inactive.id,
            slot_date=tomorrow,
            start_time=time(12, 0),
            end_time=time(13, 0),
            capacity=5,
            status=SlotStatus.OPEN,
        )

        db.session.add_all([s1, s2, s3, s_closed, s_inact_centre, s_inact_crop])
        db.session.commit()

        yield {
            "c_active": c_active,
            "c_inactive": c_inactive,
            "cr_active": cr_active,
            "cr_inactive": cr_inactive,
            "slot_1": s1,
            "slot_2": s2,
            "slot_3": s3,
            "slot_closed": s_closed,
            "slot_inact_centre": s_inact_centre,
            "slot_inact_crop": s_inact_crop,
            "tomorrow": tomorrow,
        }


class TestBookingAuthenticationAndRBAC:
    """Tests for authentication and role restrictions on Booking APIs."""

    def test_unauthenticated_request_rejected(self, client):
        resp = client.post("/api/bookings", json={"slot_id": 1})
        assert resp.status_code == 401

        resp_my = client.get("/api/bookings/my")
        assert resp_my.status_code == 401

    def test_staff_and_admin_cannot_book_slots(self, client, staff_user, admin_user, base_booking_data):
        payload = {"slot_id": base_booking_data["slot_1"].id}

        # Staff attempt
        su_staff = make_mock_user(user_id="staff-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su_staff

            resp = client.post("/api/bookings", json=payload, headers=auth_header())
            assert resp.status_code == 403

        # Admin attempt
        su_admin = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su_admin

            resp = client.post("/api/bookings", json=payload, headers=auth_header())
            assert resp.status_code == 403

    def test_farmer_can_create_valid_booking(self, client, farmer_user, base_booking_data):
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            slot_id = base_booking_data["slot_1"].id
            resp = client.post("/api/bookings", json={"slot_id": slot_id}, headers=auth_header())
            assert resp.status_code == 201

            data = resp.get_json()
            assert data["message"] == "Booking created successfully"
            assert data["booking"]["status"] == "CONFIRMED"
            assert data["booking"]["slot_id"] == slot_id
            assert data["booking"]["slot"]["crop"] == "Wheat"


class TestBookingValidations:
    """Tests for slot state, date, and profile validations."""

    def test_nonexistent_slot_rejected(self, client, farmer_user):
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp = client.post("/api/bookings", json={"slot_id": 99999}, headers=auth_header())
            assert resp.status_code == 400

    def test_closed_or_inactive_slot_rejected(self, client, farmer_user, base_booking_data):
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            # Closed slot
            resp1 = client.post("/api/bookings", json={"slot_id": base_booking_data["slot_closed"].id}, headers=auth_header())
            assert resp1.status_code == 400

            # Inactive centre
            resp2 = client.post("/api/bookings", json={"slot_id": base_booking_data["slot_inact_centre"].id}, headers=auth_header())
            assert resp2.status_code == 400

            # Inactive crop
            resp3 = client.post("/api/bookings", json={"slot_id": base_booking_data["slot_inact_crop"].id}, headers=auth_header())
            assert resp3.status_code == 400


class TestCapacityAndConflictRules:
    """Tests for slot capacity, duplicate bookings, and time conflicts."""

    def test_slot_capacity_limit_enforced(self, client, farmer_user, farmer_user_2, base_booking_data):
        slot_id = base_booking_data["slot_1"].id  # Capacity = 2

        # Farmer 1 books slot_1
        su1 = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su1

            resp1 = client.post("/api/bookings", json={"slot_id": slot_id}, headers=auth_header())
            assert resp1.status_code == 201

        # Farmer 2 books slot_1 (Reaches capacity limit = 2)
        su2 = make_mock_user(user_id="farmer-uuid-2")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su2

            resp2 = client.post("/api/bookings", json={"slot_id": slot_id}, headers=auth_header())
            assert resp2.status_code == 201

        # Third farmer attempt (Slot full -> 409 Conflict)
        with client.application.app_context():
            u3 = User(supabase_user_id="farmer-uuid-3", role=UserRole.FARMER, is_active=True)
            db.session.add(u3)
            db.session.flush()
            f3 = Farmer(user_id=u3.id, name="Kisan 3", phone="9876543212")
            db.session.add(f3)
            db.session.commit()

        su3 = make_mock_user(user_id="farmer-uuid-3")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su3

            resp3 = client.post("/api/bookings", json={"slot_id": slot_id}, headers=auth_header())
            assert resp3.status_code == 409
            assert "fully booked" in resp3.get_json()["message"].lower()

    def test_duplicate_booking_for_same_slot_rejected(self, client, farmer_user, base_booking_data):
        slot_id = base_booking_data["slot_2"].id
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            # First booking -> 201
            resp1 = client.post("/api/bookings", json={"slot_id": slot_id}, headers=auth_header())
            assert resp1.status_code == 201

            # Second booking for same slot -> 409 Conflict
            resp2 = client.post("/api/bookings", json={"slot_id": slot_id}, headers=auth_header())
            assert resp2.status_code == 409
            assert "already have a booking" in resp2.get_json()["message"].lower()

    def test_overlapping_time_booking_rejected(self, client, farmer_user, base_booking_data):
        # Slot 1: 09:00 - 10:00
        # Slot 3: 09:30 - 10:30 (Overlaps)
        # Slot 2: 10:00 - 11:00 (Adjacent)
        s1_id = base_booking_data["slot_1"].id
        s2_id = base_booking_data["slot_2"].id
        s3_id = base_booking_data["slot_3"].id

        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            # 1. Book Slot 1 (09:00 - 10:00)
            r1 = client.post("/api/bookings", json={"slot_id": s1_id}, headers=auth_header())
            assert r1.status_code == 201

            # 2. Attempt to book Slot 3 (09:30 - 10:30, Overlaps) -> 409 Conflict
            r3 = client.post("/api/bookings", json={"slot_id": s3_id}, headers=auth_header())
            assert r3.status_code == 409
            assert "overlapping" in r3.get_json()["message"].lower()

            # 3. Book Slot 2 (10:00 - 11:00, Adjacent) -> Allowed (201)
            r2 = client.post("/api/bookings", json={"slot_id": s2_id}, headers=auth_header())
            assert r2.status_code == 201


class TestBookingOwnershipAndCancellation:
    """Tests for listing, viewing, and cancelling bookings."""

    def test_farmer_can_list_and_view_own_bookings(self, client, farmer_user, base_booking_data):
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            # Create booking
            b_resp = client.post("/api/bookings", json={"slot_id": base_booking_data["slot_2"].id}, headers=auth_header())
            booking_id = b_resp.get_json()["booking"]["id"]

            # List my bookings
            list_resp = client.get("/api/bookings/my", headers=auth_header())
            assert list_resp.status_code == 200
            bookings = list_resp.get_json()["bookings"]
            assert len(bookings) >= 1
            assert bookings[0]["id"] == booking_id

            # Get booking by ID
            get_resp = client.get(f"/api/bookings/{booking_id}", headers=auth_header())
            assert get_resp.status_code == 200
            assert get_resp.get_json()["booking"]["id"] == booking_id

    def test_farmer_cannot_view_or_cancel_other_farmer_booking(self, client, farmer_user, farmer_user_2, base_booking_data):
        # Farmer 1 creates booking
        su1 = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su1

            b_resp = client.post("/api/bookings", json={"slot_id": base_booking_data["slot_2"].id}, headers=auth_header())
            booking_id = b_resp.get_json()["booking"]["id"]

        # Farmer 2 tries to view and cancel Farmer 1's booking
        su2 = make_mock_user(user_id="farmer-uuid-2")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su2

            # View -> 404
            get_resp = client.get(f"/api/bookings/{booking_id}", headers=auth_header())
            assert get_resp.status_code == 404

            # Cancel -> 404
            cancel_resp = client.put(f"/api/bookings/{booking_id}/cancel", headers=auth_header())
            assert cancel_resp.status_code == 404

    def test_cancellation_frees_capacity_and_allows_rebooking(self, client, farmer_user, base_booking_data):
        slot_id = base_booking_data["slot_2"].id
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            # 1. Create booking
            b_resp = client.post("/api/bookings", json={"slot_id": slot_id}, headers=auth_header())
            booking_id = b_resp.get_json()["booking"]["id"]

            # 2. Cancel booking
            c_resp = client.put(f"/api/bookings/{booking_id}/cancel", headers=auth_header())
            assert c_resp.status_code == 200
            assert c_resp.get_json()["booking"]["status"] == "CANCELLED"

            # 3. Cannot cancel twice -> 400
            c2_resp = client.put(f"/api/bookings/{booking_id}/cancel", headers=auth_header())
            assert c2_resp.status_code == 400

            # 4. Re-book same slot now that previous booking is cancelled -> Allowed (201)
            rebook_resp = client.post("/api/bookings", json={"slot_id": slot_id}, headers=auth_header())
            assert rebook_resp.status_code == 201

    def test_cancelled_slot_and_past_slot_rejected(self, client, farmer_user, base_booking_data, app):
        with app.app_context():
            tomorrow = date.today() + timedelta(days=1)
            yesterday = date.today() - timedelta(days=1)

            # Cancelled slot
            s_cancelled = Slot(
                centre_id=base_booking_data["c_active"].id,
                crop_id=base_booking_data["cr_active"].id,
                slot_date=tomorrow,
                start_time=time(14, 0),
                end_time=time(15, 0),
                capacity=5,
                status=SlotStatus.CANCELLED,
            )
            # Past date slot
            s_past = Slot(
                centre_id=base_booking_data["c_active"].id,
                crop_id=base_booking_data["cr_active"].id,
                slot_date=yesterday,
                start_time=time(9, 0),
                end_time=time(10, 0),
                capacity=5,
                status=SlotStatus.OPEN,
            )
            db.session.add_all([s_cancelled, s_past])
            db.session.commit()
            s_cancelled_id = s_cancelled.id
            s_past_id = s_past.id

        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            # Cancelled slot attempt -> 400
            r1 = client.post("/api/bookings", json={"slot_id": s_cancelled_id}, headers=auth_header())
            assert r1.status_code == 400

            # Past slot attempt -> 400
            r2 = client.post("/api/bookings", json={"slot_id": s_past_id}, headers=auth_header())
            assert r2.status_code == 400

    def test_capacity_status_rules_and_unmodified_capacity(self, client, farmer_user, base_booking_data, app):
        slot = base_booking_data["slot_1"]  # capacity = 2
        initial_capacity = slot.capacity

        with app.app_context():
            farmer = Farmer.query.filter_by(name="Ramesh Kumar").first()
            # Add existing CANCELLED, COMPLETED, NO_SHOW bookings on this slot
            b_cancelled = Booking(farmer_id=farmer.id, slot_id=slot.id, status=BookingStatus.CANCELLED)
            b_completed = Booking(farmer_id=farmer.id, slot_id=slot.id, status=BookingStatus.COMPLETED)
            b_noshow = Booking(farmer_id=farmer.id, slot_id=slot.id, status=BookingStatus.NO_SHOW)
            db.session.add_all([b_cancelled, b_completed, b_noshow])
            db.session.commit()

        # They should NOT count toward capacity. PENDING does count.
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            # Booking succeeds
            resp = client.post("/api/bookings", json={"slot_id": slot.id}, headers=auth_header())
            assert resp.status_code == 201

        with app.app_context():
            db_slot = db.session.get(Slot, slot.id)
            # Assert Slot.capacity was NEVER modified by booking creation
            assert db_slot.capacity == initial_capacity

    def test_non_blocking_statuses_and_different_dates(self, client, farmer_user, base_booking_data, app):
        with app.app_context():
            farmer = Farmer.query.filter_by(name="Ramesh Kumar").first()
            day_after = date.today() + timedelta(days=2)

            # Slot on different date with same time
            s_diff_date = Slot(
                centre_id=base_booking_data["c_active"].id,
                crop_id=base_booking_data["cr_active"].id,
                slot_date=day_after,
                start_time=time(9, 0),
                end_time=time(10, 0),
                capacity=5,
                status=SlotStatus.OPEN,
            )
            db.session.add(s_diff_date)
            db.session.commit()

            # Add COMPLETED booking on slot_1 (09:00 - 10:00)
            b_completed = Booking(farmer_id=farmer.id, slot_id=base_booking_data["slot_1"].id, status=BookingStatus.COMPLETED)
            db.session.add(b_completed)
            db.session.commit()

            diff_date_slot_id = s_diff_date.id
            slot_3_id = base_booking_data["slot_3"].id  # 09:30 - 10:30 on tomorrow

        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            # COMPLETED booking on slot_1 does not block overlapping slot_3 -> 201 Created
            r1 = client.post("/api/bookings", json={"slot_id": slot_3_id}, headers=auth_header())
            assert r1.status_code == 201

            # Different date slot booking -> 201 Created
            r2 = client.post("/api/bookings", json={"slot_id": diff_date_slot_id}, headers=auth_header())
            assert r2.status_code == 201

    def test_impersonation_prevention(self, client, farmer_user, base_booking_data, app):
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            # Send payload with explicit attempt to impersonate farmer_id = 99999
            resp = client.post(
                "/api/bookings",
                json={"slot_id": base_booking_data["slot_2"].id, "farmer_id": 99999},
                headers=auth_header()
            )
            assert resp.status_code == 201

            with app.app_context():
                farmer = Farmer.query.filter_by(name="Ramesh Kumar").first()
                booking = Booking.query.filter_by(slot_id=base_booking_data["slot_2"].id).first()
                # Verify booking was assigned to the authenticated user's farmer ID, ignoring 99999
                assert booking.farmer_id == farmer.id
                assert booking.farmer_id != 99999

    def test_cancel_pending_and_prohibit_completed_no_show(self, client, farmer_user, base_booking_data, app):
        with app.app_context():
            farmer = Farmer.query.filter_by(name="Ramesh Kumar").first()
            b_pending = Booking(farmer_id=farmer.id, slot_id=base_booking_data["slot_2"].id, status=BookingStatus.PENDING)
            b_completed = Booking(farmer_id=farmer.id, slot_id=base_booking_data["slot_3"].id, status=BookingStatus.COMPLETED)
            b_noshow = Booking(farmer_id=farmer.id, slot_id=base_booking_data["slot_1"].id, status=BookingStatus.NO_SHOW)
            db.session.add_all([b_pending, b_completed, b_noshow])
            db.session.commit()
            pending_id = b_pending.id
            completed_id = b_completed.id
            noshow_id = b_noshow.id

        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            # PENDING booking cancellation -> 200 OK
            r_pending = client.put(f"/api/bookings/{pending_id}/cancel", headers=auth_header())
            assert r_pending.status_code == 200
            assert r_pending.get_json()["booking"]["status"] == "CANCELLED"

            # COMPLETED booking cancellation -> 400 Bad Request
            r_completed = client.put(f"/api/bookings/{completed_id}/cancel", headers=auth_header())
            assert r_completed.status_code == 400
            assert "completed" in r_completed.get_json()["messages"][0].lower()

            # NO_SHOW booking cancellation -> 400 Bad Request
            r_noshow = client.put(f"/api/bookings/{noshow_id}/cancel", headers=auth_header())
            assert r_noshow.status_code == 400
            assert "no-show" in r_noshow.get_json()["messages"][0].lower()


class TestTokenGeneration:
    """Tests for Task 8 Procurement Token Generation."""

    def test_token_generation_format_and_persistence(self, client, farmer_user, base_booking_data):
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            slot_id = base_booking_data["slot_1"].id
            resp = client.post("/api/bookings", json={"slot_id": slot_id}, headers=auth_header())
            assert resp.status_code == 201
            b_data = resp.get_json()["booking"]

            # Token assertions
            assert b_data["token_number"] == "K-0001"
            assert b_data["token_generated_at"] is not None

            # Persistence assertion across GET calls
            get_resp = client.get(f"/api/bookings/{b_data['id']}", headers=auth_header())
            assert get_resp.status_code == 200
            get_b = get_resp.get_json()["booking"]
            assert get_b["token_number"] == "K-0001"
            assert get_b["token_generated_at"] == b_data["token_generated_at"]

    def test_sequential_token_allocation_and_scope(self, client, farmer_user, farmer_user_2, base_booking_data, app):
        with app.app_context():
            tomorrow = date.today() + timedelta(days=1)
            day_after = date.today() + timedelta(days=2)

            # Centre B slot on tomorrow
            s_centre_b = Slot(
                centre_id=base_booking_data["c_inactive"].id, # temp reactivate for test
                crop_id=base_booking_data["cr_active"].id,
                slot_date=tomorrow,
                start_time=time(15, 0),
                end_time=time(16, 0),
                capacity=5,
                status=SlotStatus.OPEN,
            )
            # Re-activate c_inactive for test scope
            c_b = db.session.get(Centre, base_booking_data["c_inactive"].id)
            c_b.is_active = True

            # Centre A slot on day_after
            s_day_after = Slot(
                centre_id=base_booking_data["c_active"].id,
                crop_id=base_booking_data["cr_active"].id,
                slot_date=day_after,
                start_time=time(9, 0),
                end_time=time(10, 0),
                capacity=5,
                status=SlotStatus.OPEN,
            )
            db.session.add_all([s_centre_b, s_day_after])
            db.session.commit()
            centre_b_slot_id = s_centre_b.id
            day_after_slot_id = s_day_after.id

        slot_a1_id = base_booking_data["slot_1"].id

        # 1. Farmer 1 books Centre A, Tomorrow -> K-0001
        su1 = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su1

            r1 = client.post("/api/bookings", json={"slot_id": slot_a1_id}, headers=auth_header())
            assert r1.status_code == 201
            assert r1.get_json()["booking"]["token_number"] == "K-0001"

        # 2. Farmer 2 books Centre A, Tomorrow -> K-0002
        su2 = make_mock_user(user_id="farmer-uuid-2")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su2

            r2 = client.post("/api/bookings", json={"slot_id": slot_a1_id}, headers=auth_header())
            assert r2.status_code == 201
            assert r2.get_json()["booking"]["token_number"] == "K-0002"

        # 3. Farmer 1 books Centre B, Tomorrow -> K-0001 (scoped to Centre B)
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su1

            r3 = client.post("/api/bookings", json={"slot_id": centre_b_slot_id}, headers=auth_header())
            assert r3.status_code == 201
            assert r3.get_json()["booking"]["token_number"] == "K-0001"

        # 4. Farmer 1 books Centre A, Day After -> K-0001 (scoped to Day After)
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su1

            r4 = client.post("/api/bookings", json={"slot_id": day_after_slot_id}, headers=auth_header())
            assert r4.status_code == 201
            assert r4.get_json()["booking"]["token_number"] == "K-0001"

    def test_cancellation_retains_token_and_does_not_reuse(self, client, farmer_user, farmer_user_2, base_booking_data, app):
        slot_id = base_booking_data["slot_2"].id

        # 1. Farmer 1 books -> K-0001
        su1 = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su1

            r1 = client.post("/api/bookings", json={"slot_id": slot_id}, headers=auth_header())
            b1_id = r1.get_json()["booking"]["id"]
            assert r1.get_json()["booking"]["token_number"] == "K-0001"

            # Farmer 1 cancels K-0001
            c_resp = client.put(f"/api/bookings/{b1_id}/cancel", headers=auth_header())
            assert c_resp.status_code == 200
            assert c_resp.get_json()["booking"]["status"] == "CANCELLED"
            assert c_resp.get_json()["booking"]["token_number"] == "K-0001"

        # 2. Farmer 2 books same slot -> receives K-0002 (K-0001 is NOT reused)
        su2 = make_mock_user(user_id="farmer-uuid-2")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su2

            r2 = client.post("/api/bookings", json={"slot_id": slot_id}, headers=auth_header())
            assert r2.status_code == 201
            assert r2.get_json()["booking"]["token_number"] == "K-0002"

    def test_token_endpoint_security(self, client, farmer_user, farmer_user_2, base_booking_data):
        slot_id = base_booking_data["slot_1"].id

        # Farmer 1 creates booking
        su1 = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su1

            b_resp = client.post("/api/bookings", json={"slot_id": slot_id}, headers=auth_header())
            b_id = b_resp.get_json()["booking"]["id"]

            # Farmer 1 gets own token endpoint
            t_resp = client.get(f"/api/bookings/{b_id}/token", headers=auth_header())
            assert t_resp.status_code == 200
            t_data = t_resp.get_json()
            assert t_data["booking_id"] == b_id
            assert t_data["token_number"] == "K-0001"
            assert t_data["status"] == "CONFIRMED"

        # Farmer 2 tries to access Farmer 1's token endpoint -> 404 Not Found
        su2 = make_mock_user(user_id="farmer-uuid-2")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su2

            t2_resp = client.get(f"/api/bookings/{b_id}/token", headers=auth_header())
            assert t2_resp.status_code == 404

    def test_token_allocation_different_slots_same_centre_and_date(self, client, farmer_user, farmer_user_2, base_booking_data):
        # Slot 1 (09:00-10:00) and Slot 2 (10:00-11:00) both at Centre A on Tomorrow
        slot_1_id = base_booking_data["slot_1"].id
        slot_2_id = base_booking_data["slot_2"].id

        # Farmer 1 books Slot 1 -> K-0001
        su1 = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su1

            r1 = client.post("/api/bookings", json={"slot_id": slot_1_id}, headers=auth_header())
            assert r1.status_code == 201
            assert r1.get_json()["booking"]["token_number"] == "K-0001"

        # Farmer 2 books Slot 2 (different slot, same centre & date) -> K-0002
        su2 = make_mock_user(user_id="farmer-uuid-2")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su2

            r2 = client.post("/api/bookings", json={"slot_id": slot_2_id}, headers=auth_header())
            assert r2.status_code == 201
            assert r2.get_json()["booking"]["token_number"] == "K-0002"



