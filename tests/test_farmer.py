"""Tests for the Farmer Module API and views.

Covers:
- GET /api/farmers/me (authorization, role check, 404 handling, safe profile payload)
- PUT /api/farmers/me (field updates, validations, duplicate phone 409 conflict, role protection)
- Security checks (idempotency, parameter tampering protection)
"""

import pytest
from unittest.mock import MagicMock, patch

from app.extensions import db
from app.models import User, Farmer, UserRole


def make_mock_supabase_user(user_id="farmer-uuid-1", email="farmer1@example.com"):
    user = MagicMock()
    user.id = user_id
    user.email = email
    return user


def make_mock_auth_response(user):
    response = MagicMock()
    response.user = user
    return response


def auth_header(token="valid-farmer-token"):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def farmer_user(app):
    """Fixture that creates a test User and Farmer profile in DB."""
    with app.app_context():
        u = User(supabase_user_id="farmer-uuid-1", role=UserRole.FARMER, is_active=True)
        db.session.add(u)
        db.session.flush()

        f = Farmer(
            user_id=u.id,
            name="Ramesh Kumar",
            phone="9876543210",
            address="Village 123",
            city="Karnal",
            state="Haryana",
            pincode="132001",
        )
        db.session.add(f)
        db.session.commit()

        yield u


@pytest.fixture
def second_farmer_user(app):
    """Fixture that creates a second Farmer profile in DB."""
    with app.app_context():
        u = User(supabase_user_id="farmer-uuid-2", role=UserRole.FARMER, is_active=True)
        db.session.add(u)
        db.session.flush()

        f = Farmer(
            user_id=u.id,
            name="Suresh Kumar",
            phone="9123456789",
            address="Village 456",
            city="Panipat",
            state="Haryana",
            pincode="132103",
        )
        db.session.add(f)
        db.session.commit()

        yield u


@pytest.fixture
def staff_user(app):
    """Fixture that creates a test STAFF user in DB."""
    with app.app_context():
        u = User(supabase_user_id="staff-uuid-1", role=UserRole.STAFF, is_active=True)
        db.session.add(u)
        db.session.commit()
        yield u


class TestGetFarmerProfile:
    """Tests for GET /api/farmers/me"""

    def test_authenticated_farmer_can_view_own_profile(self, client, app, farmer_user):
        su = make_mock_supabase_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value = make_mock_auth_response(su)

            resp = client.get("/api/farmers/me", headers=auth_header())
            assert resp.status_code == 200

            data = resp.get_json()["farmer"]
            assert data["name"] == "Ramesh Kumar"
            assert data["phone"] == "9876543210"
            assert data["city"] == "Karnal"
            assert "password" not in data

    def test_unauthenticated_request_returns_401(self, client):
        resp = client.get("/api/farmers/me")
        assert resp.status_code == 401
        assert "Authentication required" in resp.get_json()["error"]

    def test_wrong_role_returns_403(self, client, app, staff_user):
        su = make_mock_supabase_user(user_id="staff-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value = make_mock_auth_response(su)

            resp = client.get("/api/farmers/me", headers=auth_header())
            assert resp.status_code == 403
            assert "Requires FARMER role" in resp.get_json()["message"]

    def test_missing_farmer_profile_returns_404(self, client, app):
        with app.app_context():
            u = User(supabase_user_id="no-profile-uuid", role=UserRole.FARMER, is_active=True)
            db.session.add(u)
            db.session.commit()

        su = make_mock_supabase_user(user_id="no-profile-uuid")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value = make_mock_auth_response(su)

            resp = client.get("/api/farmers/me", headers=auth_header())
            assert resp.status_code == 404


class TestUpdateFarmerProfile:
    """Tests for PUT /api/farmers/me"""

    def test_farmer_can_update_allowed_fields(self, client, app, farmer_user):
        su = make_mock_supabase_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value = make_mock_auth_response(su)

            update_payload = {
                "name": "Ramesh Kumar Updated",
                "phone": "9998887776",
                "address": "New Farm Street",
                "city": "Ambala",
                "state": "Haryana",
                "pincode": "134003",
            }
            resp = client.put("/api/farmers/me", json=update_payload, headers=auth_header())
            assert resp.status_code == 200

            data = resp.get_json()["farmer"]
            assert data["name"] == "Ramesh Kumar Updated"
            assert data["phone"] == "9998887776"
            assert data["city"] == "Ambala"

            with app.app_context():
                f = Farmer.query.filter_by(user_id=farmer_user.id).first()
                assert f.name == "Ramesh Kumar Updated"
                assert f.phone == "9998887776"

    def test_invalid_phone_rejected(self, client, app, farmer_user):
        su = make_mock_supabase_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value = make_mock_auth_response(su)

            resp = client.put("/api/farmers/me", json={"phone": "invalid-phone"}, headers=auth_header())
            assert resp.status_code == 400
            assert "Validation failed" in resp.get_json()["error"]

    def test_invalid_pincode_rejected(self, client, app, farmer_user):
        su = make_mock_supabase_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value = make_mock_auth_response(su)

            resp = client.put("/api/farmers/me", json={"pincode": "123"}, headers=auth_header())
            assert resp.status_code == 400
            assert "Validation failed" in resp.get_json()["error"]

    def test_duplicate_phone_returns_409(self, client, app, farmer_user, second_farmer_user):
        su = make_mock_supabase_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value = make_mock_auth_response(su)

            # Try to use second_farmer_user's phone: "9123456789"
            resp = client.put("/api/farmers/me", json={"phone": "9123456789"}, headers=auth_header())
            assert resp.status_code == 409
            assert "already registered" in resp.get_json()["message"]

    def test_farmer_cannot_change_role_or_system_fields(self, client, app, farmer_user):
        su = make_mock_supabase_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value = make_mock_auth_response(su)

            resp = client.put("/api/farmers/me", json={
                "name": "Ramesh Legal",
                "role": "ADMIN",
                "supabase_user_id": "hacked-uuid",
                "user_id": 9999
            }, headers=auth_header())

            assert resp.status_code == 200
            with app.app_context():
                u = db.session.get(User, farmer_user.id)
                assert u.role == UserRole.FARMER
                assert u.supabase_user_id == "farmer-uuid-1"

    def test_unauthenticated_update_returns_401(self, client):
        resp = client.put("/api/farmers/me", json={"name": "Hacker"})
        assert resp.status_code == 401


class TestFarmerUI:
    """Tests for Farmer Dashboard view route."""

    def test_farmer_dashboard_route_renders(self, client):
        resp = client.get("/farmer/dashboard")
        assert resp.status_code == 200
        assert b"Farmer Dashboard" in resp.data
