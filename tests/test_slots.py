"""Tests for Slot Management API (/api/slots).

Covers:
- Model relationships and status enum
- Listing slots with filtering (farmers see only upcoming OPEN slots)
- Slot creation, updates, and soft cancellation (STAFF & ADMIN authorized; FARMER forbidden)
- Validations (inactive centre/crop, past dates, time range, positive capacity)
- Interval overlap detection
- Centre daily capacity constraint enforcement
"""

import pytest
from datetime import date, time, timedelta
from unittest.mock import MagicMock, patch

from app.extensions import db
from app.models import User, Centre, Crop, Slot, SlotStatus, UserRole


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
def base_data(app):
    """Fixture providing active centre, active crop, inactive centre, and inactive crop."""
    with app.app_context():
        c_active = Centre(
            name="Main Procurement Centre",
            location="Karnal",
            opening_time=time(9, 0),
            closing_time=time(17, 0),
            daily_capacity=100,
            average_processing_minutes=15,
            is_active=True,
        )
        c_inactive = Centre(
            name="Closed Centre",
            location="Old Town",
            opening_time=time(9, 0),
            closing_time=time(17, 0),
            daily_capacity=50,
            average_processing_minutes=15,
            is_active=False,
        )
        cr_active = Crop(name="Wheat", category="Cereal", is_active=True)
        cr_inactive = Crop(name="Discontinued Crop", category="Other", is_active=False)

        db.session.add_all([c_active, c_inactive, cr_active, cr_inactive])
        db.session.commit()

        yield {
            "c_active": c_active,
            "c_inactive": c_inactive,
            "cr_active": cr_active,
            "cr_inactive": cr_inactive,
        }


class TestSlotModel:
    """Tests for Slot model structure and relationships."""

    def test_valid_slot_creation_and_relationships(self, app, base_data):
        with app.app_context():
            tomorrow = date.today() + timedelta(days=1)
            slot = Slot(
                centre_id=base_data["c_active"].id,
                crop_id=base_data["cr_active"].id,
                slot_date=tomorrow,
                start_time=time(9, 0),
                end_time=time(10, 0),
                capacity=20,
                status=SlotStatus.OPEN,
            )
            db.session.add(slot)
            db.session.commit()

            fetched = db.session.get(Slot, slot.id)
            assert fetched is not None
            assert fetched.centre.name == "Main Procurement Centre"
            assert fetched.crop.name == "Wheat"
            assert fetched.status == "OPEN"


class TestSlotAuthorizationMatrix:
    """Tests for Role-Based Access Control matrix on Slot APIs."""

    def test_farmer_can_list_upcoming_open_slots(self, client, farmer_user, base_data):
        with client.application.app_context():
            tomorrow = date.today() + timedelta(days=1)
            s1 = Slot(
                centre_id=base_data["c_active"].id,
                crop_id=base_data["cr_active"].id,
                slot_date=tomorrow,
                start_time=time(9, 0),
                end_time=time(10, 0),
                capacity=20,
                status=SlotStatus.OPEN,
            )
            db.session.add(s1)
            db.session.commit()

        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp = client.get("/api/slots", headers=auth_header())
            assert resp.status_code == 200

            slots = resp.get_json()["slots"]
            assert len(slots) >= 1
            assert slots[0]["status"] == "OPEN"

    def test_admin_and_staff_can_create_slots(self, client, staff_user, admin_user, base_data):
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        payload = {
            "centre_id": base_data["c_active"].id,
            "crop_id": base_data["cr_active"].id,
            "slot_date": tomorrow,
            "start_time": "09:00",
            "end_time": "10:00",
            "capacity": 25,
        }

        # Staff can create slot
        su_staff = make_mock_user(user_id="staff-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su_staff

            resp1 = client.post("/api/slots", json=payload, headers=auth_header())
            assert resp1.status_code == 201

        # Admin can create slot
        payload2 = dict(payload, start_time="10:00", end_time="11:00")
        su_admin = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su_admin

            resp2 = client.post("/api/slots", json=payload2, headers=auth_header())
            assert resp2.status_code == 201

    def test_farmer_cannot_create_slot(self, client, farmer_user, base_data):
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
            payload = {
                "centre_id": base_data["c_active"].id,
                "crop_id": base_data["cr_active"].id,
                "slot_date": tomorrow,
                "start_time": "09:00",
                "end_time": "10:00",
                "capacity": 25,
            }
            resp = client.post("/api/slots", json=payload, headers=auth_header())
            assert resp.status_code == 403

    def test_staff_and_admin_can_update_and_cancel_slot(self, client, app, staff_user, admin_user, base_data):
        with app.app_context():
            tomorrow = date.today() + timedelta(days=1)
            slot = Slot(
                centre_id=base_data["c_active"].id,
                crop_id=base_data["cr_active"].id,
                slot_date=tomorrow,
                start_time=time(9, 0),
                end_time=time(10, 0),
                capacity=20,
                status=SlotStatus.OPEN,
            )
            db.session.add(slot)
            db.session.commit()
            slot_id = slot.id

        su_staff = make_mock_user(user_id="staff-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su_staff

            # Update capacity
            resp1 = client.put(f"/api/slots/{slot_id}", json={"capacity": 30}, headers=auth_header())
            assert resp1.status_code == 200
            assert resp1.get_json()["slot"]["capacity"] == 30

            # Cancel slot
            resp2 = client.delete(f"/api/slots/{slot_id}", headers=auth_header())
            assert resp2.status_code == 200
            assert resp2.get_json()["slot"]["status"] == "CANCELLED"

    def test_farmer_cannot_update_or_cancel_slot(self, client, app, farmer_user, base_data):
        with app.app_context():
            tomorrow = date.today() + timedelta(days=1)
            slot = Slot(
                centre_id=base_data["c_active"].id,
                crop_id=base_data["cr_active"].id,
                slot_date=tomorrow,
                start_time=time(9, 0),
                end_time=time(10, 0),
                capacity=20,
                status=SlotStatus.OPEN,
            )
            db.session.add(slot)
            db.session.commit()
            slot_id = slot.id

        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp1 = client.put(f"/api/slots/{slot_id}", json={"capacity": 50}, headers=auth_header())
            assert resp1.status_code == 403

            resp2 = client.delete(f"/api/slots/{slot_id}", headers=auth_header())
            assert resp2.status_code == 403


class TestSlotValidationsAndConstraints:
    """Tests for validations, overlapping intervals, and capacity constraints."""

    def test_missing_or_inactive_centre_rejected(self, client, admin_user, base_data):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

            # Inactive centre
            payload = {
                "centre_id": base_data["c_inactive"].id,
                "crop_id": base_data["cr_active"].id,
                "slot_date": tomorrow,
                "start_time": "09:00",
                "end_time": "10:00",
                "capacity": 20,
            }
            resp = client.post("/api/slots", json=payload, headers=auth_header())
            assert resp.status_code == 400
            assert "Centre does not exist or is inactive." in resp.get_json()["messages"]

    def test_missing_or_inactive_crop_rejected(self, client, admin_user, base_data):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

            payload = {
                "centre_id": base_data["c_active"].id,
                "crop_id": base_data["cr_inactive"].id,
                "slot_date": tomorrow,
                "start_time": "09:00",
                "end_time": "10:00",
                "capacity": 20,
            }
            resp = client.post("/api/slots", json=payload, headers=auth_header())
            assert resp.status_code == 400
            assert "Crop does not exist or is inactive." in resp.get_json()["messages"]

    def test_past_date_rejected(self, client, admin_user, base_data):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

            payload = {
                "centre_id": base_data["c_active"].id,
                "crop_id": base_data["cr_active"].id,
                "slot_date": yesterday,
                "start_time": "09:00",
                "end_time": "10:00",
                "capacity": 20,
            }
            resp = client.post("/api/slots", json=payload, headers=auth_header())
            assert resp.status_code == 400
            assert "Slot date cannot be in the past." in resp.get_json()["messages"]

    def test_end_time_before_start_time_rejected(self, client, admin_user, base_data):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

            payload = {
                "centre_id": base_data["c_active"].id,
                "crop_id": base_data["cr_active"].id,
                "slot_date": tomorrow,
                "start_time": "10:00",
                "end_time": "09:00",  # End before start
                "capacity": 20,
            }
            resp = client.post("/api/slots", json=payload, headers=auth_header())
            assert resp.status_code == 400

    def test_zero_or_negative_capacity_rejected(self, client, admin_user, base_data):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

            payload = {
                "centre_id": base_data["c_active"].id,
                "crop_id": base_data["cr_active"].id,
                "slot_date": tomorrow,
                "start_time": "09:00",
                "end_time": "10:00",
                "capacity": 0,
            }
            resp = client.post("/api/slots", json=payload, headers=auth_header())
            assert resp.status_code == 400

    def test_overlapping_slot_rejected(self, client, admin_user, base_data):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")

            # Slot 1: 09:00 - 10:00
            payload1 = {
                "centre_id": base_data["c_active"].id,
                "crop_id": base_data["cr_active"].id,
                "slot_date": tomorrow,
                "start_time": "09:00",
                "end_time": "10:00",
                "capacity": 20,
            }
            resp1 = client.post("/api/slots", json=payload1, headers=auth_header())
            assert resp1.status_code == 201

            # Slot 2: Overlaps (09:30 - 10:30)
            payload2 = {
                "centre_id": base_data["c_active"].id,
                "crop_id": base_data["cr_active"].id,
                "slot_date": tomorrow,
                "start_time": "09:30",
                "end_time": "10:30",
                "capacity": 20,
            }
            resp2 = client.post("/api/slots", json=payload2, headers=auth_header())
            assert resp2.status_code == 409
            assert "overlaps" in resp2.get_json()["message"].lower()

            # Slot 3: Touches boundary (10:00 - 11:00) -> Allowed
            payload3 = {
                "centre_id": base_data["c_active"].id,
                "crop_id": base_data["cr_active"].id,
                "slot_date": tomorrow,
                "start_time": "10:00",
                "end_time": "11:00",
                "capacity": 20,
            }
            resp3 = client.post("/api/slots", json=payload3, headers=auth_header())
            assert resp3.status_code == 201

    def test_daily_capacity_exceeded_rejected(self, client, admin_user, base_data):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
            # Centre daily capacity is 100

            # Slot 1: 60 capacity
            p1 = {
                "centre_id": base_data["c_active"].id,
                "crop_id": base_data["cr_active"].id,
                "slot_date": tomorrow,
                "start_time": "09:00",
                "end_time": "10:00",
                "capacity": 60,
            }
            assert client.post("/api/slots", json=p1, headers=auth_header()).status_code == 201

            # Slot 2: 50 capacity -> Total 110 > 100 limit -> Rejected
            p2 = {
                "centre_id": base_data["c_active"].id,
                "crop_id": base_data["cr_active"].id,
                "slot_date": tomorrow,
                "start_time": "10:00",
                "end_time": "11:00",
                "capacity": 50,
            }
            resp2 = client.post("/api/slots", json=p2, headers=auth_header())
            assert resp2.status_code == 409
            assert "would exceed daily limit" in resp2.get_json()["message"]

    def test_operating_hours_validation(self, client, admin_user, base_data):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
            # Centre operating hours: 09:00 - 17:00

            base_payload = {
                "centre_id": base_data["c_active"].id,
                "crop_id": base_data["cr_active"].id,
                "slot_date": tomorrow,
                "capacity": 10,
            }

            # 1. Slot starts before opening -> rejected (08:00 - 09:00)
            p1 = dict(base_payload, start_time="08:00", end_time="09:00")
            r1 = client.post("/api/slots", json=p1, headers=auth_header())
            assert r1.status_code == 400
            assert any("operating hours" in msg for msg in r1.get_json()["messages"])

            # 2. Slot ends after closing -> rejected (16:30 - 17:30)
            p2 = dict(base_payload, start_time="16:30", end_time="17:30")
            r2 = client.post("/api/slots", json=p2, headers=auth_header())
            assert r2.status_code == 400
            assert any("operating hours" in msg for msg in r2.get_json()["messages"])

            # 3. Slot exactly at opening time -> allowed (09:00 - 10:00)
            p3 = dict(base_payload, start_time="09:00", end_time="10:00")
            r3 = client.post("/api/slots", json=p3, headers=auth_header())
            assert r3.status_code == 201
            slot_id = r3.get_json()["slot"]["id"]

            # 4. Slot crosses both boundaries -> rejected (08:00 - 18:00)
            p4 = dict(base_payload, start_time="08:00", end_time="18:00")
            r4 = client.post("/api/slots", json=p4, headers=auth_header())
            assert r4.status_code == 400
            assert any("operating hours" in msg for msg in r4.get_json()["messages"])

            # 5. Update to end after closing -> rejected
            r5 = client.put(f"/api/slots/{slot_id}", json={"start_time": "16:00", "end_time": "18:00"}, headers=auth_header())
            assert r5.status_code == 400
            assert any("operating hours" in msg for msg in r5.get_json()["messages"])

            # 6. Update to valid hours -> allowed
            r6 = client.put(f"/api/slots/{slot_id}", json={"start_time": "16:00", "end_time": "17:00"}, headers=auth_header())
            assert r6.status_code == 200


class TestSlotSecurity:
    """Security tests for Slot APIs."""

    def test_unauthenticated_request_returns_401(self, client):
        resp = client.get("/api/slots")
        assert resp.status_code == 401

    def test_invalid_slot_id_returns_404(self, client, admin_user):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp = client.get("/api/slots/99999", headers=auth_header())
            assert resp.status_code == 404
