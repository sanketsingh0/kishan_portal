"""Unit and Integration tests for Procurement Status tracking (Task 11)."""

import pytest
from datetime import date, time, timedelta
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.models import (
    User, Farmer, Staff, Centre, Crop, Slot, SlotStatus,
    Booking, BookingStatus, Procurement, ProcurementStatus, UserRole
)
from app.services.procurement_service import (
    create_procurement, update_procurement, ProcurementValidationError, ProcurementConflictError, ProcurementNotFoundError
)


@pytest.fixture
def test_setup(app):
    """Fixture creating test users, centre, crop, slot, and booking."""
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
        u_farmer1 = User(supabase_user_id="user-proc-farmer1", role=UserRole.FARMER, is_active=True)
        u_farmer2 = User(supabase_user_id="user-proc-farmer2", role=UserRole.FARMER, is_active=True)
        u_staff = User(supabase_user_id="user-proc-staff", role=UserRole.STAFF, is_active=True)
        u_admin = User(supabase_user_id="user-proc-admin", role=UserRole.ADMIN, is_active=True)
        db.session.add_all([u_farmer1, u_farmer2, u_staff, u_admin])
        db.session.commit()

        f1 = Farmer(user_id=u_farmer1.id, name="Proc Farmer 1", phone="9900000001", state="Punjab")
        f2 = Farmer(user_id=u_farmer2.id, name="Proc Farmer 2", phone="9900000002", state="Punjab")
        s = Staff(user_id=u_staff.id, name="Proc Staff")
        c = Centre(name="Procurement Hub", location="District 1", daily_capacity=100, is_active=True)
        cr = Crop(name="Wheat", is_active=True)
        db.session.add_all([f1, f2, s, c, cr])
        db.session.commit()

        slot = Slot(
            centre_id=c.id,
            crop_id=cr.id,
            slot_date=date.today() + timedelta(days=1),
            start_time=time(9, 0),
            end_time=time(10, 0),
            capacity=10,
            status=SlotStatus.OPEN,
        )
        db.session.add(slot)
        db.session.commit()

        b1 = Booking(farmer_id=f1.id, slot_id=slot.id, status=BookingStatus.CONFIRMED, token_number="K-0001")
        b2 = Booking(farmer_id=f2.id, slot_id=slot.id, status=BookingStatus.CONFIRMED, token_number="K-0002")
        db.session.add_all([b1, b2])
        db.session.commit()

        yield {
            "farmer1_user_id": u_farmer1.id,
            "farmer2_user_id": u_farmer2.id,
            "staff_user_id": u_staff.id,
            "admin_user_id": u_admin.id,
            "farmer1_sub_id": u_farmer1.supabase_user_id,
            "farmer2_sub_id": u_farmer2.supabase_user_id,
            "staff_sub_id": u_staff.supabase_user_id,
            "admin_sub_id": u_admin.supabase_user_id,
            "booking1_id": b1.id,
            "booking2_id": b2.id,
            "slot_id": slot.id,
        }


def make_auth_call(client, method, url, sub_id, json_data=None):
    """Helper to mock Supabase token verification and execute client HTTP call."""
    with patch("app.auth.decorators.verify_token") as mock_vt:
        mock_user = MagicMock()
        mock_user.id = sub_id
        mock_vt.return_value = mock_user

        headers = {"Authorization": "Bearer mock-valid-token"}
        if method.upper() == "GET":
            return client.get(url, headers=headers)
        elif method.upper() == "POST":
            return client.post(url, json=json_data, headers=headers)
        elif method.upper() == "PUT":
            return client.put(url, json=json_data, headers=headers)


# 1. Farmer can view own procurement status
def test_farmer_can_view_own_procurement(client, test_setup):
    b_id = test_setup["booking1_id"]
    res = make_auth_call(client, "GET", f"/api/procurement/my/{b_id}", test_setup["farmer1_sub_id"])
    assert res.status_code == 200
    data = res.get_json()
    assert "procurement" in data
    assert data["procurement"]["procurement_status"] == ProcurementStatus.PENDING


# 2. Farmer cannot view another farmer's procurement
def test_farmer_cannot_view_other_procurement(client, test_setup):
    b1_id = test_setup["booking1_id"]
    res = make_auth_call(client, "GET", f"/api/procurement/my/{b1_id}", test_setup["farmer2_sub_id"])
    assert res.status_code == 404


# 3. Staff can create procurement record
def test_staff_can_create_procurement(client, test_setup):
    b_id = test_setup["booking1_id"]
    payload = {
        "procurement_status": ProcurementStatus.IN_PROGRESS,
        "quantity": 50.5,
        "unit": "quintal",
        "procurement_date": "2026-09-10",
        "remarks": "Staff initiated procurement",
    }
    res = make_auth_call(client, "POST", f"/api/procurement/{b_id}", test_setup["staff_sub_id"], payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["procurement"]["procurement_status"] == ProcurementStatus.IN_PROGRESS
    assert data["procurement"]["quantity"] == 50.5


# 4. Admin can create procurement record
def test_admin_can_create_procurement(client, test_setup):
    b_id = test_setup["booking2_id"]
    payload = {
        "procurement_status": ProcurementStatus.COMPLETED,
        "quantity": 100.0,
        "unit": "quintal",
        "procurement_date": "2026-09-10",
        "remarks": "Admin completed procurement",
    }
    res = make_auth_call(client, "POST", f"/api/procurement/{b_id}", test_setup["admin_sub_id"], payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["procurement"]["procurement_status"] == ProcurementStatus.COMPLETED


# 5. Farmer cannot create procurement record
def test_farmer_cannot_create_procurement(client, test_setup):
    b_id = test_setup["booking1_id"]
    payload = {"procurement_status": ProcurementStatus.COMPLETED, "quantity": 10.0}
    res = make_auth_call(client, "POST", f"/api/procurement/{b_id}", test_setup["farmer1_sub_id"], payload)
    assert res.status_code == 403


# 6. Farmer cannot update procurement record
def test_farmer_cannot_update_procurement(client, test_setup):
    b_id = test_setup["booking1_id"]
    payload = {"procurement_status": ProcurementStatus.COMPLETED}
    res = make_auth_call(client, "PUT", f"/api/procurement/{b_id}", test_setup["farmer1_sub_id"], payload)
    assert res.status_code == 403


# 7. Staff can update procurement status
def test_staff_can_update_procurement(client, test_setup):
    b_id = test_setup["booking1_id"]
    # Create first
    make_auth_call(client, "POST", f"/api/procurement/{b_id}", test_setup["staff_sub_id"], {"procurement_status": "IN_PROGRESS"})
    # Update
    res = make_auth_call(client, "PUT", f"/api/procurement/{b_id}", test_setup["staff_sub_id"], {"procurement_status": "COMPLETED", "quantity": 75.0})
    assert res.status_code == 200
    data = res.get_json()
    assert data["procurement"]["procurement_status"] == "COMPLETED"
    assert data["procurement"]["quantity"] == 75.0


# 8. Admin can update procurement status
def test_admin_can_update_procurement(client, test_setup):
    b_id = test_setup["booking2_id"]
    # Create first
    make_auth_call(client, "POST", f"/api/procurement/{b_id}", test_setup["admin_sub_id"], {"procurement_status": "PENDING"})
    # Update
    res = make_auth_call(client, "PUT", f"/api/procurement/{b_id}", test_setup["admin_sub_id"], {"procurement_status": "REJECTED", "remarks": "Quality check failed"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["procurement"]["procurement_status"] == "REJECTED"


# 9. Duplicate procurement record rejected
def test_duplicate_procurement_rejected(client, test_setup):
    b_id = test_setup["booking1_id"]
    make_auth_call(client, "POST", f"/api/procurement/{b_id}", test_setup["staff_sub_id"], {"procurement_status": "IN_PROGRESS"})
    res2 = make_auth_call(client, "POST", f"/api/procurement/{b_id}", test_setup["staff_sub_id"], {"procurement_status": "COMPLETED"})
    assert res2.status_code == 409


# 10. Invalid procurement status rejected
def test_invalid_procurement_status_rejected(client, test_setup):
    b_id = test_setup["booking1_id"]
    res = make_auth_call(client, "POST", f"/api/procurement/{b_id}", test_setup["staff_sub_id"], {"procurement_status": "INVALID_STATUS"})
    assert res.status_code == 400


# 11. Quantity validation tests
def test_quantity_zero_rejected(client, test_setup):
    b_id = test_setup["booking1_id"]
    res = make_auth_call(client, "POST", f"/api/procurement/{b_id}", test_setup["staff_sub_id"], {"quantity": 0.0})
    assert res.status_code == 400
    assert "quantity must be a positive number (> 0)" in res.get_json()["messages"][0]


def test_quantity_negative_rejected(client, test_setup):
    b_id = test_setup["booking1_id"]
    res = make_auth_call(client, "POST", f"/api/procurement/{b_id}", test_setup["staff_sub_id"], {"quantity": -15.5})
    assert res.status_code == 400
    assert "quantity must be a positive number (> 0)" in res.get_json()["messages"][0]


def test_quantity_positive_accepted(client, test_setup):
    b_id = test_setup["booking1_id"]
    res = make_auth_call(client, "POST", f"/api/procurement/{b_id}", test_setup["staff_sub_id"], {"quantity": 25.0, "procurement_status": "IN_PROGRESS"})
    assert res.status_code == 201
    assert res.get_json()["procurement"]["quantity"] == 25.0


def test_invalid_quantity_non_numeric_rejected(client, test_setup):
    b_id = test_setup["booking1_id"]
    res = make_auth_call(client, "POST", f"/api/procurement/{b_id}", test_setup["staff_sub_id"], {"quantity": "invalid_number"})
    assert res.status_code == 400


# 12. Nonexistent booking rejected
def test_nonexistent_booking_procurement_rejected(client, test_setup):
    res = make_auth_call(client, "POST", "/api/procurement/99999", test_setup["staff_sub_id"], {"procurement_status": "COMPLETED"})
    assert res.status_code == 404
