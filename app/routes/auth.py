"""Authentication API routes.

Endpoints:
    POST /api/auth/register -> register a new farmer
    POST /api/auth/login    -> login with email/password
    POST /api/auth/logout   -> logout (revoke token)
    GET  /api/auth/me       -> get current user profile
"""

from flask import Blueprint, current_app, g, jsonify, request

from app.auth.decorators import login_required
from app.auth.exceptions import (
    AuthError,
    DuplicateUserError,
    InvalidCredentialsError,
    SupabaseConfigError,
    UserSynchronizationError,
)
from app.auth.service import (
    get_local_user,
    login_user,
    logout_user,
    register_farmer,
)
from app.models import UserRole

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _clean_optional_str(value) -> str | None:
    """Normalize an optional string field from JSON input.

    Safely handles missing keys, explicit JSON ``None``, empty strings and
    whitespace-only strings as ``None``; any other string is stripped.
    Non-string junk (numbers, objects) is coerced to a stripped string.
    """
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _validate_registration_input(data):
    """Validate registration input fields.

    Returns:
        tuple: (error_response, status_code) or (None, None) if valid.
    """
    if not data:
        return jsonify({"error": "Invalid request", "message": "JSON body required."}), 400

    email = _clean_optional_str(data.get("email")) or ""
    password = _clean_optional_str(data.get("password")) or ""
    name = _clean_optional_str(data.get("name")) or ""

    errors = []
    if not email:
        errors.append("email is required")
    elif "@" not in email or "." not in email:
        errors.append("email is invalid")

    if not password:
        errors.append("password is required")
    elif len(password) < 6:
        errors.append("password must be at least 6 characters")

    if not name:
        errors.append("name is required")

    if errors:
        return jsonify({"error": "Validation failed", "messages": errors}), 400

    return None, None


def _validate_login_input(data):
    """Validate login input fields.

    Returns:
        tuple: (error_response, status_code) or (None, None) if valid.
    """
    if not data:
        return jsonify({"error": "Invalid request", "message": "JSON body required."}), 400

    email = _clean_optional_str(data.get("email")) or ""
    password = _clean_optional_str(data.get("password")) or ""

    errors = []
    if not email:
        errors.append("email is required")
    if not password:
        errors.append("password is required")

    if errors:
        return jsonify({"error": "Validation failed", "messages": errors}), 400

    return None, None


def _get_user_role(supabase_user_id):
    """Get the role for a Supabase user ID, defaulting to FARMER."""
    local_user = get_local_user(supabase_user_id)

    return local_user.role if local_user else UserRole.FARMER


@auth_bp.route("/register", methods=["POST"])
def register():
    """Register a new farmer.

    Request JSON:
        {"email": "...", "password": "...", "name": "...", "phone": "..."}

    Returns:
        201 on success, 400 on validation error, 409 on duplicate, 503 if not configured.
    """
    data = request.get_json(silent=True)
    error, status = _validate_registration_input(data)
    if error:
        return error, status

    email = (_clean_optional_str(data.get("email")) or "").lower()
    password = _clean_optional_str(data.get("password")) or ""
    name = _clean_optional_str(data.get("name")) or ""
    phone = _clean_optional_str(data.get("phone"))

    try:
        supabase_user, session = register_farmer(
            email=email, password=password, name=name, phone=phone
        )
    except DuplicateUserError:
        return jsonify({
            "error": "Registration failed",
            "message": "An account with this email already exists.",
        }), 409
    except UserSynchronizationError as exc:
        current_app.logger.error(f"User sync error: {exc}")
        return jsonify({
            "error": "Registration failed",
            "message": "Account created but profile setup incomplete.",
        }), 500
    except SupabaseConfigError:
        current_app.logger.error("Supabase not configured")
        return jsonify({
            "error": "Service unavailable",
            "message": "Authentication service is not configured.",
        }), 503
    except AuthError as exc:
        return jsonify({"error": "Registration failed", "message": exc.message}), 400

    if not supabase_user:
        return jsonify({
            "error": "Registration failed",
            "message": "Could not create account.",
        }), 500

    return jsonify({
        "message": "Registration successful",
        "user": {
            "id": supabase_user.id,
            "email": supabase_user.email,
            "role": UserRole.FARMER,
            "access_token": session.access_token if session else None,
            "refresh_token": session.refresh_token if session else None,
        },
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """Login with email and password.

    Returns:
        200 on success, 400 on validation error, 401 on invalid credentials,
        503 if Supabase not configured.
    """
    data = request.get_json(silent=True)
    error, status = _validate_login_input(data)
    if error:
        return error, status

    email = (_clean_optional_str(data.get("email")) or "").lower()
    password = _clean_optional_str(data.get("password")) or ""

    try:
        supabase_user, session = login_user(email=email, password=password)
    except InvalidCredentialsError:
        return jsonify({
            "error": "Authentication failed",
            "message": "Invalid email or password.",
        }), 401
    except SupabaseConfigError:
        current_app.logger.error("Supabase not configured")
        return jsonify({
            "error": "Service unavailable",
            "message": "Authentication service is not configured.",
        }), 503
    except AuthError as exc:
        if getattr(exc, "code", None) == "ACCOUNT_DISABLED":
            return jsonify({
                "error": "Account disabled",
                "message": exc.message,
            }), 401
        return jsonify({"error": "Authentication failed", "message": exc.message}), 401

    if not supabase_user or not session:
        return jsonify({
            "error": "Authentication failed",
            "message": "Could not authenticate.",
        }), 401

    return jsonify({
        "message": "Login successful",
        "user": {
            "id": supabase_user.id,
            "email": supabase_user.email,
            "role": _get_user_role(supabase_user.id),
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
        },
    }), 200



@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Logout the current user.

    Revokes the access token server-side. Frontend should also clear tokens.

    Returns:
        200: { message }
    """
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.split()[1] if len(auth_header.split()) == 2 else None

    if token:
        logout_user(token)

    return jsonify({"message": "Logged out successfully."}), 200


@auth_bp.route("/me", methods=["GET"])
@login_required
def get_current_user():
    """Get the authenticated user's profile.

    Returns:
        200: { user: { id, supabase_user_id, email, role, active, profile? } }
    """
    local_user = g.current_user
    supabase_user = g.supabase_user

    response = {
        "id": local_user.id,
        "supabase_user_id": local_user.supabase_user_id,
        "email": supabase_user.email,
        "role": local_user.role,
        "active": local_user.is_active,
    }

    # Include role-specific profile for farmers
    if local_user.role == UserRole.FARMER and local_user.farmer:
        farmer = local_user.farmer
        response["profile"] = {
            "name": farmer.name,
            "phone": farmer.phone,
            "address": farmer.address,
            "city": farmer.city,
            "state": farmer.state,
            "pincode": farmer.pincode,
        }

    return jsonify({"user": response}), 200
