"""Staff Dashboard page route.

Renders the staff dashboard showing the assigned centre and operational
quick-links. Centre isolation is enforced on every operational API; this
page itself only displays information belonging to the assigned centre.

An unassigned STAFF (centre_id = None) sees a clear message instead of
centre operations.
"""

from flask import Blueprint, render_template, g

from app.auth.decorators import login_required, role_required
from app.models import UserRole, Staff

staff_bp = Blueprint("staff", __name__, url_prefix="/staff")


@staff_bp.get("/dashboard")
def staff_dashboard():
    """Render the staff dashboard HTML template for browser navigation.

    Client-side JavaScript (auth.js) will authenticate the Bearer token, verify
    the STAFF role, and dynamically load centre/queue data via authenticated APIs.
    """
    staff = None
    centre = None
    if hasattr(g, "current_user") and g.current_user:
        staff = Staff.query.filter_by(user_id=g.current_user.id).first()
        centre = staff.centre if staff else None

    return render_template(
        "staff_dashboard.html",
        staff=staff,
        centre=centre,
    )
