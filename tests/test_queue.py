"""Tests for Task 9 Procurement Queue Management."""

from datetime import date, time, timedelta
from unittest.mock import patch, MagicMock

import pytest
from app.extensions import db
from app.models import (
    UserRole,
    User,
    Centre,
    Crop,
    Slot,
    SlotStatus,
    Booking,
    BookingStatus,
    Farmer,
    Staff,
    Procurement,
    ProcurementStatus,
)


def make_mock_user(user_id="farmer-uuid-1", role=UserRole.FARMER):
    u = MagicMock()
    u.id = user_id
    u.user_metadata = {"role": role}
    return u


def auth_header(token="valid-token"):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def queue_test_data(app):
    """Fixture creating users, centres, crops, slots, and multiple farmers for queue testing."""
    with app.app_context():
        # 1. Users
        u1 = User(supabase_user_id="farmer-uuid-1", role=UserRole.FARMER, is_active=True)
        u2 = User(supabase_user_id="farmer-uuid-2", role=UserRole.FARMER, is_active=True)
        u3 = User(supabase_user_id="farmer-uuid-3", role=UserRole.FARMER, is_active=True)
        u4 = User(supabase_user_id="farmer-uuid-4", role=UserRole.FARMER, is_active=True)
        u_staff = User(supabase_user_id="staff-uuid-1", role=UserRole.STAFF, is_active=True)
        db.session.add_all([u1, u2, u3, u4, u_staff])
        db.session.commit()

        # 2. Centres
        c_a = Centre(
            name="Queue Centre A",
            location="Location A",
            opening_time=time(8, 0),
            closing_time=time(18, 0),
            daily_capacity=100,
            is_active=True,
            average_processing_minutes=15,
        )
        c_b = Centre(
            name="Queue Centre B",
            location="Location B",
            opening_time=time(8, 0),
            closing_time=time(18, 0),
            daily_capacity=100,
            is_active=True,
            average_processing_minutes=20,
        )
        db.session.add_all([c_a, c_b])
        db.session.commit()

        # 3. Crop
        crop = Crop(name="Wheat Queue", is_active=True)
        db.session.add(crop)
        db.session.commit()

        # 4. Dates
        d_today = date.today() + timedelta(days=1)
        d_tomorrow = date.today() + timedelta(days=2)

        # 5. Slots at Centre A
        s_a_slot1 = Slot(
            centre_id=c_a.id,
            crop_id=crop.id,
            slot_date=d_today,
            start_time=time(9, 0),
            end_time=time(10, 0),
            capacity=10,
            status=SlotStatus.OPEN,
        )
        s_a_slot2 = Slot(
            centre_id=c_a.id,
            crop_id=crop.id,
            slot_date=d_today,
            start_time=time(10, 0),
            end_time=time(11, 0),
            capacity=10,
            status=SlotStatus.OPEN,
        )
        s_a_next_day = Slot(
            centre_id=c_a.id,
            crop_id=crop.id,
            slot_date=d_tomorrow,
            start_time=time(9, 0),
            end_time=time(10, 0),
            capacity=10,
            status=SlotStatus.OPEN,
        )

        # 6. Slot at Centre B
        s_b_slot1 = Slot(
            centre_id=c_b.id,
            crop_id=crop.id,
            slot_date=d_today,
            start_time=time(9, 0),
            end_time=time(10, 0),
            capacity=10,
            status=SlotStatus.OPEN,
        )

        db.session.add_all([s_a_slot1, s_a_slot2, s_a_next_day, s_b_slot1])
        db.session.commit()

        # 7. Farmers
        f1 = Farmer(user_id=u1.id, name="Farmer One", phone="9000000001", address="Addr 1", city="District 1", state="State 1")
        f2 = Farmer(user_id=u2.id, name="Farmer Two", phone="9000000002", address="Addr 2", city="District 2", state="State 2")
        f3 = Farmer(user_id=u3.id, name="Farmer Three", phone="9000000003", address="Addr 3", city="District 3", state="State 3")
        f4 = Farmer(user_id=u4.id, name="Farmer Four", phone="9000000004", address="Addr 4", city="District 4", state="State 4")
        db.session.add_all([f1, f2, f3, f4])
        db.session.commit()

        # 8. Staff user for Centre A
        staff = Staff(user_id=u_staff.id, centre_id=c_a.id, name="Staff Member", phone="9111111111")
        db.session.add(staff)
        db.session.commit()

        return {
            "c_a_id": c_a.id,
            "c_b_id": c_b.id,
            "crop_id": crop.id,
            "d_today": d_today,
            "d_tomorrow": d_tomorrow,
            "s_a_slot1_id": s_a_slot1.id,
            "s_a_slot2_id": s_a_slot2.id,
            "s_a_next_day_id": s_a_next_day.id,
            "s_b_slot1_id": s_b_slot1.id,
            "f1_id": f1.id,
            "f2_id": f2.id,
            "f3_id": f3.id,
            "f4_id": f4.id,
            "staff_id": staff.id,
        }


class TestQueueManagement:
    """Comprehensive test suite for Task 9 Queue Management."""

    def test_basic_queue_position_and_wait_time(self, client, queue_test_data, app):
        """Test sequential token queue calculation for active bookings."""
        with app.app_context():
            slot = db.session.get(Slot, queue_test_data["s_a_slot1_id"])
            f1 = db.session.get(Farmer, queue_test_data["f1_id"])
            f2 = db.session.get(Farmer, queue_test_data["f2_id"])
            f3 = db.session.get(Farmer, queue_test_data["f3_id"])

            b1 = Booking(farmer_id=f1.id, slot_id=slot.id, token_number="K-0001", status=BookingStatus.CONFIRMED)
            b2 = Booking(farmer_id=f2.id, slot_id=slot.id, token_number="K-0002", status=BookingStatus.CONFIRMED)
            b3 = Booking(farmer_id=f3.id, slot_id=slot.id, token_number="K-0003", status=BookingStatus.CONFIRMED)
            db.session.add_all([b1, b2, b3])
            db.session.commit()
            b1_id, b2_id, b3_id = b1.id, b2.id, b3.id

        # Farmer 1 queue check
        su1 = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su1

            r1 = client.get(f"/api/queue/my/{b1_id}", headers=auth_header())
            assert r1.status_code == 200
            q1 = r1.get_json()
            assert q1["queue_position"] == 1
            assert q1["farmers_ahead"] == 0
            assert q1["estimated_wait_minutes"] == 0
            assert q1["is_active_queue"] is True

        # Farmer 2 queue check
        su2 = make_mock_user(user_id="farmer-uuid-2")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su2

            r2 = client.get(f"/api/queue/my/{b2_id}", headers=auth_header())
            assert r2.status_code == 200
            q2 = r2.get_json()
            assert q2["queue_position"] == 2
            assert q2["farmers_ahead"] == 1
            assert q2["estimated_wait_minutes"] == 15

        # Farmer 3 queue check
        su3 = make_mock_user(user_id="farmer-uuid-3")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su3

            r3 = client.get(f"/api/queue/my/{b3_id}", headers=auth_header())
            assert r3.status_code == 200
            q3 = r3.get_json()
            assert q3["queue_position"] == 3
            assert q3["farmers_ahead"] == 2
            assert q3["estimated_wait_minutes"] == 30

    def test_token_numeric_ordering(self, client, queue_test_data, app):
        """Verify queue orders by token integer suffix (K-0002 before K-0010), not DB ID or string order."""
        with app.app_context():
            slot = db.session.get(Slot, queue_test_data["s_a_slot1_id"])
            f1 = db.session.get(Farmer, queue_test_data["f1_id"])
            f2 = db.session.get(Farmer, queue_test_data["f2_id"])

            b10 = Booking(farmer_id=f1.id, slot_id=slot.id, token_number="K-0010", status=BookingStatus.CONFIRMED)
            b2 = Booking(farmer_id=f2.id, slot_id=slot.id, token_number="K-0002", status=BookingStatus.CONFIRMED)
            db.session.add_all([b10, b2])
            db.session.commit()
            b10_id, b2_id = b10.id, b2.id

        su2 = make_mock_user(user_id="farmer-uuid-2")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su2

            r2 = client.get(f"/api/queue/my/{b2_id}", headers=auth_header())
            assert r2.status_code == 200
            assert r2.get_json()["queue_position"] == 1
            assert r2.get_json()["farmers_ahead"] == 0

    def test_status_filtering_and_cancellation_shift(self, client, queue_test_data, app):
        """Verify CANCELLED/COMPLETED/NO_SHOW bookings vacate queue spots and remaining positions shift forward."""
        with app.app_context():
            slot = db.session.get(Slot, queue_test_data["s_a_slot1_id"])
            f1 = db.session.get(Farmer, queue_test_data["f1_id"])
            f2 = db.session.get(Farmer, queue_test_data["f2_id"])
            f3 = db.session.get(Farmer, queue_test_data["f3_id"])
            f4 = db.session.get(Farmer, queue_test_data["f4_id"])

            b1 = Booking(farmer_id=f1.id, slot_id=slot.id, token_number="K-0001", status=BookingStatus.CONFIRMED)
            b2 = Booking(farmer_id=f2.id, slot_id=slot.id, token_number="K-0002", status=BookingStatus.CONFIRMED)
            b3 = Booking(farmer_id=f3.id, slot_id=slot.id, token_number="K-0003", status=BookingStatus.CONFIRMED)
            b4 = Booking(farmer_id=f4.id, slot_id=slot.id, token_number="K-0004", status=BookingStatus.CANCELLED)
            db.session.add_all([b1, b2, b3, b4])
            db.session.commit()
            b1_id, b2_id, b3_id, b4_id = b1.id, b2.id, b3.id, b4.id

        su4 = make_mock_user(user_id="farmer-uuid-4")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su4

            r4 = client.get(f"/api/queue/my/{b4_id}", headers=auth_header())
            assert r4.status_code == 200
            q4 = r4.get_json()
            assert q4["queue_position"] is None
            assert q4["farmers_ahead"] == 0

        with app.app_context():
            b2_obj = db.session.get(Booking, b2_id)
            b2_obj.status = BookingStatus.CANCELLED
            b1_obj = db.session.get(Booking, b1_id)
            b1_obj.status = BookingStatus.COMPLETED
            db.session.commit()

        su3 = make_mock_user(user_id="farmer-uuid-3")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su3

            r3 = client.get(f"/api/queue/my/{b3_id}", headers=auth_header())
            assert r3.status_code == 200
            q3 = r3.get_json()
            assert q3["queue_position"] == 1
            assert q3["farmers_ahead"] == 0

    def test_scope_isolation_centre_and_date(self, client, queue_test_data, app):
        """Verify queues are strictly scoped by centre and slot_date."""
        with app.app_context():
            slot_a1 = db.session.get(Slot, queue_test_data["s_a_slot1_id"])
            slot_a_next = db.session.get(Slot, queue_test_data["s_a_next_day_id"])
            slot_b1 = db.session.get(Slot, queue_test_data["s_b_slot1_id"])

            f1 = db.session.get(Farmer, queue_test_data["f1_id"])
            f2 = db.session.get(Farmer, queue_test_data["f2_id"])

            b_a1 = Booking(farmer_id=f1.id, slot_id=slot_a1.id, token_number="K-0001", status=BookingStatus.CONFIRMED)
            b_b1 = Booking(farmer_id=f1.id, slot_id=slot_b1.id, token_number="K-0001", status=BookingStatus.CONFIRMED)
            b_anext = Booking(farmer_id=f2.id, slot_id=slot_a_next.id, token_number="K-0001", status=BookingStatus.CONFIRMED)

            db.session.add_all([b_a1, b_b1, b_anext])
            db.session.commit()
            b_b1_id = b_b1.id

        su1 = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su1

            rb = client.get(f"/api/queue/my/{b_b1_id}", headers=auth_header())
            assert rb.status_code == 200
            qb = rb.get_json()
            assert qb["queue_position"] == 1
            assert qb["centre"] == "Queue Centre B"
            assert qb["average_processing_time"] == 20

    def test_ownership_and_auth_security(self, client, queue_test_data, app):
        """Farmer A cannot access Farmer B's queue data, and unauthenticated requests are rejected."""
        with app.app_context():
            slot = db.session.get(Slot, queue_test_data["s_a_slot1_id"])
            f1 = db.session.get(Farmer, queue_test_data["f1_id"])
            b1 = Booking(farmer_id=f1.id, slot_id=slot.id, token_number="K-0001", status=BookingStatus.CONFIRMED)
            db.session.add(b1)
            db.session.commit()
            b1_id = b1.id

        r_unauth = client.get(f"/api/queue/my/{b1_id}")
        assert r_unauth.status_code == 401

        su2 = make_mock_user(user_id="farmer-uuid-2")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su2

            r_f2 = client.get(f"/api/queue/my/{b1_id}", headers=auth_header())
            assert r_f2.status_code == 404

    def test_staff_admin_centre_queue_endpoint(self, client, queue_test_data, app):
        """STAFF or ADMIN can view full active centre queue, while FARMER is forbidden."""
        with app.app_context():
            c_a_id = queue_test_data["c_a_id"]
            slot = db.session.get(Slot, queue_test_data["s_a_slot1_id"])
            f1 = db.session.get(Farmer, queue_test_data["f1_id"])
            f2 = db.session.get(Farmer, queue_test_data["f2_id"])

            b1 = Booking(farmer_id=f1.id, slot_id=slot.id, token_number="K-0001", status=BookingStatus.CONFIRMED)
            b2 = Booking(farmer_id=f2.id, slot_id=slot.id, token_number="K-0002", status=BookingStatus.CONFIRMED)
            db.session.add_all([b1, b2])
            db.session.commit()
            d_str = queue_test_data["d_today"].isoformat()

        su_farmer = make_mock_user(user_id="farmer-uuid-1", role=UserRole.FARMER)
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su_farmer

            r_farm = client.get(f"/api/queue/centre/{c_a_id}?date={d_str}", headers=auth_header())
            assert r_farm.status_code == 403

        su_staff = make_mock_user(user_id="staff-uuid-1", role=UserRole.STAFF)
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su_staff

            r_staff = client.get(f"/api/queue/centre/{c_a_id}?date={d_str}", headers=auth_header())
            assert r_staff.status_code == 200
            q_data = r_staff.get_json()
            assert q_data["centre_id"] == c_a_id
            assert q_data["total_waiting"] == 2

class TestStaffQueueDateVisibility:
    """Regression tests for the Staff queue visibility bug.

    Mirrors the verified production scenario: staff03 assigned to centre 7 and
    booking 27 (token K-0001, CONFIRMED, farmer 5) on slot 24 dated 2026-09-15.
    The dashboard must request /api/queue/centre/<id>?date=YYYY-MM-DD explicitly,
    otherwise queue_service defaults to date.today() and hides the booking.
    """

    @pytest.fixture
    def staff_queue_date_scenario(self, app):
        """Create the production bug scenario: staff03 at centre 7 + booking 27."""
        with app.app_context():
            u_staff = User(supabase_user_id="staff03", role=UserRole.STAFF, is_active=True)
            u_farmer = User(supabase_user_id="farmer05", role=UserRole.FARMER, is_active=True)
            db.session.add_all([u_staff, u_farmer])
            db.session.flush()

            centre = Centre(
                id=7,
                name="Centre 7 Procurement Hub",
                location="Karnal",
                opening_time=time(9, 0),
                closing_time=time(17, 0),
                daily_capacity=100,
                average_processing_minutes=15,
                is_active=True,
            )
            staff = Staff(user_id=u_staff.id, centre_id=7, name="Staff 03", phone="9111111103")
            farmer = Farmer(id=5, user_id=u_farmer.id, name="Farmer 05", phone="9000000005")
            crop = Crop(name="Paddy", is_active=True)
            db.session.add_all([centre, staff, farmer, crop])
            db.session.flush()

            slot = Slot(
                id=24,
                centre_id=7,
                crop_id=crop.id,
                slot_date=date(2026, 9, 15),
                start_time=time(9, 0),
                end_time=time(10, 0),
                capacity=10,
                status=SlotStatus.OPEN,
            )
            db.session.add(slot)
            db.session.flush()

            booking = Booking(
                id=27,
                farmer_id=5,
                slot_id=24,
                token_number="K-0001",
                status=BookingStatus.CONFIRMED,
            )
            db.session.add(booking)
            db.session.commit()

            centre_a_id = centre.id
            slot_a_id = slot.id
            booking_a1_id = booking.id
            crop_id = crop.id

        return {
            "staff_sub": "staff03",
            "centre_a_id": centre_a_id,
            "centre_b_id": 8,
            "slot_a_id": slot_a_id,
            "booking_a1_id": booking_a1_id,
            "crop_id": crop_id,
            "date_str": "2026-09-15",
        }

    def _add_farmer_with_booking(self, app, sub, phone, token, status, slot_id=24,
                                 procurement_status=None, booking_date=date(2026, 9, 15)):
        """Create a farmer + booking (optionally with a procurement record) and return the booking id."""
        with app.app_context():
            u = User(supabase_user_id=sub, role=UserRole.FARMER, is_active=True)
            db.session.add(u)
            db.session.flush()
            f = Farmer(user_id=u.id, name=f"Farmer {sub}", phone=phone)
            db.session.add(f)
            db.session.flush()
            b = Booking(farmer_id=f.id, slot_id=slot_id, token_number=token, status=status, booking_date=booking_date)
            db.session.add(b)
            db.session.flush()
            if procurement_status:
                db.session.add(Procurement(booking_id=b.id, procurement_status=procurement_status))
            db.session.commit()
            return b.id

    def staff_queue_call(self, client, sub_id, url):
        """Call a staff-protected endpoint with a mocked Supabase token."""
        with patch("app.auth.decorators.verify_token") as mock_vt:
            mock_user = MagicMock()
            mock_user.id = sub_id
            mock_user.email = f"{sub_id}@example.com"
            mock_vt.return_value = mock_user
            return client.get(url, headers=auth_header())

    def test_staff03_sees_booking_27_at_centre_7_on_2026_09_15(self, client, staff_queue_date_scenario):
        """staff03 must see booking 27 for centre 7 on 2026-09-15 when the date is sent explicitly."""
        r = self.staff_queue_call(client, "staff03", "/api/queue/centre/7?date=2026-09-15")
        assert r.status_code == 200
        data = r.get_json()
        assert data["centre_id"] == 7
        assert data["date"] == "2026-09-15"

        queue_ids = [q["booking_id"] for q in data["queue"]]
        assert staff_queue_date_scenario["booking_a1_id"] in queue_ids
        entry = next(q for q in data["queue"] if q["booking_id"] == staff_queue_date_scenario["booking_a1_id"])
        assert entry["token_number"] == "K-0001"
        assert entry["queue_position"] == 1
        assert entry["status"] == BookingStatus.CONFIRMED

        # Response-key contract relied on by the staff dashboard stat cards
        assert data["total_waiting"] == 1
        assert data["opening_time"] == "09:00"
        assert data["closing_time"] == "17:00"
        assert data["daily_capacity"] == 100
        assert data["average_processing_time"] == 15

    def test_without_date_param_defaults_to_server_today(self, client, staff_queue_date_scenario):
        """Root-cause regression: omitting ?date hides 2026-09-15 bookings when server date differs."""
        with patch("app.services.queue_service.date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 14)
            r = self.staff_queue_call(client, "staff03", "/api/queue/centre/7")
            assert r.status_code == 200
            data = r.get_json()
            assert data["date"] == "2026-09-14"
            assert [q["booking_id"] for q in data["queue"]] == []

    def test_staff03_cannot_access_another_centre(self, client, staff_queue_date_scenario):
        """staff03 (centre 7) is denied access to another centre, with or without a date param."""
        r = self.staff_queue_call(client, "staff03", "/api/queue/centre/8?date=2026-09-15")
        assert r.status_code == 403
        assert "Access denied" in r.get_json()["message"]

        r_no_date = self.staff_queue_call(client, "staff03", "/api/queue/centre/8")
        assert r_no_date.status_code == 403

    def test_selecting_another_date_changes_displayed_queue(self, client, app, staff_queue_date_scenario):
        """The displayed queue must change when the selected procurement date changes."""
        with app.app_context():
            slot_next = Slot(
                centre_id=7,
                crop_id=staff_queue_date_scenario["crop_id"],
                slot_date=date(2026, 9, 16),
                start_time=time(9, 0),
                end_time=time(10, 0),
                capacity=10,
                status=SlotStatus.OPEN,
            )
            db.session.add(slot_next)
            db.session.commit()
            slot_next_id = slot_next.id

        b_next_id = self._add_farmer_with_booking(
            app, "farmer06", "9000000006", "K-0002", BookingStatus.CONFIRMED, slot_id=slot_next_id
        )

        r15 = self.staff_queue_call(client, "staff03", "/api/queue/centre/7?date=2026-09-15")
        ids_15 = [q["booking_id"] for q in r15.get_json()["queue"]]
        assert staff_queue_date_scenario["booking_a1_id"] in ids_15
        assert b_next_id not in ids_15

        r16 = self.staff_queue_call(client, "staff03", "/api/queue/centre/7?date=2026-09-16")
        ids_16 = [q["booking_id"] for q in r16.get_json()["queue"]]
        assert b_next_id in ids_16
        assert staff_queue_date_scenario["booking_a1_id"] not in ids_16

    def test_pending_and_confirmed_bookings_appear(self, client, app, staff_queue_date_scenario):
        """PENDING and CONFIRMED active bookings are both visible to staff."""
        pending_id = self._add_farmer_with_booking(
            app, "farmer06", "9000000006", "K-0002", BookingStatus.PENDING
        )
        r = self.staff_queue_call(client, "staff03", "/api/queue/centre/7?date=2026-09-15")
        assert r.status_code == 200
        data = r.get_json()
        queue_ids = [q["booking_id"] for q in data["queue"]]
        assert staff_queue_date_scenario["booking_a1_id"] in queue_ids
        assert pending_id in queue_ids
        assert data["total_waiting"] == 2

        statuses = {q["booking_id"]: q["status"] for q in data["queue"]}
        assert statuses[pending_id] == BookingStatus.PENDING
        assert statuses[staff_queue_date_scenario["booking_a1_id"]] == BookingStatus.CONFIRMED

    def test_cancelled_completed_rejected_bookings_not_in_queue(self, client, app, staff_queue_date_scenario):
        """CANCELLED/COMPLETED booking statuses and COMPLETED/REJECTED procurements are excluded."""
        cancelled_id = self._add_farmer_with_booking(
            app, "farmer06", "9000000006", "K-0002", BookingStatus.CANCELLED
        )
        completed_booking_id = self._add_farmer_with_booking(
            app, "farmer07", "9000000007", "K-0003", BookingStatus.COMPLETED
        )
        proc_completed_id = self._add_farmer_with_booking(
            app, "farmer08", "9000000008", "K-0004", BookingStatus.CONFIRMED,
            procurement_status=ProcurementStatus.COMPLETED,
        )
        proc_rejected_id = self._add_farmer_with_booking(
            app, "farmer09", "9000000009", "K-0005", BookingStatus.CONFIRMED,
            procurement_status=ProcurementStatus.REJECTED,
        )

        r = self.staff_queue_call(client, "staff03", "/api/queue/centre/7?date=2026-09-15")
        assert r.status_code == 200
        data = r.get_json()
        queue_ids = [q["booking_id"] for q in data["queue"]]

        assert staff_queue_date_scenario["booking_a1_id"] in queue_ids
        assert cancelled_id not in queue_ids
        assert completed_booking_id not in queue_ids
        assert proc_completed_id not in queue_ids
        assert proc_rejected_id not in queue_ids
        assert data["total_waiting"] == 1

    def test_admin_can_access_any_centre_with_staff_date_filter(self, client, app, staff_queue_date_scenario):
        """ADMIN access to all centres is preserved (centre isolation bypassed)."""
        with app.app_context():
            u_admin = User(supabase_user_id="admin-sub-7", role=UserRole.ADMIN, is_active=True)
            db.session.add(u_admin)
            db.session.commit()

        r = self.staff_queue_call(client, "admin-sub-7", "/api/queue/centre/7?date=2026-09-15")
        assert r.status_code == 200
        assert staff_queue_date_scenario["booking_a1_id"] in [q["booking_id"] for q in r.get_json()["queue"]]