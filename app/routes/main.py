"""Placeholder pages for the prototype shell.

Only a minimal landing page exists right now; the real frontend
(HTML/CSS/JS/Bootstrap) is built in a later milestone.
"""

from flask import Blueprint, render_template

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    return render_template("index.html")