"""Tests for Crop Catalogue API (/api/crops).

Covers:
- Listing crops (active only for farmers/staff, all for admin with flag)
- Viewing crop details
- Creation, update, deactivation (soft delete) with role authorization matrix
- Validations (duplicate names, length limits)
"""

import pytest
from unittest.mock import MagicMock, patch

from app.extensions import db
from app.models import User, Crop, UserRole


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
def sample_crops(app):
    with app.app_context():
        c1 = Crop(name="Wheat", category="Cereal", is_active=True)
        c2 = Crop(name="Rice", category="Cereal", is_active=True)
        c3 = Crop(name="Old Barley", category="Cereal", is_active=False)
        db.session.add_all([c1, c2, c3])
        db.session.commit()
        yield [c1, c2, c3]


class TestCropListAndView:
    """Tests for GET /api/crops and GET /api/crops/<id>"""

    def test_farmer_can_list_active_crops(self, client, farmer_user, sample_crops):
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp = client.get("/api/crops", headers=auth_header())
            assert resp.status_code == 200

            crops = resp.get_json()["crops"]
            assert len(crops) == 2
            names = [c["name"] for c in crops]
            assert "Wheat" in names
            assert "Rice" in names
            assert "Old Barley" not in names

    def test_staff_can_list_active_crops(self, client, staff_user, sample_crops):
        su = make_mock_user(user_id="staff-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp = client.get("/api/crops", headers=auth_header())
            assert resp.status_code == 200
            assert len(resp.get_json()["crops"]) == 2

    def test_admin_can_list_all_crops(self, client, admin_user, sample_crops):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp = client.get("/api/crops?all=true", headers=auth_header())
            assert resp.status_code == 200

            crops = resp.get_json()["crops"]
            assert len(crops) == 3

    def test_deactivated_crop_not_shown_to_farmer(self, client, farmer_user, sample_crops):
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            inactive_id = sample_crops[2].id
            resp = client.get(f"/api/crops/{inactive_id}", headers=auth_header())
            assert resp.status_code == 404

    def test_unauthenticated_request_returns_401(self, client):
        resp = client.get("/api/crops")
        assert resp.status_code == 401


class TestCropCreationAndUpdate:
    """Tests for POST /api/crops, PUT /api/crops/<id>, DELETE /api/crops/<id>"""

    def test_admin_can_create_crop(self, client, admin_user):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp = client.post("/api/crops", json={"name": "Mustard", "category": "Oilseed"}, headers=auth_header())
            assert resp.status_code == 201

            data = resp.get_json()["crop"]
            assert data["name"] == "Mustard"
            assert data["category"] == "Oilseed"
            assert data["is_active"] is True

    def test_farmer_cannot_create_crop(self, client, farmer_user):
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp = client.post("/api/crops", json={"name": "Illegal"}, headers=auth_header())
            assert resp.status_code == 403

    def test_staff_cannot_create_crop(self, client, staff_user):
        su = make_mock_user(user_id="staff-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp = client.post("/api/crops", json={"name": "Illegal"}, headers=auth_header())
            assert resp.status_code == 403

    def test_duplicate_crop_name_rejected(self, client, admin_user, sample_crops):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp = client.post("/api/crops", json={"name": "Wheat"}, headers=auth_header())
            assert resp.status_code == 409
            assert "already exists" in resp.get_json()["message"]

    def test_invalid_crop_input_rejected(self, client, admin_user):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp = client.post("/api/crops", json={"name": ""}, headers=auth_header())
            assert resp.status_code == 400

    def test_admin_can_update_crop(self, client, admin_user, sample_crops):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            crop_id = sample_crops[0].id
            resp = client.put(f"/api/crops/{crop_id}", json={"category": "Golden Grain"}, headers=auth_header())
            assert resp.status_code == 200
            assert resp.get_json()["crop"]["category"] == "Golden Grain"

    def test_farmer_cannot_update_crop(self, client, farmer_user, sample_crops):
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            crop_id = sample_crops[0].id
            resp = client.put(f"/api/crops/{crop_id}", json={"name": "Hacked"}, headers=auth_header())
            assert resp.status_code == 403

    def test_admin_can_deactivate_crop(self, client, app, admin_user, sample_crops):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            crop_id = sample_crops[0].id
            resp = client.delete(f"/api/crops/{crop_id}", headers=auth_header())
            assert resp.status_code == 200
            assert resp.get_json()["crop"]["is_active"] is False

            with app.app_context():
                c = db.session.get(Crop, crop_id)
                assert c.is_active is False
