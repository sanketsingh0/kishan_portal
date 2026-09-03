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
