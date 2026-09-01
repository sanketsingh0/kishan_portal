"""
KisanProcure entry point.

Loads environment variables from .env (if present), builds the Flask app
and runs the development server.

Usage:
    python run.py
    flask --app run.py run
"""

import os

from dotenv import load_dotenv

load_dotenv()

from app import create_app  # noqa: E402  (dotenv must load before app imports)

app = create_app()


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "1") == "1"
    app.run(host=host, port=port, debug=debug)