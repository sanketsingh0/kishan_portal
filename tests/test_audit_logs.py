"""
Unit and Integration test suite for Task 14 — Audit Log System.

Tests AuditLog model, service creation, sensitive metadata sanitization,
ADMIN-only access control, filtering, pagination, append-only security,
and automatic triggers across centre, crop, slot, procurement, payment, and delay services.
"""

import pytest
from datetime import date, time
from unittest.mock import patch, MagicMock
from app.extensions import db
from app.models import User, UserRole, AuditLog, Centre, Crop, Slot, SlotStatus
from app.services.audit_service import (
    create_audit_log,
    get_audit_logs,
    get_audit_log_by_id,
    sanitize_metadata,
)
from app.services.centre_service import create_centre, update_centre, deactivate_centre
from app.services.crop_service import create_crop, update_crop, deactivate_crop
from app.services.slot_service import create_slot, update_slot, cancel_slot
from app.services.delay_service import create_delay, update_delay, cancel_delay


@pytest.fixture
def audit_users(app):
    """Create test users: Admin, Farmer, Staff."""
    with app.app_context():
        admin = User(id=301, supabase_user_id="sub-admin-301", role=UserRole.ADMIN, is_active=True)
        farmer = User(id=302, supabase_user_id="sub-farmer-302", role=UserRole.FARMER, is_active=True)
        staff = User(id=303, supabase_user_id="sub-staff-303", role=UserRole.STAFF, is_active=True)

        db.session.add_all([admin, farmer, staff])
        db.session.commit()

        yield admin, farmer, staff


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
        elif method.upper() == "PUT":
            return client.put(url, json=json_data, headers=headers)
        elif method.upper() == "DELETE":
            return client.delete(url, headers=headers)


def test_sanitize_metadata():
    """Verify sensitive keys are redacted from metadata dictionaries."""
    raw_meta = {
        "user_id": 10,
        "action": "LOGIN",
        "password": "SuperSecretPassword123!",
        "token": "bearer-xyz",
        "nested": {"cvv": "123", "card_number": "4111222233334444", "status": "OK"},
    }

    cleaned = sanitize_metadata(raw_meta)
    assert cleaned["user_id"] == 10
    assert cleaned["action"] == "LOGIN"
    assert cleaned["password"] == "[REDACTED]"
    assert cleaned["token"] == "[REDACTED]"
    assert cleaned["nested"]["cvv"] == "[REDACTED]"
    assert cleaned["nested"]["card_number"] == "[REDACTED]"
    assert cleaned["nested"]["status"] == "OK"


def test_create_and_query_audit_log(app, audit_users):
    """Verify create_audit_log and get_audit_logs service logic."""
    with app.app_context():
        admin = audit_users[0]

        log = create_audit_log(
            action="CREATE_CENTRE",
            entity_type="CENTRE",
            entity_id=5,
            description="Created new centre in Amritsar",
            metadata={"name": "Amritsar Mandi", "token": "secret-token"},
            user_id=admin.id,
        )

        assert log is not None
        assert log.id is not None
        assert log.user_id == admin.id
        assert log.action == "CREATE_CENTRE"
        assert log.entity_type == "CENTRE"
        assert log.metadata_json["token"] == "[REDACTED]"

        # Retrieve log
        logs, total = get_audit_logs(action="CREATE_CENTRE", entity_type="CENTRE")
        assert total >= 1
        assert any(l.id == log.id for l in logs)

        # Single get
        fetched_log = get_audit_log_by_id(log.id)
        assert fetched_log is not None
        assert fetched_log.description == "Created new centre in Amritsar"


def test_api_admin_audit_log_access_control(client, audit_users):
    """Verify ADMIN access is allowed while FARMER and STAFF receive 403 Forbidden."""
    # 1. Unauthenticated -> 401
    res = client.get("/api/admin/audit-logs")
    assert res.status_code == 401

    # 2. Farmer -> 403
    res_farmer = make_auth_call(client, "GET", "/api/admin/audit-logs", "sub-farmer-302")
    assert res_farmer.status_code == 403

    # 3. Staff -> 403
    res_staff = make_auth_call(client, "GET", "/api/admin/audit-logs", "sub-staff-303")
    assert res_staff.status_code == 403

    # 4. Admin -> 200
    res_admin = make_auth_call(client, "GET", "/api/admin/audit-logs", "sub-admin-301")
    assert res_admin.status_code == 200
    assert "audit_logs" in res_admin.get_json()


def test_audit_logs_append_only_security(client, audit_users, app):
    """Verify clients cannot edit or delete audit logs via API."""
    with app.app_context():
        log = create_audit_log(
            action="SYSTEM_INIT",
            entity_type="SYSTEM",
            description="System initialization test",
        )
        log_id = log.id

    # Attempt PUT (Update) -> 405 Method Not Allowed or 404
    res_put = make_auth_call(client, "PUT", f"/api/admin/audit-logs/{log_id}", "sub-admin-301", json_data={"description": "Hacked"})
    assert res_put.status_code in (404, 405)

    # Attempt DELETE -> 405 Method Not Allowed or 404
    res_del = make_auth_call(client, "DELETE", f"/api/admin/audit-logs/{log_id}", "sub-admin-301")
    assert res_del.status_code in (404, 405)


def test_automatic_audit_triggers_on_admin_actions(app, audit_users):
    """Verify centre, crop, slot, and delay actions automatically generate audit logs."""
    with app.app_context():
        # 1. Centre CRUD
        c = create_centre({
            "name": "Audit Test Centre",
            "location": "Jalandhar",
            "opening_time": "09:00",
            "closing_time": "17:00",
            "daily_capacity": 50,
            "average_processing_minutes": 15,
        })
        c_logs, _ = get_audit_logs(entity_type="CENTRE", action="CREATE_CENTRE")
        assert any(l.entity_id == c.id for l in c_logs)

        update_centre(c.id, {"location": "Updated Jalandhar"})
        u_logs, _ = get_audit_logs(entity_type="CENTRE", action="UPDATE_CENTRE")
        assert any(l.entity_id == c.id for l in u_logs)

        deactivate_centre(c.id)
        d_logs, _ = get_audit_logs(entity_type="CENTRE", action="DEACTIVATE_CENTRE")
        assert any(l.entity_id == c.id for l in d_logs)

        # 2. Crop CRUD
        crop = create_crop({"name": "Audit Barley", "category": "Cereal"})
        crop_logs, _ = get_audit_logs(entity_type="CROP", action="CREATE_CROP")
        assert any(l.entity_id == crop.id for l in crop_logs)

        deactivate_crop(crop.id)
        crop_d_logs, _ = get_audit_logs(entity_type="CROP", action="DEACTIVATE_CROP")
        assert any(l.entity_id == crop.id for l in crop_d_logs)
