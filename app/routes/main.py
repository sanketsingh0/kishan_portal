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