"""
Unit and Integration test suite for Task 14 — Admin Analytics.

Tests ADMIN-only authorization, overview KPIs, booking statistics, procurement
aggregation, payment totals, queue/delay metrics, and date filter validations.
"""

import pytest
from datetime import date, time, datetime, timezone
from unittest.mock import patch, MagicMock
from app.extensions import db
from app.models import (
    User,
    UserRole,
    Farmer,
    Staff,
    Centre,
    Crop,
    Slot,
    SlotStatus,
    Booking,
    BookingStatus,
    Procurement,
    ProcurementStatus,
    Payment,
    PaymentStatus,
    Delay,
    DelayStatus,
)


@pytest.fixture
def analytics_users(app):
    """Create test users: Admin, Farmer, Staff."""
    with app.app_context():
        admin = User(id=201, supabase_user_id="sub-admin-201", role=UserRole.ADMIN, is_active=True)
        farmer = User(id=202, supabase_user_id="sub-farmer-202", role=UserRole.FARMER, is_active=True)
        staff = User(id=203, supabase_user_id="sub-staff-203", role=UserRole.STAFF, is_active=True)

        db.session.add_all([admin, farmer, staff])
        db.session.commit()

        f_profile = Farmer(id=10, user_id=202, name="Analytics Farmer", state="Punjab", city="Ludhiana")
        s_profile = Staff(id=10, user_id=203, name="Analytics Staff", centre_id=1)
        db.session.add_all([f_profile, s_profile])
        db.session.commit()

        yield admin, farmer, staff


@pytest.fixture
def analytics_domain_data(app, analytics_users):
    """Setup domain entities for analytics aggregation testing."""
    with app.app_context():
        c1 = Centre(id=10, name="Central Procurement Centre", location="Ludhiana", daily_capacity=100, is_active=True)
        c2 = Centre(id=11, name="East Mandi", location="Amritsar", daily_capacity=80, is_active=True)
        crop1 = Crop(id=10, name="Wheat", category="Cereal", is_active=True)
        crop2 = Crop(id=11, name="Paddy", category="Cereal", is_active=True)

        db.session.add_all([c1, c2, crop1, crop2])
        db.session.commit()

        today = date.today()
        slot1 = Slot(
            id=10,
            centre_id=10,
            crop_id=10,
            slot_date=today,
            start_time=time(9, 0),
            end_time=time(12, 0),
            capacity=20,
            status=SlotStatus.OPEN,
        )
        slot2 = Slot(
            id=11,
            centre_id=11,
            crop_id=11,
            slot_date=today,
            start_time=time(10, 0),
            end_time=time(13, 0),
            capacity=20,
            status=SlotStatus.OPEN,
        )
        db.session.add_all([slot1, slot2])
        db.session.commit()

        b1 = Booking(
            id=10,
            farmer_id=10,
            slot_id=10,
            booking_date=datetime.now(timezone.utc),
            status=BookingStatus.CONFIRMED,
            token_number="TK-0010",
        )
        b2 = Booking(
            id=11,
            farmer_id=10,
            slot_id=11,
            booking_date=datetime.now(timezone.utc),
            status=BookingStatus.COMPLETED,
            token_number="TK-0011",
        )
        db.session.add_all([b1, b2])
        db.session.commit()

        proc1 = Procurement(
            id=10,
            booking_id=11,
            procurement_status=ProcurementStatus.COMPLETED,
            quantity=50.0,
            unit="quintal",
        )
        pay1 = Payment(
            id=10,
            booking_id=11,
            payment_status=PaymentStatus.PAID,
            amount=112500.0,
            payment_reference="PAY-1001",
        )
        delay1 = Delay(
            id=10,
            centre_id=10,
            delay_date=today,
            delay_minutes=30,
            status=DelayStatus.ACTIVE,
            created_by=201,
        )
        db.session.add_all([proc1, pay1, delay1])
        db.session.commit()


def make_auth_call(client, method, url, sub_id, json_data=None):
    """Helper to simulate authenticated API calls."""
    with patch("app.auth.decorators.verify_token") as mock_vt:
        mock_user = MagicMock()
        mock_user.id = sub_id
        mock_vt.return_value = mock_user

        headers = {"Authorization": "Bearer mock-token"}
        if method.upper() == "GET":
            return client.get(url, headers=headers)
        elif method.upper() == "POST":
            return client.post(url, json=json_data, headers=headers)


def test_admin_analytics_access_control(client, analytics_users):
    """Verify ADMIN access is allowed while FARMER and STAFF receive 403 Forbidden."""
    # 1. Unauthenticated -> 401
    res = client.get("/api/admin/analytics/overview")
    assert res.status_code == 401

    # 2. Farmer -> 403
    res_farmer = make_auth_call(client, "GET", "/api/admin/analytics/overview", "sub-farmer-202")
    assert res_farmer.status_code == 403

    # 3. Staff -> 403
    res_staff = make_auth_call(client, "GET", "/api/admin/analytics/overview", "sub-staff-203")
    assert res_staff.status_code == 403

    # 4. Admin -> 200
    res_admin = make_auth_call(client, "GET", "/api/admin/analytics/overview", "sub-admin-201")
    assert res_admin.status_code == 200


def test_analytics_overview_values(client, analytics_users, analytics_domain_data):
    """Verify GET /api/admin/analytics/overview returns real database metrics."""
    res = make_auth_call(client, "GET", "/api/admin/analytics/overview", "sub-admin-201")
    assert res.status_code == 200
    data = res.get_json()

    assert data["total_farmers"] >= 1
    assert data["total_centres"] >= 2
    assert data["todays_bookings"] >= 2
    assert data["todays_completed_procurements"] >= 1
    assert data["todays_delay_minutes"] >= 30


def test_booking_analytics_and_filtering(client, analytics_users, analytics_domain_data):
    """Verify booking analytics API with status breakdowns and filtering."""
    res = make_auth_call(client, "GET", "/api/admin/analytics/bookings", "sub-admin-201")
    assert res.status_code == 200
    data = res.get_json()

    assert "by_status" in data
    assert "daily_trends" in data
    assert data["total_bookings"] >= 2
    assert data["by_status"]["CONFIRMED"] >= 1
    assert data["by_status"]["COMPLETED"] >= 1

    # Test filtering by centre_id
    res_filtered = make_auth_call(client, "GET", "/api/admin/analytics/bookings?centre_id=10", "sub-admin-201")
    assert res_filtered.status_code == 200


def test_procurement_and_payment_analytics(client, analytics_users, analytics_domain_data):
    """Verify procurement and payment aggregation endpoints."""
    # Procurement analytics
    res_p = make_auth_call(client, "GET", "/api/admin/analytics/procurement", "sub-admin-201")
    assert res_p.status_code == 200
    p_data = res_p.get_json()
    assert p_data["total_quantity"] >= 50.0
    assert p_data["by_status"]["COMPLETED"] >= 1

    # Payment analytics
    res_pay = make_auth_call(client, "GET", "/api/admin/analytics/payments", "sub-admin-201")
    assert res_pay.status_code == 200
    pay_data = res_pay.get_json()
    assert pay_data["total_paid_amount"] >= 112500.0
    assert pay_data["by_status"]["PAID"] >= 1


def test_invalid_date_filter_rejection(client, analytics_users):
    """Verify 400 error is returned for invalid date formats or start_date > end_date."""
    # Invalid format
    res1 = make_auth_call(client, "GET", "/api/admin/analytics/bookings?start_date=invalid-date", "sub-admin-201")
    assert res1.status_code == 400
    assert "Invalid start_date" in res1.get_json()["error"]

    # start_date > end_date
    res2 = make_auth_call(client, "GET", "/api/admin/analytics/bookings?start_date=2026-09-20&end_date=2026-09-01", "sub-admin-201")
    assert res2.status_code == 400
    assert "start_date cannot be after end_date" in res2.get_json()["error"]
