"""Authentication tests using mocked Supabase Auth.

These tests mock all Supabase SDK interactions to avoid requiring
real Supabase credentials.
"""

import pytest
from unittest.mock import MagicMock, patch
from flask import g

from app.models import User, Farmer, UserRole


def make_mock_supabase_user(user_id="supabase-uuid-123", email="farmer@example.com"):
    user = MagicMock()
    user.id = user_id
    user.email = email
    user.user_metadata = {"name": "Test Farmer", "phone": "9876543210"}
    return user


def make_mock_session(access_token="mock-access-token", refresh_token="mock-refresh-token"):
    session = MagicMock()
    session.access_token = access_token
    session.refresh_token = refresh_token
    return session


def make_mock_auth_response(user, session):
    response = MagicMock()
    response.user = user
    response.session = session
    return response


def auth_header(token="valid-test-token"):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_supabase():
    mock_client = MagicMock()
    mock_client.auth = MagicMock()
    mock_client.auth.sign_up = MagicMock()
    mock_client.auth.sign_in_with_password = MagicMock()
    mock_client.auth.get_user = MagicMock()
    mock_client.auth.admin = MagicMock()
    mock_client.auth.admin.sign_out = MagicMock()
    with patch("app.auth.service.get_supabase_client", return_value=mock_client):
        yield mock_client

class TestRegistration:
    """Tests for POST /api/auth/register"""

    def test_valid_farmer_registration(self, client, mock_supabase):
        mock_supabase.auth.sign_up.return_value = make_mock_auth_response(
            make_mock_supabase_user(user_id="new-uuid"),
            make_mock_session(),
        )
        resp = client.post("/api/auth/register", json={
            "email": "newfarmer@example.com", "password": "securepassword",
            "name": "New Farmer", "phone": "9876543210",
        })
        assert resp.status_code == 201
        assert Farmer.query.count() == 1
        f = Farmer.query.first()
        assert f.name == "New Farmer"

    def test_registration_missing_email(self, client, mock_supabase):
        resp = client.post("/api/auth/register", json={"password": "pw", "name": "T"})
        assert resp.status_code == 400
        mock_supabase.auth.sign_up.assert_not_called()

    def test_registration_short_password(self, client, mock_supabase):
        resp = client.post("/api/auth/register", json={"email": "a@b.com", "password": "12345", "name": "T"})
        assert resp.status_code == 400

    def test_registration_invalid_email(self, client, mock_supabase):
        resp = client.post("/api/auth/register", json={"email": "not-an-email", "password": "securepassword", "name": "T"})
        assert resp.status_code == 400

    def test_duplicate_email(self, client, mock_supabase):
        from app.auth.exceptions import DuplicateUserError
        mock_supabase.auth.sign_up.side_effect = DuplicateUserError()
        resp = client.post("/api/auth/register", json={"email": "existing@example.com", "password": "securepassword", "name": "T"})
        assert resp.status_code == 409

    def test_role_cannot_be_admin_via_registration(self, client, mock_supabase):
        mock_supabase.auth.sign_up.return_value = make_mock_auth_response(
            make_mock_supabase_user(user_id="admin-attempt"),
            make_mock_session(),
        )
        resp = client.post("/api/auth/register", json={"email": "hacker@example.com", "password": "securepassword", "name": "H", "role": "ADMIN"})
        assert resp.status_code == 201
        u = User.query.filter_by(supabase_user_id="admin-attempt").first()
        assert u.role == UserRole.FARMER


class TestLogin:
    """Tests for POST /api/auth/login"""

    def test_valid_credentials(self, client, mock_supabase):
        mock_supabase.auth.sign_in_with_password.return_value = make_mock_auth_response(
            make_mock_supabase_user(email="farmer@example.com"),
            make_mock_session("access-123", "refresh-456"),
        )
        resp = client.post("/api/auth/login", json={"email": "farmer@example.com", "password": "correctpassword"})
        assert resp.status_code == 200
        assert resp.get_json()["user"]["access_token"] == "access-123"

    def test_invalid_credentials(self, client, mock_supabase):
        from app.auth.exceptions import InvalidCredentialsError
        mock_supabase.auth.sign_in_with_password.side_effect = InvalidCredentialsError()
        resp = client.post("/api/auth/login", json={"email": "a@b.com", "password": "wrong"})
        assert resp.status_code == 401

    def test_login_missing_email(self, client, mock_supabase):
        resp = client.post("/api/auth/login", json={"password": "pw"})
        assert resp.status_code == 400

    def test_login_missing_password(self, client, mock_supabase):
        resp = client.post("/api/auth/login", json={"email": "a@b.com"})
        assert resp.status_code == 400

    def test_login_no_body(self, client, mock_supabase):
        resp = client.post("/api/auth/login")
        assert resp.status_code == 400

    def test_inactive_user_login(self, client, app, mock_supabase):
        su = make_mock_supabase_user(user_id="inactive-uuid", email="inactive@example.com")
        mock_supabase.auth.sign_in_with_password.return_value = make_mock_auth_response(
            su, make_mock_session("access-123", "refresh-456")
        )
        with app.app_context():
            db = app.extensions["sqlalchemy"].session
            u = User(supabase_user_id="inactive-uuid", role=UserRole.FARMER, is_active=False)
            db.add(u)
            db.commit()

        resp = client.post("/api/auth/login", json={"email": "inactive@example.com", "password": "password123"})
        assert resp.status_code == 401
        assert "disabled" in resp.get_json()["error"].lower() or "disabled" in resp.get_json()["message"].lower()


class TestJWTVerification:
    """Tests for JWT token verification in protected endpoints."""

    def test_missing_token(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401
        assert "Authentication required" in resp.get_json()["error"]

    def test_malformed_token(self, client):
        resp = client.get("/api/auth/me", headers={"Authorization": "Basic sometoken"})
        assert resp.status_code == 401

    def test_invalid_token(self, client, mock_supabase):
        mock_supabase.auth.get_user.side_effect = Exception("Invalid token")
        resp = client.get("/api/auth/me", headers=auth_header("invalid-token"))
        assert resp.status_code == 401

    def test_expired_token(self, client, mock_supabase):
        from supabase_auth.errors import AuthApiError
        mock_supabase.auth.get_user.side_effect = AuthApiError("JWT expired", status=401, code="invalid_jwt")
        resp = client.get("/api/auth/me", headers=auth_header("expired-token"))
        assert resp.status_code == 401

    def test_valid_token(self, client, app, mock_supabase):
        su = make_mock_supabase_user(user_id="valid-uuid", email="valid@example.com")
        mock_supabase.auth.get_user.return_value = make_mock_auth_response(su, make_mock_session())
        with app.app_context():
            u = User(supabase_user_id="valid-uuid", role=UserRole.FARMER, is_active=True)
            db = app.extensions["sqlalchemy"].session
            db.add(u)
            db.commit()
        resp = client.get("/api/auth/me", headers=auth_header("valid-token"))
        assert resp.status_code == 200
        assert resp.get_json()["user"]["supabase_user_id"] == "valid-uuid"

    def test_inactive_user_token(self, client, app, mock_supabase):
        su = make_mock_supabase_user(user_id="inactive-token-uuid", email="inactive@example.com")
        mock_supabase.auth.get_user.return_value = make_mock_auth_response(su, make_mock_session())
        with app.app_context():
            u = User(supabase_user_id="inactive-token-uuid", role=UserRole.FARMER, is_active=False)
            db = app.extensions["sqlalchemy"].session
            db.add(u)
            db.commit()
        resp = client.get("/api/auth/me", headers=auth_header("valid-token"))
        assert resp.status_code == 401
        assert "disabled" in resp.get_json()["error"].lower() or "deactivated" in resp.get_json()["message"].lower()

    def test_unknown_supabase_user(self, client, mock_supabase):
        su = make_mock_supabase_user(user_id="unknown-uuid", email="unknown@example.com")
        mock_supabase.auth.get_user.return_value = make_mock_auth_response(su, make_mock_session())
        resp = client.get("/api/auth/me", headers=auth_header("unmapped-token"))
        assert resp.status_code == 401
        assert "not found" in resp.get_json()["message"]


class TestAuthorization:
    """Tests for role-based access control."""

    def _setup_role_user(self, app, role, supabase_id):
        with app.app_context():
            u = User(supabase_user_id=supabase_id, role=role, is_active=True)
            db = app.extensions["sqlalchemy"].session
            db.add(u)
            db.commit()

    def _register_test_routes(self, app):
        from app.auth.decorators import login_required, role_required, roles_required
        from flask import Blueprint, jsonify
        test_bp = Blueprint("test_authz", __name__, url_prefix="/api/test")

        @test_bp.route("/farmer")
        @login_required
        def _farmer():
            return jsonify({"role": g.current_user.role})

        @test_bp.route("/staff")
        @login_required
        @role_required(UserRole.STAFF)
        def _staff():
            return jsonify({"role": g.current_user.role})

        @test_bp.route("/admin")
        @login_required
        @role_required(UserRole.ADMIN)
        def _admin():
            return jsonify({"role": g.current_user.role})

        app.register_blueprint(test_bp)

    def test_farmer_access(self, app, client):
        self._setup_role_user(app, UserRole.FARMER, "farmer-az-uuid")
        self._register_test_routes(app)
        with patch("app.auth.service.get_supabase_client") as mock_gc, \
             patch("app.auth.decorators.get_local_user") as mock_gl:
            su = make_mock_supabase_user(user_id="farmer-az-uuid")
            lu = User(supabase_user_id="farmer-az-uuid", role=UserRole.FARMER, is_active=True)
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value = make_mock_auth_response(su, None)
            mock_gl.return_value = lu
            resp = client.get("/api/test/farmer", headers=auth_header())
            assert resp.status_code == 200

    def test_staff_access(self, app, client):
        self._setup_role_user(app, UserRole.STAFF, "staff-az-uuid")
        self._register_test_routes(app)
        with patch("app.auth.service.get_supabase_client") as mock_gc, \
             patch("app.auth.decorators.get_local_user") as mock_gl:
            su = make_mock_supabase_user(user_id="staff-az-uuid")
            lu = User(supabase_user_id="staff-az-uuid", role=UserRole.STAFF, is_active=True)
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value = make_mock_auth_response(su, None)
            mock_gl.return_value = lu
            resp = client.get("/api/test/staff", headers=auth_header())
            assert resp.status_code == 200

    def test_admin_access(self, app, client):
        self._setup_role_user(app, UserRole.ADMIN, "admin-az-uuid")
        self._register_test_routes(app)
        with patch("app.auth.service.get_supabase_client") as mock_gc, \
             patch("app.auth.decorators.get_local_user") as mock_gl:
            su = make_mock_supabase_user(user_id="admin-az-uuid")
            lu = User(supabase_user_id="admin-az-uuid", role=UserRole.ADMIN, is_active=True)
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value = make_mock_auth_response(su, None)
            mock_gl.return_value = lu
            resp = client.get("/api/test/admin", headers=auth_header())
            assert resp.status_code == 200

    def test_farmer_cannot_access_admin(self, app, client):
        self._setup_role_user(app, UserRole.FARMER, "farmer-f1")
        self._register_test_routes(app)
        with patch("app.auth.service.get_supabase_client") as mock_gc, \
             patch("app.auth.decorators.get_local_user") as mock_gl:
            su = make_mock_supabase_user(user_id="farmer-f1")
            lu = User(supabase_user_id="farmer-f1", role=UserRole.FARMER, is_active=True)
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value = make_mock_auth_response(su, None)
            mock_gl.return_value = lu
            resp = client.get("/api/test/admin", headers=auth_header())
            assert resp.status_code == 403

    def test_staff_cannot_access_admin(self, app, client):
        self._setup_role_user(app, UserRole.STAFF, "staff-f1")
        self._register_test_routes(app)
        with patch("app.auth.service.get_supabase_client") as mock_gc, \
             patch("app.auth.decorators.get_local_user") as mock_gl:
            su = make_mock_supabase_user(user_id="staff-f1")
            lu = User(supabase_user_id="staff-f1", role=UserRole.STAFF, is_active=True)
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value = make_mock_auth_response(su, None)
            mock_gl.return_value = lu
            resp = client.get("/api/test/admin", headers=auth_header())
            assert resp.status_code == 403

    def test_unauthenticated_returns_401(self, app, client):
        self._register_test_routes(app)
        resp = client.get("/api/test/admin")
        assert resp.status_code == 401


class TestUserSynchronization:
    """Tests for Supabase-to-local user synchronization."""

    def test_creates_local_user_on_login(self, app, mock_supabase):
        from app.auth.service import login_user
        su = make_mock_supabase_user(user_id="sync-new-uuid")
        mock_supabase.auth.sign_in_with_password.return_value = make_mock_auth_response(su, make_mock_session())
        with app.app_context():
            login_user("sync@example.com", "password123")
            assert User.query.count() == 1
            u = User.query.filter_by(supabase_user_id="sync-new-uuid").first()
            assert u is not None
            assert u.role == UserRole.FARMER
            assert Farmer.query.count() == 1

    def test_does_not_duplicate_existing_user(self, app, mock_supabase):
        from app.auth.service import login_user
        su = make_mock_supabase_user(user_id="sync-existing-uuid")
        mock_supabase.auth.sign_in_with_password.return_value = make_mock_auth_response(su, make_mock_session())
        with app.app_context():
            login_user("existing@example.com", "password123")
            assert User.query.count() == 1
            login_user("existing@example.com", "password123")
            assert User.query.count() == 1

    def test_correctly_maps_supabase_user_id(self, app, mock_supabase):
        from app.auth.service import login_user
        su = make_mock_supabase_user(user_id="mapping-test-uuid", email="mapping@example.com")
        mock_supabase.auth.sign_in_with_password.return_value = make_mock_auth_response(su, make_mock_session())
        with app.app_context():
            login_user("mapping@example.com", "password123")
            u = User.query.filter_by(supabase_user_id="mapping-test-uuid").first()
            assert u is not None
            assert u.supabase_user_id == "mapping-test-uuid"
