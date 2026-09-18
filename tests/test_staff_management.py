"""
Comprehensive test suite for Admin Staff Assignment + Centre Isolation.
"""

import pytest
from datetime import date, time, timedelta
from unittest.mock import MagicMock, patch

from app.extensions import db
from app.models import (
    User, UserRole, Farmer, Staff, Centre, Crop, Slot, SlotStatus,
    Booking, BookingStatus, Delay, DelayStatus,
)


def auth_header(token="valid-token"):
    return {"Authorization": f"Bearer {token}"}


def make_auth_call(client, method, url, sub_id, json_data=None):
    with patch("app.auth.decorators.verify_token") as mock_vt:
        mock_user = MagicMock()
        mock_user.id = sub_id
        mock_user.email = f"{sub_id}@example.com"
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
def farmer_user(app):
    with app.app_context():
        u = User(supabase_user_id="farmer-sub-1", role=UserRole.FARMER, is_active=True)
        db.session.add(u)
        db.session.flush()
        f = Farmer(user_id=u.id, name="Test Farmer", phone="9000000001")
        db.session.add(f)
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
def centre_b(app):
    with app.app_context():
        c = Centre(name="Centre Beta", location="Location B",
                   opening_time=time(9, 0), closing_time=time(17, 0),
                   daily_capacity=100, average_processing_minutes=20, is_active=True)
        db.session.add(c)
        db.session.commit()
        yield c


@pytest.fixture
def staff_a(app, centre_a):
    with app.app_context():
        u = User(supabase_user_id="staff-a-sub", role=UserRole.STAFF, is_active=True)
        db.session.add(u)
        db.session.flush()
        s = Staff(user_id=u.id, name="Staff Alpha", phone="9000000011", centre_id=centre_a.id)
        db.session.add(s)
        db.session.commit()
        yield s


@pytest.fixture
def staff_b(app, centre_b):
    with app.app_context():
        u = User(supabase_user_id="staff-b-sub", role=UserRole.STAFF, is_active=True)
        db.session.add(u)
        db.session.flush()
        s = Staff(user_id=u.id, name="Staff Beta", phone="9000000022", centre_id=centre_b.id)
        db.session.add(s)
        db.session.commit()
        yield s


@pytest.fixture
def unassigned_staff(app):
    with app.app_context():
        u = User(supabase_user_id="staff-unassigned-sub", role=UserRole.STAFF, is_active=True)
        db.session.add(u)
        db.session.flush()
        s = Staff(user_id=u.id, name="Unassigned Staff", phone="9000000033", centre_id=None)
        db.session.add(s)
        db.session.commit()
        yield s


@pytest.fixture
def crop_wheat(app):
    with app.app_context():
        c = Crop(name="Wheat", category="Cereal", is_active=True)
        db.session.add(c)
        db.session.commit()
        yield c


@pytest.fixture
def mock_supabase():
    mock_client = MagicMock()
    mock_client.auth = MagicMock()
    with patch("app.auth.service.get_supabase_client", return_value=mock_client):
        yield mock_client


# === 1. STAFF MANAGEMENT ===

class TestStaffManagement:

    def test_admin_can_list_staff(self, client, admin_user, staff_a, staff_b):
        """1. ADMIN can list staff -> 200."""
        res = make_auth_call(client, "GET", "/api/admin/staff", "admin-sub-1")
        assert res.status_code == 200
        data = res.get_json()
        assert "staff" in data
        assert len(data["staff"]) >= 2

    def test_admin_can_provision_staff(self, client, admin_user, centre_a, mock_supabase):
        """2. ADMIN can create/provision staff -> 201."""
        new_user = MagicMock()
        new_user.id = "new-staff-uuid"
        mock_response = MagicMock()
        mock_response.user = new_user
        mock_supabase.auth.sign_up.return_value = mock_response
        payload = {"email": "newstaff@example.com", "name": "New Staff",
                   "phone": "9111111111", "centre_id": centre_a.id}
        res = make_auth_call(client, "POST", "/api/admin/staff", "admin-sub-1", payload)
        assert res.status_code == 201
        assert res.get_json()["staff"]["name"] == "New Staff"
        assert res.get_json()["staff"]["centre_id"] == centre_a.id

    def test_admin_can_assign_staff_to_centre(self, client, admin_user, unassigned_staff, centre_b):
        """3. ADMIN can assign staff to centre -> 200."""
        res = make_auth_call(client, "PUT", f"/api/admin/staff/{unassigned_staff.id}",
                             "admin-sub-1", {"centre_id": centre_b.id})
        assert res.status_code == 200
        assert res.get_json()["staff"]["centre_id"] == centre_b.id

    def test_admin_can_change_staff_centre(self, client, admin_user, staff_a, centre_b):
        """4. ADMIN can change staff centre -> 200."""
        res = make_auth_call(client, "PUT", f"/api/admin/staff/{staff_a.id}",
                             "admin-sub-1", {"centre_id": centre_b.id})
        assert res.status_code == 200
        assert res.get_json()["staff"]["centre_id"] == centre_b.id

    def test_admin_can_deactivate_staff(self, client, admin_user, staff_a):
        """5. ADMIN can deactivate staff -> 200."""
        res = make_auth_call(client, "DELETE", f"/api/admin/staff/{staff_a.id}", "admin-sub-1")
        assert res.status_code == 200
        assert res.get_json()["staff"]["is_active"] is False

    def test_farmer_cannot_manage_staff(self, client, farmer_user, staff_a):
        """6. FARMER cannot manage staff -> 403."""
        assert make_auth_call(client, "GET", "/api/admin/staff", "farmer-sub-1").status_code == 403
        assert make_auth_call(client, "POST", "/api/admin/staff", "farmer-sub-1",
                              {"email": "x@y.com", "name": "X"}).status_code == 403
        assert make_auth_call(client, "PUT", f"/api/admin/staff/{staff_a.id}", "farmer-sub-1",
                              {"name": "H"}).status_code == 403
        assert make_auth_call(client, "DELETE", f"/api/admin/staff/{staff_a.id}",
                              "farmer-sub-1").status_code == 403

    def test_staff_cannot_manage_staff(self, client, staff_a, staff_b):
        """7. STAFF cannot manage staff -> 403."""
        assert make_auth_call(client, "GET", "/api/admin/staff", "staff-a-sub").status_code == 403
        assert make_auth_call(client, "POST", "/api/admin/staff", "staff-a-sub",
                              {"email": "x@y.com", "name": "X"}).status_code == 403
        assert make_auth_call(client, "PUT", f"/api/admin/staff/{staff_b.id}", "staff-a-sub",
                              {"name": "H"}).status_code == 403
        assert make_auth_call(client, "DELETE", f"/api/admin/staff/{staff_b.id}",
                              "staff-a-sub").status_code == 403

# === 2. CENTRE ISOLATION - SLOTS ===

class TestCentreIsolationSlots:

    @pytest.fixture
    def slot_info(self, centre_a, centre_b, crop_wheat):
        return {"a": centre_a.id, "b": centre_b.id, "crop": crop_wheat.id,
                "date": (date.today() + timedelta(days=1)).isoformat()}

    def test_staff_a_can_create_slot_at_centre_a(self, client, staff_a, slot_info):
        """8. Staff A can create slot at Centre A."""
        p = {"centre_id": slot_info["a"], "crop_id": slot_info["crop"],
             "slot_date": slot_info["date"], "start_time": "09:00", "end_time": "10:00", "capacity": 10}
        assert make_auth_call(client, "POST", "/api/slots", "staff-a-sub", p).status_code == 201

    def test_staff_a_cannot_create_slot_at_centre_b(self, client, staff_a, slot_info):
        """9. Staff A cannot create slot at Centre B -> 403."""
        p = {"centre_id": slot_info["b"], "crop_id": slot_info["crop"],
             "slot_date": slot_info["date"], "start_time": "09:00", "end_time": "10:00", "capacity": 10}
        res = make_auth_call(client, "POST", "/api/slots", "staff-a-sub", p)
        assert res.status_code == 403
        assert "Access denied" in res.get_json()["message"]

    def test_staff_a_cannot_update_centre_b_slot(self, client, centre_b, crop_wheat, staff_a, app):
        """10. Staff A cannot update Centre B slot -> 403."""
        with app.app_context():
            slot = Slot(centre_id=centre_b.id, crop_id=crop_wheat.id,
                        slot_date=date.today() + timedelta(days=1),
                        start_time=time(9, 0), end_time=time(10, 0),
                        capacity=10, status=SlotStatus.OPEN)
            db.session.add(slot)
            db.session.commit()
            sid = slot.id
        assert make_auth_call(client, "PUT", f"/api/slots/{sid}", "staff-a-sub",
                              {"capacity": 20}).status_code == 403

    def test_staff_a_cannot_cancel_centre_b_slot(self, client, centre_b, crop_wheat, staff_a, app):
        """11. Staff A cannot cancel Centre B slot -> 403."""
        with app.app_context():
            slot = Slot(centre_id=centre_b.id, crop_id=crop_wheat.id,
                        slot_date=date.today() + timedelta(days=1),
                        start_time=time(11, 0), end_time=time(12, 0),
                        capacity=10, status=SlotStatus.OPEN)
            db.session.add(slot)
            db.session.commit()
            sid = slot.id
        assert make_auth_call(client, "DELETE", f"/api/slots/{sid}", "staff-a-sub").status_code == 403


# === 3. CENTRE ISOLATION - QUEUE ===

class TestCentreIsolationQueue:

    def test_staff_a_can_view_centre_a_queue(self, client, staff_a, centre_a):
        """12. Staff A can view Centre A queue."""
        assert make_auth_call(client, "GET", f"/api/queue/centre/{centre_a.id}",
                              "staff-a-sub").status_code == 200

    def test_staff_a_cannot_view_centre_b_queue(self, client, staff_a, centre_b):
        """13. Staff A cannot view Centre B queue -> 403."""
        res = make_auth_call(client, "GET", f"/api/queue/centre/{centre_b.id}", "staff-a-sub")
        assert res.status_code == 403
        assert "Access denied" in res.get_json()["message"]


# === 4. CENTRE ISOLATION - DELAYS ===

class TestCentreIsolationDelays:

    def test_staff_a_cannot_create_delay_for_centre_b(self, client, staff_a, centre_b):
        """14. Staff A cannot create delay for Centre B -> 403."""
        p = {"centre_id": centre_b.id, "delay_date": date.today().isoformat(), "delay_minutes": 30}
        assert make_auth_call(client, "POST", "/api/delays", "staff-a-sub", p).status_code == 403

    def test_staff_a_cannot_update_centre_b_delay(self, client, centre_b, staff_a, app):
        """15. Staff A cannot update/cancel Centre B delay -> 403."""
        with app.app_context():
            delay = Delay(centre_id=centre_b.id, delay_date=date.today() + timedelta(days=1),
                          delay_minutes=30, status=DelayStatus.ACTIVE)
            db.session.add(delay)
            db.session.commit()
            did = delay.id
        assert make_auth_call(client, "PUT", f"/api/delays/{did}", "staff-a-sub",
                              {"delay_minutes": 60}).status_code == 403
        assert make_auth_call(client, "DELETE", f"/api/delays/{did}", "staff-a-sub").status_code == 403

# === 5. CENTRE ISOLATION - PROCUREMENT ===

class TestCentreIsolationProcurement:

    @pytest.fixture
    def centre_b_booking_id(self, app, centre_b, crop_wheat, farmer_user):
        with app.app_context():
            farmer = Farmer.query.filter_by(user_id=farmer_user.id).first()
            if not farmer:
                farmer = Farmer(user_id=farmer_user.id, name="FB", phone="9000000099")
                db.session.add(farmer)
                db.session.flush()
            slot = Slot(centre_id=centre_b.id, crop_id=crop_wheat.id,
                        slot_date=date.today() + timedelta(days=1),
                        start_time=time(9, 0), end_time=time(10, 0),
                        capacity=10, status=SlotStatus.OPEN)
            db.session.add(slot)
            db.session.flush()
            booking = Booking(farmer_id=farmer.id, slot_id=slot.id,
                              status=BookingStatus.CONFIRMED, token_number="K-0099")
            db.session.add(booking)
            db.session.commit()
            return booking.id

    def test_staff_a_cannot_access_centre_b_procurement(self, client, staff_a, centre_b_booking_id):
        """16. Staff A cannot access Centre B procurement -> 403."""
        assert make_auth_call(client, "GET", f"/api/procurement/{centre_b_booking_id}",
                              "staff-a-sub").status_code == 403

    def test_staff_a_cannot_modify_centre_b_procurement(self, client, staff_a, centre_b_booking_id):
        """17. Staff A cannot modify Centre B procurement -> 403."""
        assert make_auth_call(client, "POST", f"/api/procurement/{centre_b_booking_id}",
                              "staff-a-sub", {"procurement_status": "IN_PROGRESS"}).status_code == 403
        assert make_auth_call(client, "PUT", f"/api/procurement/{centre_b_booking_id}",
                              "staff-a-sub", {"procurement_status": "COMPLETED"}).status_code == 403


# === 6. CENTRE ISOLATION - PAYMENT ===

class TestCentreIsolationPayment:

    @pytest.fixture
    def centre_b_booking_id(self, app, centre_b, crop_wheat, farmer_user):
        with app.app_context():
            farmer = Farmer.query.filter_by(user_id=farmer_user.id).first()
            if not farmer:
                farmer = Farmer(user_id=farmer_user.id, name="FB2", phone="9000000088")
                db.session.add(farmer)
                db.session.flush()
            slot = Slot(centre_id=centre_b.id, crop_id=crop_wheat.id,
                        slot_date=date.today() + timedelta(days=1),
                        start_time=time(9, 0), end_time=time(10, 0),
                        capacity=10, status=SlotStatus.OPEN)
            db.session.add(slot)
            db.session.flush()
            booking = Booking(farmer_id=farmer.id, slot_id=slot.id,
                              status=BookingStatus.CONFIRMED, token_number="K-0088")
            db.session.add(booking)
            db.session.commit()
            return booking.id

    def test_staff_a_cannot_access_centre_b_payment(self, client, staff_a, centre_b_booking_id):
        """18. Staff A cannot access Centre B payment -> 403."""
        assert make_auth_call(client, "GET", f"/api/payment/{centre_b_booking_id}",
                              "staff-a-sub").status_code == 403

    def test_staff_a_cannot_modify_centre_b_payment(self, client, staff_a, centre_b_booking_id):
        """19. Staff A cannot modify Centre B payment -> 403."""
        assert make_auth_call(client, "POST", f"/api/payment/{centre_b_booking_id}",
                              "staff-a-sub", {"payment_status": "PROCESSING"}).status_code == 403
        assert make_auth_call(client, "PUT", f"/api/payment/{centre_b_booking_id}",
                              "staff-a-sub", {"payment_status": "PAID"}).status_code == 403

# === 7. ADMIN BYPASS ===

class TestAdminBypass:

    def test_admin_can_access_centre_a(self, client, admin_user, centre_a):
        """20. ADMIN can access Centre A."""
        assert make_auth_call(client, "GET", f"/api/queue/centre/{centre_a.id}",
                              "admin-sub-1").status_code == 200

    def test_admin_can_access_centre_b(self, client, admin_user, centre_b):
        """21. ADMIN can access Centre B."""
        assert make_auth_call(client, "GET", f"/api/queue/centre/{centre_b.id}",
                              "admin-sub-1").status_code == 200

    def test_admin_can_manage_slots_in_both(self, client, admin_user, centre_a, centre_b, crop_wheat):
        """22. ADMIN can manage slots in both centres."""
        d = (date.today() + timedelta(days=1)).isoformat()
        pa = {"centre_id": centre_a.id, "crop_id": crop_wheat.id, "slot_date": d,
              "start_time": "09:00", "end_time": "10:00", "capacity": 10}
        pb = {"centre_id": centre_b.id, "crop_id": crop_wheat.id, "slot_date": d,
              "start_time": "09:00", "end_time": "10:00", "capacity": 10}
        assert make_auth_call(client, "POST", "/api/slots", "admin-sub-1", pa).status_code == 201
        assert make_auth_call(client, "POST", "/api/slots", "admin-sub-1", pb).status_code == 201

    def test_admin_can_manage_delays_in_both(self, client, admin_user, centre_a, centre_b):
        """23. ADMIN can manage delays in both centres."""
        pa = {"centre_id": centre_a.id, "delay_date": date.today().isoformat(), "delay_minutes": 15}
        pb = {"centre_id": centre_b.id, "delay_date": date.today().isoformat(), "delay_minutes": 20}
        assert make_auth_call(client, "POST", "/api/delays", "admin-sub-1", pa).status_code == 201
        assert make_auth_call(client, "POST", "/api/delays", "admin-sub-1", pb).status_code == 201

    def test_admin_can_manage_procurement_across_centres(self, client, admin_user, app,
                                                        centre_a, crop_wheat, farmer_user):
        """24. ADMIN can manage procurement/payment across centres."""
        with app.app_context():
            farmer = Farmer.query.filter_by(user_id=farmer_user.id).first()
            if not farmer:
                farmer = Farmer(user_id=farmer_user.id, name="ADM", phone="9000000077")
                db.session.add(farmer)
                db.session.flush()
            slot = Slot(centre_id=centre_a.id, crop_id=crop_wheat.id,
                        slot_date=date.today() + timedelta(days=2),
                        start_time=time(9, 0), end_time=time(10, 0),
                        capacity=10, status=SlotStatus.OPEN)
            db.session.add(slot)
            db.session.flush()
            booking = Booking(farmer_id=farmer.id, slot_id=slot.id,
                              status=BookingStatus.CONFIRMED, token_number="K-0077")
            db.session.add(booking)
            db.session.commit()
            bid = booking.id
        assert make_auth_call(client, "GET", f"/api/procurement/{bid}", "admin-sub-1").status_code == 200
        assert make_auth_call(client, "POST", f"/api/procurement/{bid}", "admin-sub-1",
                              {"procurement_status": "IN_PROGRESS"}).status_code == 201
        assert make_auth_call(client, "GET", f"/api/payment/{bid}", "admin-sub-1").status_code == 200
        assert make_auth_call(client, "POST", f"/api/payment/{bid}", "admin-sub-1",
                              {"payment_status": "PROCESSING"}).status_code == 201


# === 8. UNASSIGNED STAFF ===

class TestUnassignedStaff:

    def test_unassigned_staff_cannot_perform_centre_operations(self, client, unassigned_staff,
                                                               centre_a, crop_wheat):
        """25. STAFF with centre_id=None cannot perform centre operations -> 403."""
        d = (date.today() + timedelta(days=1)).isoformat()
        p = {"centre_id": centre_a.id, "crop_id": crop_wheat.id, "slot_date": d,
             "start_time": "09:00", "end_time": "10:00", "capacity": 10}
        assert make_auth_call(client, "POST", "/api/slots", "staff-unassigned-sub", p).status_code == 403
        assert make_auth_call(client, "GET", f"/api/queue/centre/{centre_a.id}",
                              "staff-unassigned-sub").status_code == 403
        p = {"centre_id": centre_a.id, "delay_date": date.today().isoformat(), "delay_minutes": 30}
        res = make_auth_call(client, "POST", "/api/delays", "staff-unassigned-sub", p)
        assert res.status_code == 403
        msg = res.get_json()["message"].lower()
        assert "contact the administrator" in msg or "not been assigned" in msg
        msg = res.get_json()["message"].lower()
        assert "contact the administrator" in msg or "not been assigned" in msg


# === 9. STAFF DASHBOARD (PUBLIC HTML SHELL) & AUTH REGRESSION TESTS ===

class TestStaffDashboard:
    """/staff/dashboard is a PUBLIC HTML page shell, exactly like the Farmer and
    Admin dashboard shells in app/routes/main.py.

    The shell embeds NO staff/centre/queue/session data: the page authenticates
    through window.KP.authFetch() (shared auth.js helper) and loads everything
    from the authenticated JSON APIs, where STAFF role authorization and centre
    isolation stay enforced.
    """

    # --- 1-4: the page shell itself -----------------------------------------

    def test_staff_dashboard_browser_navigation(self, client):
        """1. Plain browser navigation (no Authorization header) gets the page."""
        resp = client.get("/staff/dashboard")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_staff_dashboard_is_the_staff_html_shell(self, client):
        """2. The response is the staff dashboard HTML shell."""
        html = client.get("/staff/dashboard").get_data(as_text=True)
        assert "<!DOCTYPE html>" in html
        assert "KisanProcure Staff" in html
        assert "Staff Panel" in html
        assert 'id="assignedCentreContainer"' in html
        assert 'id="unassignedCentreContainer"' in html
        # Client-side-only controls: queue date selector + QR scanner section.
        assert 'id="queueDate"' in html
        assert "Smart Queue Pass Scanner" in html
        assert "initStaffDashboard" in html

    def test_staff_dashboard_shell_uses_auth_js_and_auth_fetch(self, client):
        """3. The shell carries the existing auth.js / authFetch mechanism."""
        html = client.get("/staff/dashboard").get_data(as_text=True)
        assert "/static/js/auth.js" in html
        assert "window.KP.authFetch" in html
        # An unauthenticated browser session is bounced to login client-side.
        assert "/login?next=/staff/dashboard" in html

    def test_staff_dashboard_shell_embeds_no_server_side_staff_data(
        self, client, staff_a, centre_a
    ):
        """4. No staff/centre identity or session material is rendered.

        The fixtures insert a real assigned STAFF and centre, so these
        assertions prove the route renders none of that server-side.
        """
        html = client.get("/staff/dashboard").get_data(as_text=True)
        assert staff_a.name not in html       # "Staff Alpha"
        assert staff_a.phone not in html      # "9000000011"
        assert centre_a.name not in html      # "Centre Alpha"
        assert centre_a.location not in html  # "Location A"
        assert "eyJ" not in html              # no JWT header prefix
        assert "kp_access_token" not in html  # no token material

    def test_assigned_staff_dashboard_loads_template(self, client, staff_a):
        """The same public shell loads for an assigned STAFF as well."""
        resp = make_auth_call(client, "GET", "/staff/dashboard", "staff-a-sub")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "KisanProcure Staff" in html

    # --- 5-9: the protected APIs are untouched ------------------------------

    def test_protected_staff_apis_still_require_authentication(self, client, centre_a):
        """5. Opening the page shell opens no staff API: they all answer 401."""
        assert client.get("/api/auth/me").status_code == 401
        assert client.get(f"/api/queue/centre/{centre_a.id}").status_code == 401
        assert client.get("/api/delays").status_code == 401
        assert client.post("/api/delays", json={
            "centre_id": centre_a.id,
            "delay_date": date.today().isoformat(),
            "delay_minutes": 30,
        }).status_code == 401
        assert client.get("/api/procurement/1").status_code == 401
        assert client.get("/api/payment/1").status_code == 401

    def test_staff_role_authorization_enforced_on_protected_apis(
        self, client, farmer_user, centre_a
    ):
        """6. A FARMER is still refused by every protected STAFF API -> 403."""
        assert make_auth_call(client, "GET", f"/api/queue/centre/{centre_a.id}",
                              "farmer-sub-1").status_code == 403
        assert make_auth_call(client, "POST", "/api/delays", "farmer-sub-1",
                              {"centre_id": centre_a.id,
                               "delay_date": date.today().isoformat(),
                               "delay_minutes": 30}).status_code == 403

    def test_staff_centre_isolation_enforced_on_protected_apis(
        self, client, staff_a, centre_b
    ):
        """7. Staff A still cannot reach Centre B operations -> 403."""
        assert make_auth_call(client, "GET", f"/api/queue/centre/{centre_b.id}",
                              "staff-a-sub").status_code == 403

    def test_unassigned_staff_shell_loads_but_apis_stay_403(
        self, client, unassigned_staff, centre_a
    ):
        """8. Unassigned STAFF gets the public shell; centre APIs keep the 403."""
        assert client.get("/staff/dashboard").status_code == 200
        assert make_auth_call(client, "GET", f"/api/queue/centre/{centre_a.id}",
                              "staff-unassigned-sub").status_code == 403
        res = make_auth_call(client, "POST", "/api/delays", "staff-unassigned-sub",
                             {"centre_id": centre_a.id,
                              "delay_date": date.today().isoformat(),
                              "delay_minutes": 30})
        assert res.status_code == 403
        msg = res.get_json()["message"].lower()
        assert "contact the administrator" in msg or "not been assigned" in msg

    def test_qr_scanner_endpoint_remains_protected(self, client):
        """9. The QR scanner API is never public, even though its page is."""
        assert client.post(
            "/api/queue-pass/verify",
            json={"pass_id": "kp_pass_not_a_real_id"},
        ).status_code == 401
        assert client.get(
            "/api/queue-pass/lookup/kp_pass_not_a_real_id"
        ).status_code == 401

    def test_api_auth_me_returns_staff_profile(self, client, staff_a):
        """GET /api/auth/me returns staff profile details including assigned centre."""
        res = make_auth_call(client, "GET", "/api/auth/me", "staff-a-sub")
        assert res.status_code == 200
        data = res.get_json()
        assert data["user"]["role"] == "STAFF"
        profile = data["user"]["profile"]
        assert profile["name"] == "Staff Alpha"
        assert profile["centre_id"] == staff_a.centre_id
        assert profile["centre_name"] == "Centre Alpha"

    def test_api_auth_me_returns_unassigned_staff_profile(self, client, unassigned_staff):
        """GET /api/auth/me for unassigned staff returns profile with centre_id = None."""
        res = make_auth_call(client, "GET", "/api/auth/me", "staff-unassigned-sub")
        assert res.status_code == 200
        data = res.get_json()
        assert data["user"]["role"] == "STAFF"
        profile = data["user"]["profile"]
        assert profile["centre_id"] is None
        assert profile["name"] == "Unassigned Staff"

    def test_login_template_redirects_staff_to_staff_dashboard(self, client):
        """login.html specifies /staff/dashboard as redirect destination for STAFF role."""
        resp = client.get("/login")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'if (role === "STAFF") return "/staff/dashboard";' in html

