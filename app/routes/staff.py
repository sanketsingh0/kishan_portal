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
@login_required
@role_required(UserRole.STAFF)
def staff_dashboard():
    """Render the staff dashboard for the logged-in STAFF user.

    If the staff member has no Staff profile or no assigned centre, the
    template renders a clear "no centre assigned" message and no centre
    operations are available.
    """
    staff = Staff.query.filter_by(user_id=g.current_user.id).first()
    centre = staff.centre if staff else None
    return render_template(
        "staff_dashboard.html",
        staff=staff,
        centre=centre,
    )
