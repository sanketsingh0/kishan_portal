"""Farmer service layer.

Handles business logic and data validation for Farmer profiles:
- Retrieving farmer profile details
- Updating profile information with input validation and phone uniqueness checks
"""

import re
from app.extensions import db
from app.models import Farmer, User


class FarmerError(Exception):
    """Base exception for farmer service errors."""

    def __init__(self, message: str, code: str = "FARMER_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class DuplicatePhoneError(FarmerError):
    """Raised when updated phone number is already registered to another user."""

    def __init__(self, message: str = "Phone number already registered to another account."):
        super().__init__(message, code="DUPLICATE_PHONE")


class FarmerValidationError(FarmerError):
    """Raised when profile validation fails."""

    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message, code="VALIDATION_ERROR")
        self.errors = errors or [message]


def get_farmer_by_user_id(user_id: int) -> Farmer | None:
    """Retrieve farmer profile by local user ID.

    Args:
        user_id: The local database ID of the user.

    Returns:
        Farmer profile object or None.
    """
    return Farmer.query.filter_by(user_id=user_id).first()


def update_farmer_profile(user_id: int, data: dict) -> Farmer:
    """Update farmer profile with validation.

    Args:
        user_id: Local user ID of the authenticated farmer.
        data: Dictionary of fields to update.

    Returns:
        Updated Farmer object.

    Raises:
        FarmerValidationError: if input fails validation checks.
        DuplicatePhoneError: if phone belongs to another user.
    """
    farmer = get_farmer_by_user_id(user_id)
    if not farmer:
        raise FarmerValidationError("Farmer profile not found for current user.")

    if not isinstance(data, dict):
        raise FarmerValidationError("Invalid request body. Expected JSON object.")

    errors = []

    # Validations
    if "name" in data:
        name = str(data["name"] or "").strip()
        if not name or len(name) < 2:
            errors.append("Name must be at least 2 characters long.")
        elif len(name) > 120:
            errors.append("Name cannot exceed 120 characters.")
        else:
            farmer.name = name

    if "phone" in data and data["phone"] is not None:
        phone = str(data["phone"]).strip()
        if phone:
            # Phone validation: digits, optional leading +, length 10-15
            clean_phone = re.sub(r"[\s\-\(\)]", "", phone)
            if not re.match(r"^\+?\d{10,15}$", clean_phone):
                errors.append("Phone number must be between 10 and 15 digits.")
            else:
                # Check uniqueness against other farmers
                existing = Farmer.query.filter(
                    Farmer.phone == clean_phone,
                    Farmer.user_id != user_id
                ).first()
                if existing:
                    raise DuplicatePhoneError()
                farmer.phone = clean_phone
        else:
            farmer.phone = None

    if "pincode" in data and data["pincode"] is not None:
        pincode = str(data["pincode"]).strip()
        if pincode:
            if not re.match(r"^\d{6}$", pincode):
                errors.append("Pincode must be a valid 6-digit number.")
            else:
                farmer.pincode = pincode
        else:
            farmer.pincode = None

    if "address" in data and data["address"] is not None:
        address = str(data["address"]).strip()
        if len(address) > 500:
            errors.append("Address cannot exceed 500 characters.")
        else:
            farmer.address = address if address else None

    if "city" in data and data["city"] is not None:
        city = str(data["city"]).strip()
        if len(city) > 100:
            errors.append("City cannot exceed 100 characters.")
        else:
            farmer.city = city if city else None

    if "state" in data and data["state"] is not None:
        state = str(data["state"]).strip()
        if len(state) > 100:
            errors.append("State cannot exceed 100 characters.")
        else:
            farmer.state = state if state else None

    if errors:
        raise FarmerValidationError("Profile validation failed", errors=errors)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise FarmerError(f"Database error while saving profile: {exc}")

    return farmer
