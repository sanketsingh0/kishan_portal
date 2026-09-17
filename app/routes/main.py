"""Placeholder pages for the prototype shell.

Only a minimal landing page exists right now; the real frontend
(HTML/CSS/JS/Bootstrap) is built in a later milestone.
"""

from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    return render_template("index.html")


@main_bp.get("/login")
def login_page():
    return render_template("auth/login.html")


@main_bp.get("/register")
def register_page():
    return render_template("auth/register.html")


@main_bp.get("/farmer/dashboard")
def farmer_dashboard():
    return render_template("farmer_dashboard.html")


@main_bp.get("/farmer/queue-pass/<int:booking_id>")
def farmer_queue_pass(booking_id: int):
    """Serve the Smart Queue Pass HTML page (no pass data embedded).

    This is a page route, NOT an API endpoint: it is safe to open with a plain
    browser navigation (no Authorization header), exactly like the other page
    shells in this module. The page itself then requests the pass through the
    authenticated JSON API ``GET /api/queue-pass/my/<booking_id>/display`` using
    ``window.KP.authFetch()`` (Bearer token from local storage).

    No pass, QR or farmer data is rendered server-side, so this HTML shell stays
    free of sensitive information and farmer ownership is still enforced by the
    API route.
    """
    return render_template("queue_pass.html", booking_id=booking_id)


@main_bp.get("/admin/management")
def admin_management():
    return render_template("admin_management.html")


@main_bp.get("/admin/slots")
def admin_slots():
    return render_template("admin_slots.html")


@main_bp.get("/admin/dashboard")
def admin_dashboard():
    return render_template("admin_dashboard.html")


@main_bp.get("/offline")
def offline():
    return render_template("offline.html")