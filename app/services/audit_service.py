"""
Audit Log service.

Provides business logic for creating and querying system audit logs.
"""

from datetime import datetime, time, date
import logging
from flask import g
from app.extensions import db
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)

# Keys to strip from metadata for security
SENSITIVE_KEYS = {
    "password", "token", "jwt", "cvv", "card", "secret", "private_key",
    "authorization", "auth", "p256dh"
}


def sanitize_metadata(metadata: dict | None) -> dict | None:
    """Remove sensitive entries from metadata dictionary."""
    if not metadata or not isinstance(metadata, dict):
        return metadata

    cleaned = {}
    for k, v in metadata.items():
        if any(sk in k.lower() for sk in SENSITIVE_KEYS):
            cleaned[k] = "[REDACTED]"
        elif isinstance(v, dict):
            cleaned[k] = sanitize_metadata(v)
        else:
            cleaned[k] = v
    return cleaned


def create_audit_log(
    action: str,
    entity_type: str,
    entity_id: int | None = None,
    description: str = "",
    metadata: dict | None = None,
    user_id: int | None = None,
) -> AuditLog:
    """Create and persist an audit log entry.

    If user_id is not explicitly provided, attempts to derive it from g.current_user.
    """
    if user_id is None:
        try:
            if hasattr(g, "current_user") and g.current_user:
                user_id = g.current_user.id
        except Exception:
            user_id = None

    cleaned_metadata = sanitize_metadata(metadata)

    audit_entry = AuditLog(
        user_id=user_id,
        action=action.upper().strip(),
        entity_type=entity_type.upper().strip(),
        entity_id=entity_id,
        description=description,
        metadata_json=cleaned_metadata,
    )

    try:
        db.session.add(audit_entry)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        logger.error(f"Failed to save audit log: {exc}")
        # Audit logging failure should not crash business transaction
        return None

    return audit_entry


def get_audit_logs(
    action: str | None = None,
    entity_type: str | None = None,
    user_id: int | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[AuditLog], int]:
    """Retrieve filtered and paginated audit logs.

    Returns:
        tuple of (list of AuditLog objects, total count)
    """
    query = AuditLog.query

    if action:
        query = query.filter(AuditLog.action == action.upper().strip())
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type.upper().strip())
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)

    if start_date:
        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(AuditLog.created_at >= sd)
        except ValueError:
            pass

    if end_date:
        try:
            ed = datetime.strptime(end_date, "%Y-%m-%d")
            ed_end = datetime.combine(ed.date(), time(23, 59, 59))
            query = query.filter(AuditLog.created_at <= ed_end)
        except ValueError:
            pass

    total = query.count()
    logs = (
        query.order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return logs, total


def get_audit_log_by_id(log_id: int) -> AuditLog | None:
    """Retrieve a single audit log entry by ID."""
    return db.session.get(AuditLog, log_id)
