"""
Unit and Integration test suite for Task 15 — PWA Foundation and End-to-End Workflow.

Tests manifest.json accessibility/validity, service-worker.js rules, offline page,
and the complete end-to-end KisanProcure business lifecycle across Tasks 1–14.
"""

import json
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
    Notification,
    AuditLog,
)
from app.services.booking_service import create_booking
from app.services.queue_service import get_booking_queue_status
from app.services.delay_service import create_delay
from app.services.procurement_service import create_procurement
from app.services.payment_service import create_payment
from app.services.analytics_service import get_overview_analytics
from app.services.audit_service import get_audit_logs


def test_manifest_accessibility_and_valid_json(client):
    """Verify GET /static/manifest.json returns valid PWA configuration."""
    res = client.get("/static/manifest.json")
    assert res.status_code == 200
    assert res.content_type == "application/json" or "json" in res.content_type

    data = json.loads(res.data.decode("utf-8"))
    assert "KisanProcure" in data["name"]
    assert data["display"] == "standalone"
    assert data["start_url"] == "/farmer/dashboard"
    assert len(data["icons"]) >= 2


def test_service_worker_accessible_and_safe(client):
    """Verify service-worker.js is served and contains API cache bypass rules."""
    res = client.get("/static/service-worker.js")
    assert res.status_code == 200
    content = res.data.decode("utf-8")

    assert "CACHE_NAME" in content
    assert "/api/" in content
    assert "/offline" in content


def test_offline_page_accessible(client):
    """Verify GET /offline returns the user-facing offline fallback page."""
    res = client.get("/offline")
    assert res.status_code == 200
    assert "Offline" in res.data.decode("utf-8")


def test_full_end_to_end_kisanprocure_workflow(app):
    """Verify complete end-to-end business lifecycle from registration to audit logs."""
    with app.app_context():
        # 1. User & Profile Setup
        f_user = User(id=501, supabase_user_id="sub-e2e-501", role=UserRole.FARMER, is_active=True)
        a_user = User(id=502, supabase_user_id="sub-e2e-502", role=UserRole.ADMIN, is_active=True)
        db.session.add_all([f_user, a_user])
        db.session.commit()

        farmer = Farmer(id=50, user_id=501, name="E2E Farmer", state="Punjab", city="Patiala")
        db.session.add(farmer)
        db.session.commit()

        # 2. Centre & Crop Management
        centre = Centre(id=50, name="Patiala Central Mandi", location="Patiala", daily_capacity=100, is_active=True)
        crop = Crop(id=50, name="Basmati Rice", category="Paddy", is_active=True)
        db.session.add_all([centre, crop])
        db.session.commit()

        # 3. Slot Management
        today = date.today()
        slot = Slot(
            id=50,
            centre_id=50,
            crop_id=50,
            slot_date=today,
            start_time=time(9, 0),
            end_time=time(12, 0),
            capacity=10,
            status=SlotStatus.OPEN,
        )
        db.session.add(slot)
        db.session.commit()

        # 4. Farmer Booking & Token Generation
        booking = create_booking(user_id=501, slot_id=50)
        assert booking.id is not None
        assert booking.token_number is not None
        assert booking.status == BookingStatus.CONFIRMED

        # 5. Queue Estimation
        q_est = get_booking_queue_status(booking.id, is_staff_or_admin=True)
        assert q_est["queue_position"] >= 1
        assert "estimated_wait_minutes" in q_est

        # 6. Delay Recorded & Wait Time Recalculated
        delay = create_delay(
            data={"centre_id": 50, "delay_date": str(today), "delay_minutes": 25, "reason": "System Delay Test"},
            current_user_id=502,
        )
        assert delay.id is not None
        updated_q = get_booking_queue_status(booking.id, is_staff_or_admin=True)
        assert updated_q["active_delay_minutes"] == 25

        # 7. Notification Verification
        notifs = Notification.query.filter_by(user_id=501).all()
        assert len(notifs) >= 1

        # 8. Procurement Status Tracking
        proc = create_procurement(
            booking_id=booking.id,
            data={"procurement_status": "COMPLETED", "quantity": 30.0, "unit": "quintal"},
        )
        assert proc.procurement_status == ProcurementStatus.COMPLETED

        # 9. Payment Status Tracking
        pay = create_payment(
            booking_id=booking.id,
            data={"payment_status": "PAID", "amount": 67500.0, "payment_reference": "PAY-E2E-999"},
        )
        assert pay.payment_status == PaymentStatus.PAID

        # 10. Admin Analytics Overview
        overview = get_overview_analytics()
        assert overview["total_farmers"] >= 1
        assert overview["todays_completed_procurements"] >= 1

        # 11. Audit Trail Verification
        logs, total = get_audit_logs(entity_type="DELAY")
        assert total >= 1
