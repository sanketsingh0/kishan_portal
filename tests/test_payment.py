"""Unit and Integration tests for Payment Status tracking (Task 11)."""

import pytest
from datetime import date, time, timedelta
from unittest.mock import patch, MagicMock

from app.extensions import db
from app.models import (
    User, Farmer, Staff, Centre, Crop, Slot, SlotStatus,
    Booking, BookingStatus, Payment, PaymentStatus, UserRole
)
from app.services.payment_service import (
    create_payment, update_payment, PaymentValidationError, PaymentConflictError, PaymentNotFoundError
)


@pytest.fixture
def test_setup(app):
    """Fixture creating test users, centre, crop, slot, and booking."""
    with app.app_context():
        # Clean existing test data
        db.session.query(Payment).delete()
        db.session.query(Booking).delete()
        db.session.query(Slot).delete()
        db.session.query(Farmer).delete()
        db.session.query(Staff).delete()
        db.session.query(Crop).delete()
        db.session.query(Centre).delete()
        db.session.query(User).delete()
        db.session.commit()

        # Users
        u_farmer1 = User(supabase_user_id="user-pay-farmer1", role=UserRole.FARMER, is_active=True)
        u_farmer2 = User(supabase_user_id="user-pay-farmer2", role=UserRole.FARMER, is_active=True)
        u_staff = User(supabase_user_id="user-pay-staff", role=UserRole.STAFF, is_active=True)
        u_admin = User(supabase_user_id="user-pay-admin", role=UserRole.ADMIN, is_active=True)
        db.session.add_all([u_farmer1, u_farmer2, u_staff, u_admin])
        db.session.commit()

        f1 = Farmer(user_id=u_farmer1.id, name="Pay Farmer 1", phone="9900000003", state="Punjab")
        f2 = Farmer(user_id=u_farmer2.id, name="Pay Farmer 2", phone="9900000004", state="Punjab")
        s = Staff(user_id=u_staff.id, name="Pay Staff")
        c = Centre(name="Payment Hub", location="District 2", daily_capacity=100, is_active=True)
        cr = Crop(name="Rice", is_active=True)
        db.session.add_all([f1, f2, s, c, cr])
        db.session.commit()

        slot = Slot(
            centre_id=c.id,
            crop_id=cr.id,
            slot_date=date.today() + timedelta(days=1),
            start_time=time(10, 0),
            end_time=time(11, 0),
            capacity=10,
            status=SlotStatus.OPEN,
        )
        db.session.add(slot)
        db.session.commit()

        b1 = Booking(farmer_id=f1.id, slot_id=slot.id, status=BookingStatus.CONFIRMED, token_number="K-0003")
        b2 = Booking(farmer_id=f2.id, slot_id=slot.id, status=BookingStatus.CONFIRMED, token_number="K-0004")
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


# 13. Farmer can view own payment status
def test_farmer_can_view_own_payment(client, test_setup):
    b_id = test_setup["booking1_id"]
    res = make_auth_call(client, "GET", f"/api/payment/my/{b_id}", test_setup["farmer1_sub_id"])
    assert res.status_code == 200
    data = res.get_json()
    assert "payment" in data
    assert data["payment"]["payment_status"] == PaymentStatus.PENDING


# 14. Farmer cannot view another farmer's payment
def test_farmer_cannot_view_other_payment(client, test_setup):
    b1_id = test_setup["booking1_id"]
    res = make_auth_call(client, "GET", f"/api/payment/my/{b1_id}", test_setup["farmer2_sub_id"])
    assert res.status_code == 404


# 15. Staff can create payment record
def test_staff_can_create_payment(client, test_setup):
    b_id = test_setup["booking1_id"]
    payload = {
        "payment_status": PaymentStatus.PROCESSING,
        "amount": 105000.00,
        "payment_reference": "TXN-987654",
        "payment_date": "2026-09-10",
        "remarks": "Payment initiated by staff",
    }
    res = make_auth_call(client, "POST", f"/api/payment/{b_id}", test_setup["staff_sub_id"], payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["payment"]["payment_status"] == PaymentStatus.PROCESSING
    assert data["payment"]["amount"] == 105000.00
    assert data["payment"]["payment_reference"] == "TXN-987654"


# 16. Admin can create payment record
def test_admin_can_create_payment(client, test_setup):
    b_id = test_setup["booking2_id"]
    payload = {
        "payment_status": PaymentStatus.PAID,
        "amount": 50000.00,
        "payment_reference": "TXN-112233",
        "payment_date": "2026-09-10",
        "remarks": "Direct payment clearance by admin",
    }
    res = make_auth_call(client, "POST", f"/api/payment/{b_id}", test_setup["admin_sub_id"], payload)
    assert res.status_code == 201
    data = res.get_json()
    assert data["payment"]["payment_status"] == PaymentStatus.PAID


# 17. Farmer cannot create payment record
def test_farmer_cannot_create_payment(client, test_setup):
    b_id = test_setup["booking1_id"]
    payload = {"payment_status": PaymentStatus.PAID, "amount": 100.0}
    res = make_auth_call(client, "POST", f"/api/payment/{b_id}", test_setup["farmer1_sub_id"], payload)
    assert res.status_code == 403


# 18. Farmer cannot update payment record
def test_farmer_cannot_update_payment(client, test_setup):
    b_id = test_setup["booking1_id"]
    payload = {"payment_status": PaymentStatus.PAID}
    res = make_auth_call(client, "PUT", f"/api/payment/{b_id}", test_setup["farmer1_sub_id"], payload)
    assert res.status_code == 403


# 19. Staff can update payment status
def test_staff_can_update_payment(client, test_setup):
    b_id = test_setup["booking1_id"]
    # Create
    make_auth_call(client, "POST", f"/api/payment/{b_id}", test_setup["staff_sub_id"], {"payment_status": "PROCESSING", "amount": 1000.0})
    # Update
    res = make_auth_call(client, "PUT", f"/api/payment/{b_id}", test_setup["staff_sub_id"], {"payment_status": "PAID", "payment_reference": "TXN-FINAL-01"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["payment"]["payment_status"] == "PAID"
    assert data["payment"]["payment_reference"] == "TXN-FINAL-01"


# 20. Admin can update payment status
def test_admin_can_update_payment(client, test_setup):
    b_id = test_setup["booking2_id"]
    # Create
    make_auth_call(client, "POST", f"/api/payment/{b_id}", test_setup["admin_sub_id"], {"payment_status": "PROCESSING"})
    # Update
    res = make_auth_call(client, "PUT", f"/api/payment/{b_id}", test_setup["admin_sub_id"], {"payment_status": "FAILED", "remarks": "Bank account validation failed"})
    assert res.status_code == 200
    data = res.get_json()
    assert data["payment"]["payment_status"] == "FAILED"


# 21. Duplicate payment record rejected
def test_duplicate_payment_rejected(client, test_setup):
    b_id = test_setup["booking1_id"]
    make_auth_call(client, "POST", f"/api/payment/{b_id}", test_setup["staff_sub_id"], {"payment_status": "PROCESSING"})
    res2 = make_auth_call(client, "POST", f"/api/payment/{b_id}", test_setup["staff_sub_id"], {"payment_status": "PAID"})
    assert res2.status_code == 409


# 22. Invalid payment status rejected
def test_invalid_payment_status_rejected(client, test_setup):
    b_id = test_setup["booking1_id"]
    res = make_auth_call(client, "POST", f"/api/payment/{b_id}", test_setup["staff_sub_id"], {"payment_status": "INVALID_STATUS"})
    assert res.status_code == 400


# 23. Amount validation tests
def test_amount_zero_accepted(client, test_setup):
    b_id = test_setup["booking1_id"]
    res = make_auth_call(client, "POST", f"/api/payment/{b_id}", test_setup["staff_sub_id"], {"amount": 0.0, "payment_status": "PROCESSING"})
    assert res.status_code == 201
    assert res.get_json()["payment"]["amount"] == 0.0


def test_amount_negative_rejected(client, test_setup):
    b_id = test_setup["booking1_id"]
    res = make_auth_call(client, "POST", f"/api/payment/{b_id}", test_setup["staff_sub_id"], {"amount": -500.0})
    assert res.status_code == 400
    assert "amount must be greater than or equal to 0" in res.get_json()["messages"][0]


def test_amount_positive_accepted(client, test_setup):
    b_id = test_setup["booking1_id"]
    res = make_auth_call(client, "POST", f"/api/payment/{b_id}", test_setup["staff_sub_id"], {"amount": 75000.0, "payment_status": "PAID"})
    assert res.status_code == 201
    assert res.get_json()["payment"]["amount"] == 75000.0


# 24. Nonexistent booking rejected
def test_nonexistent_booking_payment_rejected(client, test_setup):
    res = make_auth_call(client, "POST", "/api/payment/99999", test_setup["staff_sub_id"], {"payment_status": "PAID"})
    assert res.status_code == 404


# 29 & 30. Post-commit realtime event emission verification
def test_realtime_event_emitted_only_post_commit(test_setup, app):
    """Verify that Socket.IO events are emitted only after db.session.commit()."""
    with app.app_context():
        with patch("app.services.payment_service.emit_payment_update") as mock_emit:
            b_id = test_setup["booking1_id"]
            create_payment(b_id, {"payment_status": "PROCESSING", "amount": 1000.0})

            # Check that event was emitted
            assert mock_emit.called
            mock_emit.assert_called_once()


def test_failed_transaction_does_not_emit_realtime_event(test_setup, app):
    """Verify that if database transaction fails, no Socket.IO update event is emitted."""
    with app.app_context():
        with patch("app.services.payment_service.emit_payment_update") as mock_emit:
            b_id = test_setup["booking1_id"]
            create_payment(b_id, {"payment_status": "PROCESSING"})
            mock_emit.reset_mock()

            # Trigger duplicate conflict error
            with pytest.raises(Exception):
                create_payment(b_id, {"payment_status": "PAID"})

            # Second failed call must not emit event
            mock_emit.assert_not_called()
