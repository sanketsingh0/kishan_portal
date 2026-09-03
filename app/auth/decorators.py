"""Authentication and role-based authorization decorators.

Provides reusable decorators for Flask routes:
- @login_required: verifies JWT and attaches current user
- @role_required(role): requires a specific role
- @roles_required(*roles): requires any of the specified roles
"""

from functools import wraps

from flask import g, jsonify, request

from app.auth.exceptions import AuthError
from app.auth.service import get_local_user, verify_token
from app.models import UserRole


def _extract_bearer_token():
    """Extract the Bearer token from the Authorization header.

    Returns:
        The token string, or None if missing/malformed.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header:
        return None

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    return parts[1]


def login_required(f):
    """Decorator that requires a valid Supabase JWT access token.

    On success, attaches the local User object to `g.current_user`.
    On failure, returns 401 Unauthorized.

    Usage:
        @login_required
        def my_route():
            user = g.current_user
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_bearer_token()

        if not token:
            return jsonify({
                "error": "Authentication required",
                "message": "Missing or malformed Authorization header. "
                           "Use 'Bearer <token>' format.",
            }), 401

        # Verify the token cryptographically via Supabase
        supabase_user = verify_token(token)

        if not supabase_user:
            return jsonify({
                "error": "Authentication failed",
                "message": "Invalid or expired token.",
            }), 401

        # Look up the local user record
        local_user = get_local_user(supabase_user.id)

        if not local_user:
            return jsonify({
                "error": "Authentication failed",
                "message": "User account not found.",
            }), 401

        if not local_user.is_active:
            return jsonify({
                "error": "Account disabled",
                "message": "This account has been deactivated.",
            }), 401

        # Attach to request context
        g.current_user = local_user
        g.supabase_user = supabase_user

        return f(*args, **kwargs)

    return decorated


def role_required(required_role):
    """Decorator that requires the user to have a specific role.

    Must be used after @login_required.
    Returns 403 Forbidden if the user's role doesn't match.

    Args:
        required_role: a UserRole value (e.g., UserRole.ADMIN).

    Usage:
        @login_required
        @role_required(UserRole.ADMIN)
        def admin_route():
            ...
    """

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(g, "current_user") or g.current_user is None:
                return jsonify({
                    "error": "Authentication required",
                    "message": "Login required for this resource.",
                }), 401

            if g.current_user.role != required_role:
                return jsonify({
                    "error": "Forbidden",
                    "message": f"Requires {required_role} role.",
                }), 403

            return f(*args, **kwargs)

        return decorated

    return decorator


def roles_required(*allowed_roles):
    """Decorator that requires the user to have one of several roles.

    Must be used after @login_required.
    Returns 403 Forbidden if the user's role is not in the allowed set.

    Args:
        *allowed_roles: UserRole values (e.g., UserRole.STAFF, UserRole.ADMIN).

    Usage:
        @login_required
        @roles_required(UserRole.STAFF, UserRole.ADMIN)
        def staff_or_admin_route():
            ...
    """

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not hasattr(g, "current_user") or g.current_user is None:
                return jsonify({
                    "error": "Authentication required",
                    "message": "Login required for this resource.",
                }), 401

            if g.current_user.role not in allowed_roles:
                return jsonify({
                    "error": "Forbidden",
                    "message": "Insufficient permissions.",
                }), 403

            return f(*args, **kwargs)

        return decorated

    return decorator
