"""Test suite for Task 12 — Delay Management & Dynamic Queue Estimation.

Tests cover authorization, input validation, CRUD operations, dynamic queue estimation,
date/centre/slot isolation, ownership security, and post-commit Socket.IO realtime updates.
"""

import pytest
from datetime import date, time, timedelta
from unittest.mock import patch, MagicMock
from app.extensions import db
from app.models import User, UserRole, Farmer, Staff, Centre, Crop, Slot, SlotStatus, Booking, BookingStatus, Delay, DelayStatus


@pytest.fixture
def test_setup(app):
    """Fixture providing populated test users, centre, crop, slot, bookings, and delay test data."""
    with app.app_context():
        # Clear existing
        Delay.query.delete()
        Booking.query.delete()
        Slot.query.delete()
        Crop.query.delete()
        Centre.query.delete()
        Farmer.query.delete()
        Staff.query.delete()
        User.query.delete()
        db.session.commit()

        # Users
        u_farmer1 = User(supabase_user_id="sub_farmer1", role=UserRole.FARMER, is_active=True)
        u_farmer2 = User(supabase_user_id="sub_farmer2", role=UserRole.FARMER, is_active=True)
        u_staff = User(supabase_user_id="sub_staff", role=UserRole.STAFF, is_active=True)
        u_admin = User(supabase_user_id="sub_admin", role=UserRole.ADMIN, is_active=True)
        db.session.add_all([u_farmer1, u_farmer2, u_staff, u_admin])
        db.session.commit()

        f1 = Farmer(user_id=u_farmer1.id, name="Farmer One", state="Punjab", pincode="141001")
        f2 = Farmer(user_id=u_farmer2.id, name="Farmer Two", state="Punjab", pincode="141001")
        st = Staff(user_id=u_staff.id, name="Staff One")
        db.session.add_all([f1, f2, st])
        db.session.commit()

        # Centres
        c1 = Centre(name="Ludhiana Main Centre", location="Ludhiana", opening_time=time(9, 0), closing_time=time(17, 0), daily_capacity=100, average_processing_minutes=15, is_active=True)
        c2 = Centre(name="Jalandhar Centre", location="Jalandhar", opening_time=time(9, 0), closing_time=time(17, 0), daily_capacity=100, average_processing_minutes=15, is_active=True)
        db.session.add_all([c1, c2])
        db.session.commit()

        # Crop
        crop = Crop(name="Wheat Premium", category="Cereals", is_active=True)
        db.session.add(crop)
        db.session.commit()

        target_date = date.today() + timedelta(days=2)
        other_date = date.today() + timedelta(days=5)

        # Slots
        s1 = Slot(centre_id=c1.id, crop_id=crop.id, slot_date=target_date, start_time=time(9, 0), end_time=time(10, 0), capacity=10, status=SlotStatus.OPEN)
        s2 = Slot(centre_id=c1.id, crop_id=crop.id, slot_date=target_date, start_time=time(10, 0), end_time=time(11, 0), capacity=10, status=SlotStatus.OPEN)
        s_c2 = Slot(centre_id=c2.id, crop_id=crop.id, slot_date=target_date, start_time=time(9, 0), end_time=time(10, 0), capacity=10, status=SlotStatus.OPEN)
        db.session.add_all([s1, s2, s_c2])
        db.session.commit()

        # Bookings
        b1 = Booking(farmer_id=f1.id, slot_id=s1.id, status=BookingStatus.CONFIRMED, token_number="K-0001")
        b2 = Booking(farmer_id=f2.id, slot_id=s1.id, status=BookingStatus.CONFIRMED, token_number="K-0002")
        b_c2 = Booking(farmer_id=f1.id, slot_id=s_c2.id, status=BookingStatus.CONFIRMED, token_number="K-0001")
        db.session.add_all([b1, b2, b_c2])
        db.session.commit()

        return {
            "farmer1_sub_id": u_farmer1.supabase_user_id,
            "farmer2_sub_id": u_farmer2.supabase_user_id,
            "staff_sub_id": u_staff.supabase_user_id,
            "admin_sub_id": u_admin.supabase_user_id,
            "farmer1_id": f1.id,
            "farmer2_id": f2.id,
            "staff_user_id": u_staff.id,
            "centre1_id": c1.id,
            "centre2_id": c2.id,
            "slot1_id": s1.id,
            "slot2_id": s2.id,
            "target_date": target_date.isoformat(),
            "other_date": other_date.isoformat(),
            "booking1_id": b1.id,
            "booking2_id": b2.id,
            "booking_c2_id": b_c2.id,
        }


def make_auth_call(client, method: str, url: str, sub_id: str, json_data=None):
    """Helper to execute API calls with mocked Supabase authentication context."""
    mock_user = MagicMock()
    mock_user.id = sub_id
    with patch("app.auth.decorators.verify_token", return_value=mock_user):
        headers = {"Authorization": f"Bearer fake_token_{sub_id}"}
        if method.upper() == "POST":
            return client.post(url, json=json_data, headers=headers)
        elif method.upper() == "PUT":
            return client.put(url, json=json_data, headers=headers)
        elif method.upper() == "DELETE":
            return client.delete(url, headers=headers)
        else:
            return client.get(url, headers=headers)


# --- 1. AUTHORIZATION TESTS ---

def test_farmer_cannot_create_delay(client, test_setup):
    """1. Farmer cannot create delay."""
    payload = {"centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 30}
    res = make_auth_call(client, "POST", "/api/delays", test_setup["farmer1_sub_id"], payload)
    assert res.status_code == 403


def test_farmer_cannot_update_delay(client, test_setup):
    """2. Farmer cannot update delay."""
    # Create delay as staff first
    payload = {"centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 30}
    res_create = make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], payload)
    d_id = res_create.get_json()["delay"]["id"]

    res = make_auth_call(client, "PUT", f"/api/delays/{d_id}", test_setup["farmer1_sub_id"], {"delay_minutes": 45})
    assert res.status_code == 403


def test_farmer_cannot_delete_delay(client, test_setup):
    """3. Farmer cannot delete/cancel delay."""
    payload = {"centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 30}
    res_create = make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], payload)
    d_id = res_create.get_json()["delay"]["id"]

    res = make_auth_call(client, "DELETE", f"/api/delays/{d_id}", test_setup["farmer1_sub_id"])
    assert res.status_code == 403


def test_staff_can_create_and_update_delay(client, test_setup):
    """4 & 5. Staff can create and update delay."""
    payload = {"centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 30, "reason": "Weighbridge failure"}
    res_create = make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], payload)
    assert res_create.status_code == 201
    d_data = res_create.get_json()["delay"]
    assert d_data["delay_minutes"] == 30
    assert d_data["created_by"] == test_setup["staff_user_id"]

    d_id = d_data["id"]
    res_update = make_auth_call(client, "PUT", f"/api/delays/{d_id}", test_setup["staff_sub_id"], {"delay_minutes": 45})
    assert res_update.status_code == 200
    assert res_update.get_json()["delay"]["delay_minutes"] == 45


def test_admin_can_create_and_update_delay(client, test_setup):
    """6 & 7. Admin can create and update delay."""
    payload = {"centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 20}
    res_create = make_auth_call(client, "POST", "/api/delays", test_setup["admin_sub_id"], payload)
    assert res_create.status_code == 201

    d_id = res_create.get_json()["delay"]["id"]
    res_update = make_auth_call(client, "PUT", f"/api/delays/{d_id}", test_setup["admin_sub_id"], {"status": "RESOLVED"})
    assert res_update.status_code == 200
    assert res_update.get_json()["delay"]["status"] == "RESOLVED"


# --- 2. VALIDATION TESTS ---

def test_zero_delay_rejected(client, test_setup):
    """8. Zero delay rejected."""
    payload = {"centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 0}
    res = make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], payload)
    assert res.status_code == 400


def test_negative_delay_rejected(client, test_setup):
    """9. Negative delay rejected."""
    payload = {"centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": -15}
    res = make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], payload)
    assert res.status_code == 400


def test_large_delay_rejected(client, test_setup):
    """10. Excessively large delay (>1440) rejected."""
    payload = {"centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 1500}
    res = make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], payload)
    assert res.status_code == 400


def test_invalid_date_rejected(client, test_setup):
    """11. Invalid date rejected."""
    payload = {"centre_id": test_setup["centre1_id"], "delay_date": "invalid-date", "delay_minutes": 30}
    res = make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], payload)
    assert res.status_code == 400


def test_invalid_centre_rejected(client, test_setup):
    """12. Invalid centre rejected."""
    payload = {"centre_id": 99999, "delay_date": test_setup["target_date"], "delay_minutes": 30}
    res = make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], payload)
    assert res.status_code == 400


def test_invalid_slot_rejected(client, test_setup):
    """13. Invalid slot rejected."""
    payload = {"centre_id": test_setup["centre1_id"], "slot_id": 99999, "delay_date": test_setup["target_date"], "delay_minutes": 30}
    res = make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], payload)
    assert res.status_code == 400


def test_slot_centre_mismatch_rejected(client, test_setup):
    """14. Slot belonging to another centre rejected."""
    # Slot 1 belongs to centre 1; try creating delay for centre 2 with slot 1
    payload = {"centre_id": test_setup["centre2_id"], "slot_id": test_setup["slot1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 30}
    res = make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], payload)
    assert res.status_code == 400


def test_invalid_status_rejected(client, test_setup):
    """15. Invalid status rejected."""
    payload = {"centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 30, "status": "UNKNOWN_STATUS"}
    res = make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], payload)
    assert res.status_code == 400


# --- 3. CRUD TESTS ---

def test_delay_crud_lifecycle(client, test_setup):
    """16, 17, 18, 19, 20. Staff delay CRUD lifecycle."""
    # Create ACTIVE delay
    payload = {"centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 30, "reason": "Power outage"}
    res_create = make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], payload)
    assert res_create.status_code == 201
    d_id = res_create.get_json()["delay"]["id"]

    # GET list
    res_list = make_auth_call(client, "GET", f"/api/delays?centre_id={test_setup['centre1_id']}", test_setup["staff_sub_id"])
    assert res_list.status_code == 200
    assert len(res_list.get_json()["delays"]) == 1

    # Resolve delay
    res_resolve = make_auth_call(client, "PUT", f"/api/delays/{d_id}", test_setup["staff_sub_id"], {"status": "RESOLVED"})
    assert res_resolve.status_code == 200
    assert res_resolve.get_json()["delay"]["status"] == "RESOLVED"

    # Soft-cancel delay
    res_cancel = make_auth_call(client, "DELETE", f"/api/delays/{d_id}", test_setup["staff_sub_id"])
    assert res_cancel.status_code == 200
    assert res_cancel.get_json()["delay"]["status"] == "CANCELLED"


# --- 4. QUEUE CALCULATION TESTS ---

def test_queue_estimation_without_delay(client, test_setup):
    """21. No delay -> base wait equals adjusted wait."""
    b2_id = test_setup["booking2_id"]
    res = make_auth_call(client, "GET", f"/api/queue/my/{b2_id}", test_setup["farmer2_sub_id"])
    assert res.status_code == 200
    data = res.get_json()
    assert data["farmers_ahead"] == 1
    assert data["base_estimated_wait"] == 15
    assert data["active_delay_minutes"] == 0
    assert data["adjusted_estimated_wait"] == 15
    assert data["estimated_wait_minutes"] == 15


def test_queue_estimation_with_one_active_delay(client, test_setup):
    """22. One active delay increases adjusted wait correctly."""
    make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], {
        "centre_id": test_setup["centre1_id"],
        "delay_date": test_setup["target_date"],
        "delay_minutes": 30,
        "reason": "Rain delay"
    })

    b2_id = test_setup["booking2_id"]
    res = make_auth_call(client, "GET", f"/api/queue/my/{b2_id}", test_setup["farmer2_sub_id"])
    assert res.status_code == 200
    data = res.get_json()
    assert data["farmers_ahead"] == 1
    assert data["base_estimated_wait"] == 15
    assert data["active_delay_minutes"] == 30
    assert data["adjusted_estimated_wait"] == 45
    assert data["estimated_wait_minutes"] == 45


def test_queue_estimation_with_multiple_active_delays_summed(client, test_setup):
    """23. Multiple active delays are summed."""
    make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], {
        "centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 20
    })
    make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], {
        "centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 15
    })

    b2_id = test_setup["booking2_id"]
    res = make_auth_call(client, "GET", f"/api/queue/my/{b2_id}", test_setup["farmer2_sub_id"])
    assert res.status_code == 200
    data = res.get_json()
    assert data["active_delay_minutes"] == 35
    assert data["adjusted_estimated_wait"] == 50


def test_resolved_and_cancelled_delays_contribute_zero(client, test_setup):
    """24 & 25. Resolved and cancelled delays contribute zero."""
    res1 = make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], {
        "centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 30, "status": "RESOLVED"
    })
    res2 = make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], {
        "centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 25, "status": "CANCELLED"
    })

    b2_id = test_setup["booking2_id"]
    res = make_auth_call(client, "GET", f"/api/queue/my/{b2_id}", test_setup["farmer2_sub_id"])
    assert res.status_code == 200
    data = res.get_json()
    assert data["active_delay_minutes"] == 0
    assert data["adjusted_estimated_wait"] == 15


def test_date_and_centre_isolation(client, test_setup):
    """26 & 27. Delay from another centre or date does not affect queue."""
    # Delay for centre 2
    make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], {
        "centre_id": test_setup["centre2_id"], "delay_date": test_setup["target_date"], "delay_minutes": 40
    })
    # Delay for centre 1 on another date
    make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], {
        "centre_id": test_setup["centre1_id"], "delay_date": test_setup["other_date"], "delay_minutes": 50
    })

    # Check booking on centre 1 / target_date -> active delay must be 0
    b1_id = test_setup["booking1_id"]
    res = make_auth_call(client, "GET", f"/api/queue/my/{b1_id}", test_setup["farmer1_sub_id"])
    assert res.status_code == 200
    assert res.get_json()["active_delay_minutes"] == 0


def test_slot_specific_delay_isolation(client, test_setup):
    """28. Slot-specific delay affects only matching slot."""
    # Delay specifically for slot 2
    make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], {
        "centre_id": test_setup["centre1_id"], "slot_id": test_setup["slot2_id"], "delay_date": test_setup["target_date"], "delay_minutes": 25
    })

    # Booking 1 is in slot 1 -> should NOT be affected by slot 2 delay
    b1_id = test_setup["booking1_id"]
    res = make_auth_call(client, "GET", f"/api/queue/my/{b1_id}", test_setup["farmer1_sub_id"])
    assert res.status_code == 200
    assert res.get_json()["active_delay_minutes"] == 0


# --- 5. OWNERSHIP TESTS ---

def test_farmer_ownership_security(client, test_setup):
    """29 & 30. Farmer can read delay info for own booking, denied for another's booking."""
    # Create active delay
    make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], {
        "centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 30
    })

    b1_id = test_setup["booking1_id"]
    # Farmer 1 owns Booking 1 -> 200 OK
    res1 = make_auth_call(client, "GET", f"/api/delays/my/{b1_id}", test_setup["farmer1_sub_id"])
    assert res1.status_code == 200
    assert res1.get_json()["active_delay_minutes"] == 30

    # Farmer 2 does NOT own Booking 1 -> 404 Not Found
    res2 = make_auth_call(client, "GET", f"/api/delays/my/{b1_id}", test_setup["farmer2_sub_id"])
    assert res2.status_code == 404


# --- 6. REALTIME EVENT TESTS ---

def test_realtime_delay_events_post_commit(client, test_setup):
    """31, 32, 34, 35. Delay operations trigger delay_updated post-commit."""
    with patch("app.queue.events.socketio.emit") as mock_emit:
        payload = {"centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 30}
        res = make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], payload)
        assert res.status_code == 201

        delay_calls = [c for c in mock_emit.call_args_list if c[0][0] == "delay_updated"]
        assert len(delay_calls) == 1
        args, kwargs = delay_calls[0]
        assert args[0] == "delay_updated"
        event_payload = args[1]
        assert event_payload["centre_id"] == test_setup["centre1_id"]
        assert event_payload["slot_date"] == test_setup["target_date"]
        assert event_payload["reason"] == "DELAY_CREATED"
        # Confirm no sensitive info in payload
        assert set(event_payload.keys()) == {"centre_id", "slot_date", "reason"}
        assert kwargs["namespace"] == "/queue"
        assert kwargs["to"] == f"centre_queue_{test_setup['centre1_id']}_{test_setup['target_date']}"


def test_failed_commit_prevents_realtime_emission(client, test_setup):
    """33. Failed commit does not emit success event."""
    with patch("app.extensions.db.session.commit", side_effect=Exception("Database lock failure")):
        with patch("app.queue.events.socketio.emit") as mock_emit:
            payload = {"centre_id": test_setup["centre1_id"], "delay_date": test_setup["target_date"], "delay_minutes": 30}
            res = make_auth_call(client, "POST", "/api/delays", test_setup["staff_sub_id"], payload)
            assert res.status_code == 400
            mock_emit.assert_not_called()
