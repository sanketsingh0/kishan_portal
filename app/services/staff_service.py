"""
Staff management service layer.

Handles business logic and database operations for staff profile management
by ADMIN users. Passwords are owned by Supabase Auth - never stored locally.
"""

import secrets

from app.extensions import db
from app.models import User, Staff, Centre, UserRole


class StaffError(Exception):
    """Base exception for staff operations."""

    def __init__(self, message, code="STAFF_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class StaffValidationError(StaffError):
    """Raised when staff validation fails."""

    def __init__(self, errors):
        self.errors = errors if isinstance(errors, list) else [errors]

def get_all_staff():
    """Return all staff records."""
    return Staff.query.all()


def get_staff_by_id(staff_id):
    """Retrieve a staff record by primary key."""
    return db.session.get(Staff, staff_id)


def get_staff_by_user_id(user_id):
    """Retrieve a staff record by the associated local user ID."""
    return Staff.query.filter_by(user_id=user_id).first()


def _validate_centre(centre_id):
    """Validate that a centre exists and is active. Raises StaffValidationError if invalid."""
    if centre_id is None:
        return None
    centre = db.session.get(Centre, centre_id)
    if not centre:
        raise StaffValidationError([f"Centre {centre_id} does not exist."])
    if not centre.is_active:
        raise StaffValidationError([f"Centre {centre_id} is not active."])
    return centre

def create_staff(user_id, name, phone=None, centre_id=None):
    """Create a staff profile for an existing local user (role must be STAFF).

    Does NOT create a Supabase Auth user - use provision_staff for that.
    """
    user = db.session.get(User, user_id)
    if not user:
        raise StaffValidationError([f"Local user {user_id} not found."])
    if user.role != UserRole.STAFF:
        raise StaffValidationError([f"User {user_id} does not have STAFF role."])

    existing = Staff.query.filter_by(user_id=user_id).first()
    if existing:
        raise StaffConflictError(f"Staff profile already exists for user {user_id}.")

    _validate_centre(centre_id)

    staff = Staff(user_id=user_id, name=name, phone=phone, centre_id=centre_id)
    db.session.add(staff)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise StaffError(f"Database error creating staff profile: {exc}")

    return staff



def provision_staff(email, name, phone=None, centre_id=None, password=None):
    """Provision a new staff user end-to-end.

    1. Creates a Supabase Auth user (owns the password).
    2. Creates a local User record (role=STAFF).
    3. Creates a local Staff profile linked to the centre.

    Returns the Staff record.
    """
    from app.auth.service import get_supabase_client
    from supabase_auth.errors import AuthApiError

    _validate_centre(centre_id)

    # Generate a temporary password if none provided
    if not password:
        password = secrets.token_urlsafe(16)

    client = get_supabase_client()
    try:
        response = client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "name": name,
                    "phone": phone or "",
                    "role": UserRole.STAFF,
                }
            },
        })
    except AuthApiError as exc:
        error_msg = str(exc).lower()
        if "already" in error_msg or "duplicate" in error_msg or "exists" in error_msg:
            raise StaffConflictError(f"A user with email {email} already exists.")
        raise StaffError(f"Supabase sign-up failed: {exc}")
    except Exception as exc:
        raise StaffError(f"Supabase sign-up failed: {exc}")

    if not response.user:
        raise StaffError("Supabase sign-up returned no user.")

    supabase_user_id = response.user.id

    # Create local User record
    local_user = User(
        supabase_user_id=supabase_user_id,
        role=UserRole.STAFF,
        is_active=True,
    )
    db.session.add(local_user)
    db.session.flush()

    # Create Staff profile
    staff = Staff(
        user_id=local_user.id,
        name=name,
        phone=phone,
        centre_id=centre_id,
    )
    db.session.add(staff)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise StaffError(f"Database error creating local staff records: {exc}")

    return staff


def update_staff(staff_id, data):
    """Update staff profile fields (name, phone, centre_id)."""
    staff = db.session.get(Staff, staff_id)
    if not staff:
        raise StaffNotFoundError(f"Staff {staff_id} not found.")

    if "name" in data:
        name = data["name"]
        if not name or not isinstance(name, str) or len(name.strip()) < 2:
            raise StaffValidationError(["Name must be at least 2 characters."])
        staff.name = name.strip()

    if "phone" in data:
        phone = data["phone"]
        if phone is not None:
            phone = str(phone).strip()
            if len(phone) > 20:
                raise StaffValidationError(["Phone cannot exceed 20 characters."])
        staff.phone = phone

    if "centre_id" in data:
        centre_id = data["centre_id"]
        _validate_centre(centre_id)  # raises if invalid
        staff.centre_id = centre_id

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise StaffError(f"Database error updating staff: {exc}")

    return staff


def set_staff_active(staff_id, active):
    """Activate or deactivate a staff user (soft deactivation via User.is_active)."""
    staff = db.session.get(Staff, staff_id)
    if not staff:
        raise StaffNotFoundError(f"Staff {staff_id} not found.")

    user = staff.user
    if user:
        user.is_active = active

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise StaffError(f"Database error changing staff active state: {exc}")

    return staff


def deactivate_staff(staff_id):
    """Soft-deactivate a staff user. Does NOT delete the Supabase Auth user."""
    return set_staff_active(staff_id, False)


def activate_staff(staff_id):
    """Re-activate a previously deactivated staff user."""
    return set_staff_active(staff_id, True)


class StaffNotFoundError(StaffError):
    """Raised when a staff record is not found."""

    def __init__(self, message="Staff record not found"):
        super().__init__(message, code="STAFF_NOT_FOUND")


class StaffConflictError(StaffError):
    """Raised when a staff operation conflicts with existing data."""

    def __init__(self, message="Staff operation conflict"):
        super().__init__(message, code="STAFF_CONFLICT")
