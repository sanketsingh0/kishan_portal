"""
Shared building blocks for models: UTC timestamps and the user-role constants.

Timestamps are stored as timezone-aware UTC. SQLite (local dev) stores them
without a timezone label while PostgreSQL (Supabase, production) keeps them as
`timestamptz`; SQLAlchemy normalises both back to Python datetimes.
"""

from datetime import datetime, timezone

from app.extensions import db


def utcnow() -> datetime:
    """Current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


class TimestampMixin:
    """Adds `created_at` / `updated_at` to any model."""

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class UserRole:
    """Allowed user roles. Stored as a DB CHECK-constrained string/enum."""

    FARMER = "FARMER"
    STAFF = "STAFF"
    ADMIN = "ADMIN"

    choices = (FARMER, STAFF, ADMIN)