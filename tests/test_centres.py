"""Tests for Centre Management API (/api/centres).

Covers:
- Listing centres (active only for farmers/staff, all for admin with flag)
- Viewing centre details
- Creation, update, deactivation (soft delete) with role authorization matrix
- Validations (duplicate names, operating hours, positive capacity/processing time)
"""

import pytest
from unittest.mock import MagicMock, patch

from app.extensions import db
from app.models import User, Centre, UserRole


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
def sample_centres(app):
    with app.app_context():
        from datetime import time
        c1 = Centre(
            name="Active Centre 1",
            location="Karnal",
            opening_time=time(9, 0),
            closing_time=time(17, 0),
            daily_capacity=100,
            average_processing_minutes=15,
            is_active=True,
        )
        c2 = Centre(
            name="Inactive Centre 2",
            location="Panipat",
            opening_time=time(8, 30),
            closing_time=time(16, 30),
            daily_capacity=50,
            average_processing_minutes=20,
            is_active=False,
        )
        db.session.add_all([c1, c2])
        db.session.commit()
        yield [c1, c2]


class TestCentreListAndView:
    """Tests for GET /api/centres and GET /api/centres/<id>"""

    def test_farmer_can_list_active_centres(self, client, farmer_user, sample_centres):
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp = client.get("/api/centres", headers=auth_header())
            assert resp.status_code == 200

            centres = resp.get_json()["centres"]
            assert len(centres) == 1
            assert centres[0]["name"] == "Active Centre 1"

    def test_staff_can_list_active_centres(self, client, staff_user, sample_centres):
        su = make_mock_user(user_id="staff-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp = client.get("/api/centres", headers=auth_header())
            assert resp.status_code == 200
            assert len(resp.get_json()["centres"]) == 1

    def test_admin_can_list_all_centres(self, client, admin_user, sample_centres):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp = client.get("/api/centres?all=true", headers=auth_header())
            assert resp.status_code == 200

            centres = resp.get_json()["centres"]
            assert len(centres) == 2

    def test_non_admin_cannot_see_inactive_centres(self, client, farmer_user, sample_centres):
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            # Even if farmer passes all=true, inactive centres are omitted
            resp = client.get("/api/centres?all=true", headers=auth_header())
            assert resp.status_code == 200
            assert len(resp.get_json()["centres"]) == 1

            # GET details of inactive centre returns 404 for farmer
            inactive_id = sample_centres[1].id
            resp2 = client.get(f"/api/centres/{inactive_id}", headers=auth_header())
            assert resp2.status_code == 404

    def test_unauthenticated_request_returns_401(self, client):
        resp = client.get("/api/centres")
        assert resp.status_code == 401


class TestCentreCreation:
    """Tests for POST /api/centres"""

    def test_admin_can_create_centre(self, client, admin_user):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            payload = {
                "name": "New Admin Centre",
                "location": "Rohtak",
                "district": "Rohtak",
                "tehsil": "Rohtak City",
                "opening_time": "08:00",
                "closing_time": "16:00",
                "daily_capacity": 150,
                "average_processing_minutes": 10,
            }
            resp = client.post("/api/centres", json=payload, headers=auth_header())
            assert resp.status_code == 201

            c = resp.get_json()["centre"]
            assert c["name"] == "New Admin Centre"
            assert c["district"] == "Rohtak"
            assert c["tehsil"] == "Rohtak City"
            assert c["is_active"] is True

    def test_farmer_cannot_create_centre(self, client, farmer_user):
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp = client.post("/api/centres", json={"name": "Illegal"}, headers=auth_header())
            assert resp.status_code == 403

    def test_staff_cannot_create_centre(self, client, staff_user):
        su = make_mock_user(user_id="staff-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            resp = client.post("/api/centres", json={"name": "Illegal"}, headers=auth_header())
            assert resp.status_code == 403

    def test_duplicate_centre_name_rejected(self, client, admin_user, sample_centres):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            payload = {
                "name": "Active Centre 1",  # Existing name
                "location": "Rohtak",
                "district": "Rohtak",
                "tehsil": "Rohtak City",
                "opening_time": "08:00",
                "closing_time": "16:00",
                "daily_capacity": 100,
                "average_processing_minutes": 10,
            }
            resp = client.post("/api/centres", json=payload, headers=auth_header())
            assert resp.status_code == 409
            assert "already exists" in resp.get_json()["message"]

    def test_invalid_operating_hours_rejected(self, client, admin_user):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            payload = {
                "name": "Bad Hours Centre",
                "location": "Hisar",
                "district": "Hisar",
                "tehsil": "Hisar City",
                "opening_time": "17:00",
                "closing_time": "09:00",  # Closing before opening
                "daily_capacity": 100,
                "average_processing_minutes": 10,
            }
            resp = client.post("/api/centres", json=payload, headers=auth_header())
            assert resp.status_code == 400
            assert "Opening time must be earlier than closing time." in resp.get_json()["messages"]

    def test_invalid_capacity_rejected(self, client, admin_user):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            payload = {
                "name": "Bad Cap Centre",
                "location": "Hisar",
                "district": "Hisar",
                "tehsil": "Hisar City",
                "opening_time": "09:00",
                "closing_time": "17:00",
                "daily_capacity": -5,  # Invalid
                "average_processing_minutes": 10,
            }
            resp = client.post("/api/centres", json=payload, headers=auth_header())
            assert resp.status_code == 400

    def test_invalid_processing_time_rejected(self, client, admin_user):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            payload = {
                "name": "Bad Proc Centre",
                "location": "Hisar",
                "district": "Hisar",
                "tehsil": "Hisar City",
                "opening_time": "09:00",
                "closing_time": "17:00",
                "daily_capacity": 50,
                "average_processing_minutes": 0,  # Invalid
            }
            resp = client.post("/api/centres", json=payload, headers=auth_header())
            assert resp.status_code == 400


class TestCentreUpdateAndDelete:
    """Tests for PUT /api/centres/<id> and DELETE /api/centres/<id>"""

    def test_admin_can_update_centre(self, client, admin_user, sample_centres):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            c_id = sample_centres[0].id
            resp = client.put(f"/api/centres/{c_id}", json={"daily_capacity": 300}, headers=auth_header())
            assert resp.status_code == 200
            assert resp.get_json()["centre"]["daily_capacity"] == 300

    def test_farmer_cannot_update_centre(self, client, farmer_user, sample_centres):
        su = make_mock_user(user_id="farmer-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            c_id = sample_centres[0].id
            resp = client.put(f"/api/centres/{c_id}", json={"daily_capacity": 300}, headers=auth_header())
            assert resp.status_code == 403

    def test_admin_can_deactivate_centre(self, client, app, admin_user, sample_centres):
        su = make_mock_user(user_id="admin-uuid-1")
        with patch("app.auth.service.get_supabase_client") as mock_gc:
            mock_client = MagicMock()
            mock_gc.return_value = mock_client
            mock_client.auth.get_user.return_value.user = su

            c_id = sample_centres[0].id
            resp = client.delete(f"/api/centres/{c_id}", headers=auth_header())
            assert resp.status_code == 200
            assert resp.get_json()["centre"]["is_active"] is False

            with app.app_context():
                c = db.session.get(Centre, c_id)
                assert c.is_active is False


class TestCentreLocationFields:
    """District/Tehsil management for farmer location eligibility.

    Covers:
    - A/B/C: admin create + edit of district/tehsil and read-back
    - Validation: required on create, non-empty on update, whitespace trimmed
    - H/I: STAFF and FARMER cannot modify centre location fields
    - J: legacy centres with NULL district/tehsil do not crash centre APIs
    """

    @staticmethod
    def _login(client, user):
        su = make_mock_user(user_id=user.supabase_user_id)
        patcher = patch("app.auth.service.get_supabase_client")
        mock_gc = patcher.start()
        mock_client = MagicMock()
        mock_gc.return_value = mock_client
        mock_client.auth.get_user.return_value.user = su
        return patcher

    @staticmethod
    def _base_payload(name):
        return {
            "name": name,
            "location": "Yard 1",
            "district": "Mirzapur",
            "tehsil": "Mirzapur Sadar",
            "opening_time": "08:00",
            "closing_time": "16:00",
            "daily_capacity": 50,
            "average_processing_minutes": 10,
        }

    # ---- A & C: admin creates with district + tehsil, values returned ----
    def test_admin_creates_centre_with_district_and_tehsil(self, client, admin_user):
        patcher = self._login(client, admin_user)
        try:
            payload = self._base_payload("Location Aware Centre")
            resp = client.post("/api/centres", json=payload, headers=auth_header())
            assert resp.status_code == 201, resp.get_json()
            centre = resp.get_json()["centre"]
            assert centre["district"] == "Mirzapur"
            assert centre["tehsil"] == "Mirzapur Sadar"

            # C: saved values are returned on read-back.
            fetched = client.get(f"/api/centres/{centre['id']}", headers=auth_header())
            assert fetched.status_code == 200
            body = fetched.get_json()["centre"]
            assert body["district"] == "Mirzapur"
            assert body["tehsil"] == "Mirzapur Sadar"
        finally:
            patcher.stop()

    def test_create_requires_district_and_tehsil(self, client, admin_user):
        patcher = self._login(client, admin_user)
        try:
            payload = self._base_payload("No Loc Centre")
            del payload["district"]
            del payload["tehsil"]
            resp = client.post("/api/centres", json=payload, headers=auth_header())
            assert resp.status_code == 400
            messages = resp.get_json()["messages"]
            assert "District is required." in messages
            assert "Tehsil is required." in messages
        finally:
            patcher.stop()

    def test_create_rejects_blank_district_and_tehsil(self, client, admin_user):
        patcher = self._login(client, admin_user)
        try:
            payload = self._base_payload("Blank Loc Centre")
            payload["district"] = "   "
            payload["tehsil"] = ""
            resp = client.post("/api/centres", json=payload, headers=auth_header())
            assert resp.status_code == 400
            messages = resp.get_json()["messages"]
            assert "District is required." in messages
            assert "Tehsil is required." in messages
        finally:
            patcher.stop()

    def test_create_trims_district_and_tehsil_whitespace(self, client, app, admin_user):
        patcher = self._login(client, admin_user)
        try:
            payload = self._base_payload("Trimmed Loc Centre")
            payload["district"] = "  Mirzapur \n"
            payload["tehsil"] = "\tMirzapur Sadar  "
            resp = client.post("/api/centres", json=payload, headers=auth_header())
            assert resp.status_code == 201, resp.get_json()
            centre = resp.get_json()["centre"]
            assert centre["district"] == "Mirzapur"
            assert centre["tehsil"] == "Mirzapur Sadar"
            with app.app_context():
                stored = db.session.get(Centre, centre["id"])
                assert stored.district == "Mirzapur"
                assert stored.tehsil == "Mirzapur Sadar"
        finally:
            patcher.stop()

    # ---- B & C: admin edits district + tehsil, values returned -----------
    def test_admin_edits_centre_district_and_tehsil(self, client, app, admin_user,
                                                    sample_centres):
        patcher = self._login(client, admin_user)
        try:
            c_id = sample_centres[0].id
            resp = client.put(
                f"/api/centres/{c_id}",
                json={"district": "  Panipat ", "tehsil": " Sanoli "},
                headers=auth_header(),
            )
            assert resp.status_code == 200, resp.get_json()
            centre = resp.get_json()["centre"]
            assert centre["district"] == "Panipat"
            assert centre["tehsil"] == "Sanoli"

            # C: persisted + returned on read-back.
            fetched = client.get(f"/api/centres/{c_id}", headers=auth_header())
            body = fetched.get_json()["centre"]
            assert body["district"] == "Panipat"
            assert body["tehsil"] == "Sanoli"
            with app.app_context():
                stored = db.session.get(Centre, c_id)
                assert stored.district == "Panipat"
                assert stored.tehsil == "Sanoli"
        finally:
            patcher.stop()

    def test_update_rejects_empty_district_or_tehsil(self, client, admin_user,
                                                     sample_centres):
        patcher = self._login(client, admin_user)
        try:
            c_id = sample_centres[0].id
            resp = client.put(
                f"/api/centres/{c_id}",
                json={"district": "", "tehsil": "   "},
                headers=auth_header(),
            )
            assert resp.status_code == 400
            messages = resp.get_json()["messages"]
            assert "District cannot be empty." in messages
            assert "Tehsil cannot be empty." in messages
        finally:
            patcher.stop()

    def test_omitted_location_keys_leave_values_unchanged(self, client, app,
                                                          admin_user, sample_centres):
        """Partial updates without district/tehsil keep the stored values."""
        patcher = self._login(client, admin_user)
        try:
            c_id = sample_centres[0].id
            resp = client.put(
                f"/api/centres/{c_id}",
                json={"daily_capacity": 321},
                headers=auth_header(),
            )
            assert resp.status_code == 200, resp.get_json()
            with app.app_context():
                stored = db.session.get(Centre, c_id)
                assert stored.daily_capacity == 321
                assert stored.district is None  # sample fixture leaves them NULL
                assert stored.tehsil is None
        finally:
            patcher.stop()

    # ---- H: STAFF cannot modify centre location fields -------------------
    def test_staff_cannot_modify_centre_location_fields(self, client, app, staff_user,
                                                        sample_centres):
        patcher = self._login(client, staff_user)
        try:
            c_id = sample_centres[0].id
            resp = client.put(
                f"/api/centres/{c_id}",
                json={"district": "Hacked", "tehsil": "Hacked"},
                headers=auth_header(),
            )
            assert resp.status_code == 403
            with app.app_context():
                stored = db.session.get(Centre, c_id)
                assert stored.district is None
                assert stored.tehsil is None
        finally:
            patcher.stop()

    def test_staff_cannot_create_centre_with_location_fields(self, client, staff_user):
        patcher = self._login(client, staff_user)
        try:
            payload = self._base_payload("Staff Illegal Centre")
            resp = client.post("/api/centres", json=payload, headers=auth_header())
            assert resp.status_code == 403
        finally:
            patcher.stop()

    # ---- I: FARMER cannot modify centre location fields ------------------
    def test_farmer_cannot_modify_centre_location_fields(self, client, app, farmer_user,
                                                         sample_centres):
        patcher = self._login(client, farmer_user)
        try:
            c_id = sample_centres[0].id
            resp = client.put(
                f"/api/centres/{c_id}",
                json={"district": "Hacked", "tehsil": "Hacked"},
                headers=auth_header(),
            )
            assert resp.status_code == 403
            with app.app_context():
                stored = db.session.get(Centre, c_id)
                assert stored.district is None
                assert stored.tehsil is None
        finally:
            patcher.stop()

    def test_farmer_cannot_create_centre_with_location_fields(self, client, farmer_user):
        patcher = self._login(client, farmer_user)
        try:
            payload = self._base_payload("Farmer Illegal Centre")
            resp = client.post("/api/centres", json=payload, headers=auth_header())
            assert resp.status_code == 403
        finally:
            patcher.stop()

    # ---- J: legacy NULL location records never crash centre APIs ---------
    def test_legacy_null_location_centre_does_not_crash_apis(self, client, app,
                                                             admin_user, farmer_user,
                                                             sample_centres):
        """sample_centres have NULL district/tehsil (legacy production shape)."""
        patcher = self._login(client, admin_user)
        try:
            # Admin list (includes the inactive legacy row too).
            resp = client.get("/api/centres?all=true", headers=auth_header())
            assert resp.status_code == 200
            rows = resp.get_json()["centres"]
            assert len(rows) >= 2
            legacy = next(r for r in rows if r["name"] == "Inactive Centre 2")
            assert legacy["district"] is None
            assert legacy["tehsil"] is None

            # Admin detail view of a NULL-location centre.
            detail = client.get(f"/api/centres/{sample_centres[0].id}",
                                headers=auth_header())
            assert detail.status_code == 200
            assert detail.get_json()["centre"]["district"] is None
        finally:
            patcher.stop()

        # Public centre list must serialise NULL fields without crashing.
        pub = client.get("/api/public/centres")
        assert pub.status_code == 200
        pub_rows = pub.get_json()["centres"]
        assert all("district" in r and "tehsil" in r for r in pub_rows)

        # Authenticated farmer-facing list also works.
        patcher = self._login(client, farmer_user)
        try:
            resp = client.get("/api/centres", headers=auth_header())
            assert resp.status_code == 200
            assert all("district" in r for r in resp.get_json()["centres"])
        finally:
            patcher.stop()

