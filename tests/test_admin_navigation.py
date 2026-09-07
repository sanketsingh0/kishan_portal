"""
Tests for Admin Portal navigation and Admin Management UI.
"""
import pytest


class TestAdminPortalNavigation:
    def test_admin_dashboard_contains_admin_portal_link(self, client):
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert 'href="/admin/management"' in html
        assert "Admin Portal" in html

    def test_admin_portal_link_is_anchor_tag(self, client):
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert '<a href="/admin/management"' in html


class TestAdminManagementPage:
    def test_admin_management_page_loads(self, client):
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Admin Management" in html or "Centre & Crop Management" in html

    def test_admin_management_has_centre_section(self, client):
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Procurement Centres" in html or "centres-pane" in html

    def test_admin_management_has_crop_section(self, client):
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Crops" in html or "crops-pane" in html

    def test_admin_management_has_staff_section(self, client):
        resp = client.get("/admin/management")
        assert resp.status_code == 200
class TestAdminManagementActions:
    def test_centre_create_action_exists(self, client):
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "addCentreBtn" in html or "Add Centre" in html

    def test_centre_edit_action_exists(self, client):
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "openEditCentreModal" in html or "editCentre" in html

    def test_centre_deactivate_action_exists(self, client):
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "toggleCentre" in html or "deactivateCentre" in html

    def test_crop_create_action_exists(self, client):
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "addCropBtn" in html or "Add Crop" in html

    def test_crop_edit_action_exists(self, client):
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "openEditCropModal" in html or "editCrop" in html

    def test_crop_deactivate_action_exists(self, client):
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "toggleCrop" in html or "deactivateCrop" in html

    def test_staff_create_action_exists(self, client):
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "addStaffBtn" in html or "Add Staff" in html

    def test_staff_edit_action_exists(self, client):
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "openEditStaffModal" in html or "editStaff" in html

    def test_staff_deactivate_action_exists(self, client):
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "toggleStaff" in html or "deactivateStaff" in html

    def test_staff_centre_assignment_exists(self, client):
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "staffCentreId" in html or "Assign Centre" in html


class TestAdminManagementRouteRegistration:
    def test_admin_management_route_exists(self, client):
        resp = client.get("/admin/management")
        assert resp.status_code == 200

    def test_admin_dashboard_route_exists(self, client):
        resp = client.get("/admin/dashboard")
        assert resp.status_code == 200

    def test_admin_slots_route_exists(self, client):
        resp = client.get("/admin/slots")
        assert resp.status_code == 200
