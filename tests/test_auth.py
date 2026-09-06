"""Authentication tests using mocked Supabase Auth.

These tests mock all Supabase SDK interactions to avoid requiring
real Supabase credentials.
"""

import pytest
import httpx
from unittest.mock import MagicMock, patch
from flask import g

from app.models import User, Farmer, UserRole
from app.extensions import db


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


class TestRegistrationSupabaseTransportErrors:
    """Regression tests for backend-to-Supabase transport failures.

    Production bug: the supabase-auth SDK hard-codes ``http2=True`` on its
    internal httpx client; over the Render -> Supabase (Cloudflare edge) path
    that surfaced as ``httpx.RemoteProtocolError: illegal request line`` and a
    generic 500 / browser "Network error".  The app must (a) use an HTTP/1.1
    httpx client and (b) convert transport-level failures into clean 503s.
    """

    def test_remote_protocol_error_returns_503_not_500(self, client, mock_supabase):
        """The exact production failure must map to 503, never crash to 500."""
        mock_supabase.auth.sign_up.side_effect = httpx.RemoteProtocolError(
            "illegal request line"
        )
        resp = client.post("/api/auth/register", json={
            "email": "transport@example.com", "password": "securepassword",
            "name": "Transport Error",
        })
        assert resp.status_code == 503
        assert resp.get_json()["error"] == "Service unavailable"

    def test_connect_timeout_returns_503(self, client, mock_supabase):
        mock_supabase.auth.sign_up.side_effect = httpx.ConnectTimeout(
            "connect timed out",
            request=httpx.Request(
                "POST", "https://example.supabase.co"
            ),
        )
        resp = client.post("/api/auth/register", json={
            "email": "timeout@example.com", "password": "securepassword", "name": "T",
        })
        assert resp.status_code == 503

    def test_weak_password_returns_400_not_500(self, client, mock_supabase):
        """Supabase's weak-password rejection must not become a raw 500."""
        from supabase_auth.errors import AuthWeakPasswordError
        mock_supabase.auth.sign_up.side_effect = AuthWeakPasswordError(
            "Password should contain at least one of each: ...", 422, ["weak_password"]
        )
        resp = client.post("/api/auth/register", json={
            "email": "weak@example.com", "password": "123", "name": "Weak",
        })
        assert resp.status_code == 400

    def test_retryable_error_returns_400_not_500(self, client, mock_supabase):
        """Supabase 5xx/retryable responses must surface as AuthError."""
        from supabase_auth.errors import AuthRetryableError
        mock_supabase.auth.sign_up.side_effect = AuthRetryableError("temporary", 503)
        resp = client.post("/api/auth/register", json={
            "email": "retry@example.com", "password": "securepassword", "name": "R",
        })
        assert resp.status_code == 400

    def test_login_transport_error_returns_503(self, client, mock_supabase):
        """The same transport crash on login must also map to 503."""
        mock_supabase.auth.sign_in_with_password.side_effect = httpx.RemoteProtocolError(
            "illegal request line"
        )
        resp = client.post("/api/auth/login", json={
            "email": "login@example.com", "password": "securepassword",
        })
        assert resp.status_code == 503

    def test_duplicate_email_via_api_code_returns_409(self, client, mock_supabase):
        """Supabase 'user_already_exists' API code must map to 409 (not 500)."""
        from supabase_auth.errors import AuthApiError
        mock_supabase.auth.sign_up.side_effect = AuthApiError(
            "User already registered", 400, "user_already_exists"
        )
        resp = client.post("/api/auth/register", json={
            "email": "dupcode@example.com", "password": "securepassword", "name": "D",
        })
        assert resp.status_code == 409

    def test_duplicate_phone_local_constraint_returns_409(self, app, client, mock_supabase):
        """Local unique constraint on farmers.phone must map to 409, not a 500.

        Supabase only enforces phone uniqueness when phone is a login method,
        so a second account with the same phone passes Supabase auth and fails
        only at the local DB insert.
        """
        existing_user = User(
            supabase_user_id="existing-phone-user", role=UserRole.FARMER, is_active=True
        )
        with app.app_context():
            db.session.add(existing_user)
            db.session.flush()
            db.session.add(Farmer(user_id=existing_user.id, name="First", phone="9876543210"))
            db.session.commit()

        mock_supabase.auth.sign_up.return_value = make_mock_auth_response(
            make_mock_supabase_user(user_id="dup-phone-uuid"),
            make_mock_session(),
        )
        resp = client.post("/api/auth/register", json={
            "email": "dupphone@example.com", "password": "securepassword",
            "name": "Dup Phone", "phone": "9876543210",
        })
        assert resp.status_code == 409
        assert "already exists" in resp.get_json()["message"]

    def test_supabase_client_uses_http1_httpx_client(self, app):
        """get_supabase_client() must inject an HTTP/1.1 httpx client.

        Regression: the SDK defaults to http2=True; forcing HTTP/1.1 avoids the
        RemoteProtocolError that broke /api/auth/register on Render.
        """
        from app.auth.service import get_supabase_client

        captured = {}

        def fake_create_client(url, key, options=None):
            captured["url"] = url
            captured["key"] = key
            captured["options"] = options
            return MagicMock()

        with patch("app.auth.service.create_client", side_effect=fake_create_client):
            with app.app_context():
                app.config["SUPABASE_URL"] = "https://example.supabase.co"
                app.config["SUPABASE_ANON_KEY"] = "anon-key"
                get_supabase_client()

        options = captured["options"]
        assert options is not None
        client = options.httpx_client
        assert client is not None
        transport = client._transport
        assert transport._pool._http2 is False
        assert transport._pool._http1 is True

    def test_supabase_client_normalizes_url_whitespace(self, app):
        """Whitespace/quotes accidentally left on SUPABASE_URL must not break calls."""
        from app.auth.service import get_supabase_client

        captured = {}

        def fake_create_client(url, key, options=None):
            captured["url"] = url
            return MagicMock()

        with patch("app.auth.service.create_client", side_effect=fake_create_client):
            with app.app_context():
                app.config["SUPABASE_URL"] = '  "https://example.supabase.co"  '
                app.config["SUPABASE_ANON_KEY"] = "anon-key"
                get_supabase_client()
        assert captured["url"] == "https://example.supabase.co"


class TestRegistrationNullableFields:
    """Regression tests for null/missing optional-string registration fields.

    Production bug: ``data.get("phone", "").strip()`` raised AttributeError
    when the client explicitly sent ``"phone": null`` (the ``""`` default only
    applies to *missing* keys, never to explicit nulls). The same pattern
    must be safe for email/name/password (required) and phone (optional).
    """

    def _register(self, client, mock_supabase, payload, user_id="nullable-field-uuid"):
        mock_supabase.auth.sign_up.return_value = make_mock_auth_response(
            make_mock_supabase_user(user_id=user_id),
            make_mock_session(),
        )
        return client.post("/api/auth/register", json=payload)

    def test_register_explicit_null_phone_succeeds(self, client, mock_supabase):
        """The original production traceback: phone explicitly null -> 201, phone stored as None."""
        resp = self._register(client, mock_supabase, {
            "email": "nullphone@example.com",
            "password": "securepassword",
            "name": "Null Phone",
            "phone": None,
        })
        assert resp.status_code == 201
        user = User.query.filter_by(supabase_user_id="nullable-field-uuid").first()
        assert user is not None
        assert user.farmer is not None
        assert user.farmer.phone is None
        # Supabase metadata must receive an empty string, never the literal "None"
        data_sent = mock_supabase.auth.sign_up.call_args.args[0]["options"]["data"]
        assert data_sent["phone"] == ""

    @pytest.mark.parametrize("phone_value", [
        pytest.param(None, id="null"),
        pytest.param("", id="empty-string"),
        pytest.param("   ", id="whitespace"),
    ])
    def test_register_phone_null_empty_whitespace_stored_as_none(
        self, client, mock_supabase, phone_value
    ):
        payload = {
            "email": "phoneparam@example.com",
            "password": "securepassword",
            "name": "Phone Test",
            "phone": phone_value,
        }
        resp = self._register(client, mock_supabase, payload, user_id="phone-param-uuid")
        assert resp.status_code == 201
        user = User.query.filter_by(supabase_user_id="phone-param-uuid").first()
        assert user.farmer.phone is None

    def test_register_phone_not_sent_at_all(self, client, mock_supabase):
        """Missing key (legacy behaviour) must keep working."""
        resp = self._register(client, mock_supabase, {
            "email": "nopkey@example.com",
            "password": "securepassword",
            "name": "No Key",
        }, user_id="phone-missing-uuid")
        assert resp.status_code == 201
        user = User.query.filter_by(supabase_user_id="phone-missing-uuid").first()
        assert user.farmer.phone is None

    def test_register_phone_whitespace_padded_is_stored_stripped(self, client, mock_supabase):
        resp = self._register(client, mock_supabase, {
            "email": "stripped@example.com",
            "password": "securepassword",
            "name": "Padded Phone",
            "phone": "  9876543210  ",
        }, user_id="phone-stripped-uuid")
        assert resp.status_code == 201
        user = User.query.filter_by(supabase_user_id="phone-stripped-uuid").first()
        assert user.farmer.phone == "9876543210"

    def test_register_null_required_fields_rejected_with_400(self, client, mock_supabase):
        """null email/name/password -> 400 validation errors, not 500, and no Supabase call."""
        resp = self._register(client, mock_supabase, {
            "email": None,
            "password": None,
            "name": None,
            "phone": "9876543210",
        })
        assert resp.status_code == 400
        body = resp.get_json()
        assert "email is required" in body["messages"]
        assert "password is required" in body["messages"]
        assert "name is required" in body["messages"]
        mock_supabase.auth.sign_up.assert_not_called()

    def test_register_empty_and_whitespace_required_fields_rejected(self, client, mock_supabase):
        resp = self._register(client, mock_supabase, {
            "email": "",
            "password": "",
            "name": "   ",
        })
        assert resp.status_code == 400
        body = resp.get_json()
        assert "email is required" in body["messages"]
        assert "password is required" in body["messages"]
        assert "name is required" in body["messages"]
        mock_supabase.auth.sign_up.assert_not_called()

    def test_register_null_email_still_enforces_format_rules(self, client, mock_supabase):
        """Required-field validation rules are preserved (no weakening)."""
        resp = self._register(client, mock_supabase, {
            "email": "not-an-email",
            "password": "securepassword",
            "name": "T",
        })
        assert resp.status_code == 400
        assert "email is invalid" in resp.get_json()["messages"]

    def test_login_null_email_password_rejected_with_400(self, client, mock_supabase):
        """Same defensive pattern on login: explicit nulls must not 500."""
        resp = client.post("/api/auth/login", json={"email": None, "password": None})
        assert resp.status_code == 400
        body = resp.get_json()
        assert "email is required" in body["messages"]
        assert "password is required" in body["messages"]
        mock_supabase.auth.sign_in_with_password.assert_not_called()


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


class TestSupabaseConfigErrors:
    """Configuration failures must return HTTP 503 (not 400/401 machinery)."""

    def test_login_config_failure_returns_503(self, client):
        from app.auth.exceptions import SupabaseConfigError

        with patch("app.auth.service.get_supabase_client", side_effect=SupabaseConfigError()):
            resp = client.post("/api/auth/login", json={"email": "a@b.com", "password": "password123"})

        assert resp.status_code == 503
        data = resp.get_json()
        assert data["error"] == "Service unavailable"
        assert "not configured" in data["message"].lower()

    def test_register_config_failure_returns_503(self, client):
        from app.auth.exceptions import SupabaseConfigError

        with patch("app.auth.service.get_supabase_client", side_effect=SupabaseConfigError()):
            resp = client.post("/api/auth/register", json={
                "email": "a@b.com", "password": "password123", "name": "Test Farmer",
            })

        assert resp.status_code == 503
        data = resp.get_json()
        assert data["error"] == "Service unavailable"
        assert "not configured" in data["message"].lower()
        # Generic safe message only - no key names or secret values.


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
