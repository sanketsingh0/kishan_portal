"""Security and workflow regression tests for Staff Centre Isolation & Farmer Procurement Processing.

Covers PART E requirements:
1. STAFF assigned Centre A cannot list Centre B slots.
2. STAFF cannot create slot for Centre B.
3. STAFF cannot edit Centre B slot.
4. STAFF cannot cancel Centre B slot.
5. ADMIN can manage both centres.
6. STAFF can process booking belonging to Centre A.
7. STAFF cannot process Centre B booking.
8. Start Processing changes procurement to IN_PROGRESS.
9. Complete changes procurement to COMPLETED.
10. Completed farmer is removed from active waiting queue / no longer affects farmers_ahead.
11. Queue positions recalculate correctly.
12. FARMER cannot call STAFF processing actions.
13. Existing notification/realtime behavior is preserved.
14. Unassigned STAFF cannot perform centre operations.
"""

import pytest
from datetime import date, time, timedelta
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.models import (
    User, Farmer, Staff, Centre, Crop, Slot, SlotStatus,
    Booking, BookingStatus, Procurement, ProcurementStatus, UserRole
)


@pytest.fixture
def test_setup(app):
    """Fixture creating Centre A, Centre B, STAFF A, Unassigned STAFF, ADMIN, FARMER, and Bookings."""
    with app.app_context():
        # Clean existing test data
        db.session.query(Procurement).delete()
        db.session.query(Booking).delete()
        db.session.query(Slot).delete()
        db.session.query(Farmer).delete()
        db.session.query(Staff).delete()
        db.session.query(Crop).delete()
        db.session.query(Centre).delete()
        db.session.query(User).delete()
        db.session.commit()

        # Users
        u_farmer = User(supabase_user_id="user-iso-farmer", role=UserRole.FARMER, is_active=True)
        u_farmer2 = User(supabase_user_id="user-iso-farmer2", role=UserRole.FARMER, is_active=True)
        u_staff_a = User(supabase_user_id="user-iso-staff-a", role=UserRole.STAFF, is_active=True)
        u_staff_unassigned = User(supabase_user_id="user-iso-staff-unassigned", role=UserRole.STAFF, is_active=True)
        u_admin = User(supabase_user_id="user-iso-admin", role=UserRole.ADMIN, is_active=True)
        db.session.add_all([u_farmer, u_farmer2, u_staff_a, u_staff_unassigned, u_admin])
        db.session.commit()

        # Centres
        c_a = Centre(name="Centre A - Ludhiana", location="Ludhiana", daily_capacity=100, average_processing_minutes=15, is_active=True)
        c_b = Centre(name="Centre B - Patiala", location="Patiala", daily_capacity=100, average_processing_minutes=15, is_active=True)
        cr = Crop(name="Wheat", is_active=True)
        db.session.add_all([c_a, c_b, cr])
        db.session.commit()

        # Staff Profiles & Farmers
        s_a = Staff(user_id=u_staff_a.id, name="Staff Centre A", centre_id=c_a.id)
        s_unassigned = Staff(user_id=u_staff_unassigned.id, name="Unassigned Staff", centre_id=None)
        f1 = Farmer(user_id=u_farmer.id, name="Test Farmer 1", phone="9876543210")
        f2 = Farmer(user_id=u_farmer2.id, name="Test Farmer 2", phone="9876543211")
        db.session.add_all([s_a, s_unassigned, f1, f2])
        db.session.commit()

        # Slots
        tomorrow = date.today() + timedelta(days=1)
        slot_a = Slot(
            centre_id=c_a.id,
            crop_id=cr.id,
            slot_date=tomorrow,
            start_time=time(9, 0),
            end_time=time(10, 0),
            capacity=10,
            status=SlotStatus.OPEN,
        )
        slot_b = Slot(
            centre_id=c_b.id,
            crop_id=cr.id,
            slot_date=tomorrow,
            start_time=time(9, 0),
            end_time=time(10, 0),
            capacity=10,
            status=SlotStatus.OPEN,
        )
        db.session.add_all([slot_a, slot_b])
        db.session.commit()

        # Bookings
        b_a1 = Booking(farmer_id=f1.id, slot_id=slot_a.id, status=BookingStatus.CONFIRMED, token_number="K-0001")
        b_a2 = Booking(farmer_id=f2.id, slot_id=slot_a.id, status=BookingStatus.CONFIRMED, token_number="K-0002")
        b_b1 = Booking(farmer_id=f1.id, slot_id=slot_b.id, status=BookingStatus.CONFIRMED, token_number="K-0003")
        db.session.add_all([b_a1, b_a2, b_b1])
        db.session.commit()

        yield {
            "centre_a_id": c_a.id,
            "centre_b_id": c_b.id,
            "slot_a_id": slot_a.id,
            "slot_b_id": slot_b.id,
            "booking_a1_id": b_a1.id,
            "booking_a2_id": b_a2.id,
            "booking_b1_id": b_b1.id,
            "staff_a_sub": u_staff_a.supabase_user_id,
            "staff_unassigned_sub": u_staff_unassigned.supabase_user_id,
            "admin_sub": u_admin.supabase_user_id,
            "farmer_sub": u_farmer.supabase_user_id,
        }


def make_call(client, method, url, sub_id, json_data=None):
    """Helper to mock Supabase token verification and execute request."""
    with patch("app.auth.decorators.verify_token") as mock_vt:
        mock_user = MagicMock()
        mock_user.id = sub_id
        mock_vt.return_value = mock_user

        headers = {"Authorization": "Bearer mock-token"}
        if method.upper() == "GET":
          return client.get(url, headers=headers)
        elif method.upper() == "POST":
          return client.post(url, json=json_data, headers=headers)
        elif method.upper() == "PUT":
          return client.put(url, json=json_data, headers=headers)
        elif method.upper() == "DELETE":
          return client.delete(url, headers=headers)


# 1. STAFF assigned Centre A cannot list Centre B slots
def test_staff_cannot_list_centre_b_slots(client, test_setup):
    res = make_call(client, "GET", f"/api/slots?centre_id={test_setup['centre_b_id']}", test_setup["staff_a_sub"])
    assert res.status_code == 403


# 2. STAFF cannot create slot for Centre B
def test_staff_cannot_create_centre_b_slot(client, test_setup):
    tomorrow = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    payload = {
        "centre_id": test_setup["centre_b_id"],
        "crop_id": 1,
        "slot_date": tomorrow,
        "start_time": "14:00",
        "end_time": "15:00",
        "capacity": 5,
    }
    res = make_call(client, "POST", "/api/slots", test_setup["staff_a_sub"], payload)
    assert res.status_code == 403


# 3. STAFF cannot edit Centre B slot
def test_staff_cannot_edit_centre_b_slot(client, test_setup):
    res = make_call(client, "PUT", f"/api/slots/{test_setup['slot_b_id']}", test_setup["staff_a_sub"], {"capacity": 20})
    assert res.status_code == 403


# 4. STAFF cannot cancel Centre B slot
def test_staff_cannot_cancel_centre_b_slot(client, test_setup):
    res = make_call(client, "DELETE", f"/api/slots/{test_setup['slot_b_id']}", test_setup["staff_a_sub"])
    assert res.status_code == 403


# 5. ADMIN can manage both centres
def test_admin_can_manage_both_centres(client, test_setup):
    res_list = make_call(client, "GET", f"/api/slots?centre_id={test_setup['centre_b_id']}", test_setup["admin_sub"])
    assert res_list.status_code == 200

    res_edit = make_call(client, "PUT", f"/api/slots/{test_setup['slot_b_id']}", test_setup["admin_sub"], {"capacity": 15})
    assert res_edit.status_code == 200


# 6. STAFF can process booking belonging to Centre A
def test_staff_can_process_centre_a_booking(client, test_setup):
    b_id = test_setup["booking_a1_id"]
    res = make_call(client, "POST", f"/api/procurement/{b_id}", test_setup["staff_a_sub"], {"procurement_status": "IN_PROGRESS"})
    assert res.status_code == 201
    assert res.get_json()["procurement"]["procurement_status"] == "IN_PROGRESS"


# 7. STAFF cannot process Centre B booking
def test_staff_cannot_process_centre_b_booking(client, test_setup):
    b_id = test_setup["booking_b1_id"]
    res = make_call(client, "POST", f"/api/procurement/{b_id}", test_setup["staff_a_sub"], {"procurement_status": "IN_PROGRESS"})
    assert res.status_code == 403


# 8. Start Processing changes procurement to IN_PROGRESS
def test_start_processing_in_progress(client, test_setup):
    b_id = test_setup["booking_a1_id"]
    res = make_call(client, "POST", f"/api/procurement/{b_id}", test_setup["staff_a_sub"], {"procurement_status": "IN_PROGRESS"})
    assert res.status_code == 201
    assert res.get_json()["procurement"]["procurement_status"] == "IN_PROGRESS"


# 9. Complete changes procurement to COMPLETED
def test_complete_changes_procurement_completed(client, test_setup):
    b_id = test_setup["booking_a1_id"]
    make_call(client, "POST", f"/api/procurement/{b_id}", test_setup["staff_a_sub"], {"procurement_status": "IN_PROGRESS"})
    res = make_call(client, "PUT", f"/api/procurement/{b_id}", test_setup["staff_a_sub"], {
        "procurement_status": "COMPLETED",
        "quantity": 40.0,
        "unit": "quintal",
    })
    assert res.status_code == 200
    assert res.get_json()["procurement"]["procurement_status"] == "COMPLETED"


# 10 & 11. Completed farmer is removed from active waiting queue and queue positions recalculate
def test_completed_farmer_removed_from_queue_and_recalculates(client, app, test_setup):
    tomorrow = date.today() + timedelta(days=1)
    b_a1_id = test_setup["booking_a1_id"]
    b_a2_id = test_setup["booking_a2_id"]

    # Before completion: b_a1 is #1, b_a2 is #2
    q1 = make_call(client, "GET", f"/api/queue/centre/{test_setup['centre_a_id']}?date={tomorrow.strftime('%Y-%m-%d')}", test_setup["staff_a_sub"])
    assert q1.status_code == 200
    queue_before = q1.get_json()["queue"]
    assert len(queue_before) == 2
    assert queue_before[0]["booking_id"] == b_a1_id
    assert queue_before[0]["queue_position"] == 1
    assert queue_before[1]["booking_id"] == b_a2_id
    assert queue_before[1]["queue_position"] == 2

    # Complete b_a1
    make_call(client, "POST", f"/api/procurement/{b_a1_id}", test_setup["staff_a_sub"], {
        "procurement_status": "COMPLETED",
        "quantity": 25.0,
    })

    # After completion: b_a1 is removed, b_a2 becomes #1
    q2 = make_call(client, "GET", f"/api/queue/centre/{test_setup['centre_a_id']}?date={tomorrow.strftime('%Y-%m-%d')}", test_setup["staff_a_sub"])
    assert q2.status_code == 200
    queue_after = q2.get_json()["queue"]
    assert len(queue_after) == 1
    assert queue_after[0]["booking_id"] == b_a2_id
    assert queue_after[0]["queue_position"] == 1


# 12. FARMER cannot call STAFF processing actions
def test_farmer_cannot_call_staff_processing_actions(client, test_setup):
    b_id = test_setup["booking_a1_id"]
    res = make_call(client, "POST", f"/api/procurement/{b_id}", test_setup["farmer_sub"], {"procurement_status": "IN_PROGRESS"})
    assert res.status_code == 403


# 13. Notification/realtime behavior is preserved
def test_notification_and_realtime_events_emitted(client, test_setup):
    b_id = test_setup["booking_a1_id"]
    with patch("app.services.procurement_service.emit_procurement_update") as mock_emit:
        res = make_call(client, "POST", f"/api/procurement/{b_id}", test_setup["staff_a_sub"], {"procurement_status": "IN_PROGRESS"})
        assert res.status_code == 201
        assert mock_emit.called


# 14. Unassigned STAFF cannot perform centre operations
def test_unassigned_staff_cannot_perform_centre_operations(client, test_setup):
    b_id = test_setup["booking_a1_id"]
    res_proc = make_call(client, "POST", f"/api/procurement/{b_id}", test_setup["staff_unassigned_sub"], {"procurement_status": "IN_PROGRESS"})
    assert res_proc.status_code == 403

    res_queue = make_call(client, "GET", f"/api/queue/centre/{test_setup['centre_a_id']}", test_setup["staff_unassigned_sub"])
    assert res_queue.status_code == 403
