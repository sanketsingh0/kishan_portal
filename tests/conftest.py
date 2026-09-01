"""Shared pytest fixtures.

Each test gets an application bound to an isolated in-memory SQLite
database, so tests never touch real data.
"""

import pytest

from app import create_app
from app.extensions import db


@pytest.fixture()
def app():
    """Create the application with the testing configuration."""
    application = create_app("testing")
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    """HTTP test client ready to call the API routes."""
    return app.test_client()