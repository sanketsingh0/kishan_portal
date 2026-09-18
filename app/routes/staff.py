"""Staff Dashboard page shell.

Renders the staff dashboard HTML shell. The server embeds NO staff, centre or
queue data: the page itself authenticates through the shared ``auth.js``
helper (``window.KP.authFetch()``) and loads everything from the authenticated
JSON APIs, where STAFF/ADMIN role authorization and centre isolation stay
enforced.

This is a PAGE route, not an API endpoint, so - exactly like the Farmer and
Admin dashboard shells (``app/routes/main.py``) - it is served to plain browser
navigation, which cannot send the Bearer Authorization header. An unassigned
STAFF (centre_id = None) is resolved client-side via ``GET /api/auth/me`` and
sees a clear message instead of centre operations.
"""

from flask import Blueprint, render_template

staff_bp = Blueprint("staff", __name__, url_prefix="/staff")


@staff_bp.get("/dashboard")
def staff_dashboard():
    """Serve the public staff dashboard HTML shell (no staff data embedded)."""
    return render_template("staff_dashboard.html")
