"""Regression tests for the Admin Management initial-data-load bug.

The inline ``<script>`` in ``app/templates/admin_management.html`` used to sit
*between* the external ``auth.js`` include and the Delay/Staff modals.  Because
``delayForm`` and ``staffForm`` were defined *after* the script, these top-level
statements threw ``TypeError: ... null ... addEventListener`` and aborted the
whole inline script::

    document.getElementById("delayForm").addEventListener("submit", ...)
    document.getElementById("staffForm").addEventListener("submit", ...)

So ``DOMContentLoaded`` (calling ``loadCentres()``/``loadCrops()``) was never
registered and the tables stayed on "Loading ..." forever.

Fix: the inline ``<script>`` now lives immediately before ``</body>`` (after
every modal/form), and ``loadCentres``/``loadCrops`` render a visible error on
failure.  These tests guard the script/DOM ordering that caused the bug.  The
Flask test client has no JS runtime, so initial-load behaviour is verified by
asserting the JS is wired to the correct API endpoints and those endpoints serve
the seeded data.
"""
import pytest
from datetime import time
from unittest.mock import MagicMock, patch

from app.extensions import db
from app.models import User, UserRole, Centre, Crop, Staff


def _html(client):
    resp = client.get("/admin/management")
    assert resp.status_code == 200, resp.status_code
    return resp.data.decode("utf-8")


def _inline_script_open_index(html):
    """Index of the bare (no-src) ``<script>`` opening the showAlert block.

    ``<script src=...>`` never contains the bare substring ``<script>``, so
    matching the ``<script>`` that precedes ``function showAlert`` uniquely
    identifies the inline block regardless of its document position.
    """
    show = html.find("function showAlert")
    assert show != -1, "inline script (showAlert) missing from page"
    open_idx = html.rfind("<script>", 0, show)
    assert open_idx != -1, "inline <script> tag missing"
    assert html[open_idx:open_idx + 8] == "<script>", "matched tag carried a src attribute"
    return open_idx


def _first_function_body(html, func_decl):
    """Source slice from a function declaration to its first ``} catch``."""
    start = html.find(func_decl)
    assert start != -1, f"{func_decl!r} not found"
    nxt = html.find("} catch", start)
    return html[start: nxt if nxt != -1 else start + 1000]


class TestAdminManagementScriptOrdering:
    """The inline <script> must execute AFTER all modal/form markup."""

    def test_page_loads(self, client):
        assert client.get("/admin/management").status_code == 200

    def test_script_after_delay_modal_markup(self, client):
        """delayForm used to live AFTER the script -> null deref -> abort."""
        html = _html(client)
        form_idx = html.find('id="delayForm"')
        script_idx = _inline_script_open_index(html)
        assert form_idx != -1, "delayForm markup missing"
        assert form_idx < script_idx, \
            "delayForm markup must appear BEFORE the inline script (root cause)"

    def test_script_after_staff_modal_markup(self, client):
        html = _html(client)
        form_idx = html.find('id="staffForm"')
        script_idx = _inline_script_open_index(html)
        assert form_idx != -1, "staffForm markup missing"
        assert form_idx < script_idx, \
            "staffForm markup must appear BEFORE the inline script (root cause)"

    def test_script_between_modals_and_body_close(self, client):
        html = _html(client)
        script_idx = _inline_script_open_index(html)
        script_close = html.find("</script>", script_idx)
        body_close = html.rfind("</body>")
        assert script_close != -1 and body_close != -1
        assert script_idx < script_close < body_close, \
            "inline script must open and close before </body>"

    def test_no_top_level_delay_or_staff_form_null_dereference(self, client):
        """The addEventListener access must come AFTER its form markup in source
        order -- the precise regression guard: if the script were moved above
        the modals again, this assertion would flip and fail.
        """
        html = _html(client)
        for form in ("delayForm", "staffForm"):
            form_idx = html.find(f'id="{form}"')
            handler_idx = html.find(f'getElementById("{form}")')
            assert form_idx != -1, f"{form} markup missing"
            assert handler_idx != -1, f"{form} submit handler missing"
            assert form_idx < handler_idx, \
                f"{form} is accessed before its markup exists in source order"


class TestAdminManagementInitialLoad:
    """The page must bootstrap centres/crops on first paint (no user action)."""

    def test_domcontentloaded_calls_load_centres_and_crops(self, client):
        html = _html(client)
        dcl = html.find('document.addEventListener("DOMContentLoaded"')
        assert dcl != -1, "DOMContentLoaded init handler missing"
        handler = html[dcl:dcl + 400]
        assert "loadCentres()" in handler
        assert "loadCrops()" in handler

    def test_loadcentres_fetches_centres_endpoint(self, client):
        html = _html(client)
        assert "/api/centres?all=true" in _first_function_body(html, "async function loadCentres")

    def test_loadcrops_fetches_crops_endpoint(self, client):
        html = _html(client)
        assert "/api/crops?all=true" in _first_function_body(html, "async function loadCrops")

    def test_initial_load_placeholders_have_render_targets(self, client):
        html = _html(client)
        for tb in ("centresTableBody", "cropsTableBody", "staffTableBody"):
            assert f'id="{tb}"' in html


class TestAdminManagementFormHandlers:
    """All four submit handlers must still be registered."""

    def test_centre_form_handler_registered(self, client):
        assert 'getElementById("centreForm").addEventListener' in _html(client)

    def test_crop_form_handler_registered(self, client):
        assert 'getElementById("cropForm").addEventListener' in _html(client)

    def test_delay_form_handler_registered(self, client):
        assert 'getElementById("delayForm").addEventListener' in _html(client)

    def test_staff_form_handler_registered(self, client):
        assert 'getElementById("staffForm").addEventListener' in _html(client)

    def test_load_errors_visible_on_failure(self, client):
        """Hardening: an API failure must render a visible error, not 'Loading...'."""
        html = _html(client)
        assert "Unable to load centres" in html
        assert "Unable to load crops" in html


# --- behavioural backend tests for the initial-load data path ---------------
# The Flask test client has no JS runtime, so the "initial load" is verified
# here by calling the exact API endpoints the relocated script calls on first
# paint and confirming they serve the seeded data.

def auth_header(token="valid-token"):
    return {"Authorization": f"Bearer {token}"}


def make_auth_call(client, method, url, sub_id, json_data=None):
    with patch("app.auth.decorators.verify_token") as mock_vt:
        mock_user = MagicMock()
        mock_user.id = sub_id
        mock_vt.return_value = mock_user
        kwargs = {"headers": auth_header()}
        if json_data is not None:
            kwargs["json"] = json_data
        if method == "GET":
            return client.get(url, **kwargs)
        elif method == "POST":
            return client.post(url, **kwargs)
        elif method == "PUT":
            return client.put(url, **kwargs)
        elif method == "DELETE":
            return client.delete(url, **kwargs)
        raise ValueError(f"Unsupported method: {method}")


@pytest.fixture
def admin_user(app):
    with app.app_context():
        u = User(supabase_user_id="admin-sub-1", role=UserRole.ADMIN, is_active=True)
        db.session.add(u)
        db.session.commit()
        yield u


@pytest.fixture
def centre_a(app):
    with app.app_context():
        c = Centre(name="Centre Alpha", location="Location A",
                   opening_time=time(9, 0), closing_time=time(17, 0),
                   daily_capacity=100, average_processing_minutes=15, is_active=True)
        db.session.add(c)
        db.session.commit()
        yield c


@pytest.fixture
def crop_wheat(app):
    with app.app_context():
        c = Crop(name="Wheat", category="Cereal", is_active=True)
        db.session.add(c)
        db.session.commit()
        yield c


@pytest.fixture
def staff_alpha(app, centre_a):
    with app.app_context():
        u = User(supabase_user_id="staff-alpha-sub", role=UserRole.STAFF, is_active=True)
        db.session.add(u)
        db.session.flush()
        s = Staff(user_id=u.id, name="Staff Alpha", phone="9000000011", centre_id=centre_a.id)
        db.session.add(s)
        db.session.commit()
        yield s


class TestAdminManagementBackendInitialLoad:
    """Verify the data the initial-load JS depends on is actually served.

    loadCentres() -> GET /api/centres?all=true
    loadCrops()   -> GET /api/crops?all=true
    loadStaff()   -> GET /api/admin/staff
    """

    def test_initial_load_centres_endpoint_returns_seeded_centre(
        self, client, admin_user, centre_a
    ):
        resp = make_auth_call(client, "GET", "/api/centres?all=true", "admin-sub-1")
        assert resp.status_code == 200
        names = [c["name"] for c in resp.get_json()["centres"]]
        assert "Centre Alpha" in names

    def test_initial_load_crops_endpoint_returns_seeded_crop(
        self, client, admin_user, crop_wheat
    ):
        resp = make_auth_call(client, "GET", "/api/crops?all=true", "admin-sub-1")
        assert resp.status_code == 200
        names = [c["name"] for c in resp.get_json()["crops"]]
        assert "Wheat" in names

    def test_initial_load_staff_endpoint_returns_assigned_centre_name(
        self, client, admin_user, staff_alpha, centre_a
    ):
        """loadStaff() renders s.centre_name; the API must serve it (Staff row
        displays the assigned Centre)."""
        resp = make_auth_call(client, "GET", "/api/admin/staff", "admin-sub-1")
        assert resp.status_code == 200
        row = next(s for s in resp.get_json()["staff"] if s["name"] == "Staff Alpha")
        assert row["centre_id"] == centre_a.id
        assert row["centre_name"] == "Centre Alpha"
