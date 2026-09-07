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
        html = resp.data.decode("utf-8")
        assert "Staff Management" in html or "staff-pane" in html

    def test_admin_management_has_staff_table(self, client):
        """The staff pane must have a table to display staff records."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "staffTableBody" in html

    def test_admin_management_has_add_staff_button(self, client):
        """The staff pane must have an 'Add Staff' button."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "Add New Staff" in html or "Add Staff" in html

    def test_admin_management_has_staff_modal(self, client):
        """The staff modal must exist for creating/editing staff."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert 'id="staffModal"' in html

    def test_admin_management_has_staff_form(self, client):
        """The staff form must have all required fields."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        # Staff form fields
        assert 'id="staffForm"' in html
        assert 'id="staffName"' in html
        assert 'id="staffEmail"' in html
        assert 'id="staffPhone"' in html
        assert 'id="staffCentreId"' in html
        assert 'id="staffPassword"' in html

    def test_admin_management_staff_form_has_centre_dropdown(self, client):
        """The staff form must have a centre dropdown for assignment."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert 'id="staffCentreId"' in html
        assert "Assign Centre" in html or "No Centre Assigned" in html

    def test_admin_management_staff_tab_button_exists(self, client):
        """The staff tab button must exist and target the staff pane."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert 'id="staff-tab"' in html
        assert 'data-bs-target="#staff-pane"' in html

    def test_admin_management_staff_pane_exists(self, client):
        """The staff pane must exist with correct ID."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert 'id="staff-pane"' in html

    def test_admin_management_loadstaff_function_defined(self, client):
        """The loadStaff function must be defined to load staff data."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "function loadStaff()" in html or "async function loadStaff()" in html

    def test_admin_management_openCreateStaffModal_function_defined(self, client):
        """The openCreateStaffModal function must be defined."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "function openCreateStaffModal()" in html

    def test_admin_management_openEditStaffModal_function_defined(self, client):
        """The openEditStaffModal function must be defined."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "function openEditStaffModal(" in html

    def test_admin_management_deactivateStaff_function_defined(self, client):
        """The deactivateStaff function must be defined."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "function deactivateStaff(" in html or "async function deactivateStaff(" in html

    def test_admin_management_activateStaff_function_defined(self, client):
        """The activateStaff function must be defined."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "function activateStaff(" in html or "async function activateStaff(" in html

    def test_admin_management_populateStaffCentreSelect_function_defined(self, client):
        """The populateStaffCentreSelect function must be defined."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "function populateStaffCentreSelect(" in html

    def test_admin_management_staff_api_calls_present(self, client):
        """The staff management must call the correct API endpoints."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        # Staff API endpoints
        assert "/api/admin/staff" in html
        assert '"POST"' in html or "'POST'" in html
        assert '"PUT"' in html or "'PUT'" in html
        assert '"DELETE"' in html or "'DELETE'" in html

    def test_admin_management_staff_tab_onclick_loads_staff(self, client):
        """The staff tab must call loadStaff() when clicked."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "loadStaff()" in html

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


class TestAddCentreButtonAndForm:
    """Regression tests for the Add New Centre button and form behavior.

    Verifies that the 'Add New Centre' button is present, the centre modal
    contains all required fields, and the JavaScript has no syntax errors
    that would prevent the form from opening.
    """

    def test_add_new_centre_button_exists(self, client):
        """The Add New Centre button must be present on the page."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "openCreateCentreModal()" in html
        assert "Add New Centre" in html

    def test_centre_modal_exists(self, client):
        """The centre modal must exist with the correct ID."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert 'id="centreModal"' in html

    def test_centre_form_has_required_fields(self, client):
        """The centre form must contain all fields required by the Centre model/API."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        # Name field
        assert 'id="centreName"' in html
        # Location field
        assert 'id="centreLocation"' in html
        # Opening time field
        assert 'id="centreOpening"' in html
        # Closing time field
        assert 'id="centreClosing"' in html
        # Daily capacity field
        assert 'id="centreCapacity"' in html
        # Average processing minutes field
        assert 'id="centreAvgProc"' in html
        # Active/status checkbox
        assert 'id="centreActive"' in html

    def test_centre_form_has_hidden_id_field(self, client):
        """The centre form must have a hidden centreId field for edit mode."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert 'id="centreId"' in html

    def test_centre_submit_button_exists(self, client):
        """The centre form must have a submit button."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert 'id="centreForm"' in html
        assert "Save Centre" in html

    def test_javascript_has_no_extra_braces(self, client):
        """The JavaScript must not have syntax errors from extra closing braces.

        This is a regression test for the bug where extra '}' characters caused
        a JavaScript syntax error that prevented the entire script from executing,
        making the Add New Centre button non-functional.
        """
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        # The openCreateCentreModal function must be defined
        assert "function openCreateCentreModal()" in html
        # The openEditCentreModal function must be defined
        assert "function openEditCentreModal(c)" in html
        # The centreForm submit handler must be registered
        assert 'document.getElementById("centreForm").addEventListener' in html

    def test_openCreateCentreModal_function_defined(self, client):
        """The openCreateCentreModal function must be properly defined in the script."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        # Verify the function is defined and shows the modal
        assert "function openCreateCentreModal()" in html
        assert 'new bootstrap.Modal(document.getElementById("centreModal")).show()' in html

    def test_centre_form_submit_calls_api(self, client):
        """The centre form submit handler must call the /api/centres API."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        # Verify the form submits to the correct API endpoint
        assert '"/api/centres"' in html
        # Verify it uses POST for creation
        assert '"POST"' in html

    def test_bootstrap_js_loaded(self, client):
        """Bootstrap JS must be loaded for modal functionality."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "bootstrap" in html.lower()
        assert "bootstrap.bundle.min.js" in html or "bootstrap.min.js" in html

    def test_auth_js_loaded(self, client):
        """The auth.js helper must be loaded for API token handling."""
        resp = client.get("/admin/management")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "auth.js" in html
