"""Crop catalogue service layer.

Encapsulates business logic, data validation, and database operations for crops:
- Catalogue listing (filtered by active status and user role)
- Crop creation with name uniqueness and category validation
- Updates and soft deletion / deactivation
"""

from app.extensions import db
from app.models import Crop


class CropError(Exception):
    """Base exception for crop service errors."""

    def __init__(self, message: str, code: str = "CROP_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class DuplicateCropNameError(CropError):
    """Raised when crop name already exists."""

    def __init__(self, message: str = "A crop with this name already exists."):
        super().__init__(message, code="DUPLICATE_CROP_NAME")


class CropValidationError(CropError):
    """Raised when crop validation fails."""

    def __init__(self, message: str, errors: list | None = None):
        super().__init__(message, code="VALIDATION_ERROR")
        self.errors = errors or [message]


def get_all_crops(include_inactive: bool = False) -> list[Crop]:
    """Retrieve all crops.

    Args:
        include_inactive: If True, returns active and inactive crops.
                          If False, returns only active crops.

    Returns:
        List of Crop instances.
    """
    query = Crop.query
    if not include_inactive:
        query = query.filter(Crop.is_active == True)
    return query.order_by(Crop.name.asc()).all()


def get_crop_by_id(crop_id: int, include_inactive: bool = False) -> Crop | None:
    """Retrieve crop by ID.

    Args:
        crop_id: Database ID of crop.
        include_inactive: If False, returns None if crop is inactive.

    Returns:
        Crop instance or None.
    """
    crop = db.session.get(Crop, crop_id)
    if not crop:
        return None
    if not include_inactive and not crop.is_active:
        return None
    return crop


def create_crop(data: dict) -> Crop:
    """Create a new crop catalogue entry.

    Args:
        data: Dictionary with name, category, is_active.

    Returns:
        Created Crop instance.

    Raises:
        CropValidationError: if validation fails.
        DuplicateCropNameError: if name is duplicate.
    """
    if not isinstance(data, dict):
        raise CropValidationError("Invalid request body. Expected JSON object.")

    errors = []

    name = str(data.get("name") or "").strip()
    if not name:
        errors.append("Crop name is required.")
    elif len(name) > 100:
        errors.append("Crop name cannot exceed 100 characters.")
    else:
        existing = Crop.query.filter(Crop.name == name).first()
        if existing:
            raise DuplicateCropNameError()

    category = data.get("category")
    if category is not None:
        category = str(category).strip()
        if len(category) > 80:
            errors.append("Category cannot exceed 80 characters.")
        if not category:
            category = None

    is_active = data.get("is_active")
    if is_active is None:
        is_active = data.get("active", True)
    is_active = bool(is_active)

    if errors:
        raise CropValidationError("Crop creation failed validation.", errors=errors)

    crop = Crop(name=name, category=category, is_active=is_active)

    try:
        db.session.add(crop)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise CropError(f"Database error creating crop: {exc}")

    try:
        from app.services.audit_service import create_audit_log
        create_audit_log(
            action="CREATE_CROP",
            entity_type="CROP",
            entity_id=crop.id,
            description=f"Created crop '{crop.name}'",
            metadata={"crop_id": crop.id, "name": crop.name},
        )
    except Exception:
        pass

    return crop


def update_crop(crop_id: int, data: dict) -> Crop:
    """Update an existing crop.

    Args:
        crop_id: Database ID of crop to update.
        data: Dictionary of fields to update.

    Returns:
        Updated Crop instance.

    Raises:
        CropValidationError: if crop is missing or fields fail validation.
        DuplicateCropNameError: if updated name collides with another crop.
    """
    crop = db.session.get(Crop, crop_id)
    if not crop:
        raise CropValidationError("Crop not found.", errors=["Crop not found."])

    if not isinstance(data, dict):
        raise CropValidationError("Invalid request body. Expected JSON object.")

    errors = []

    if "name" in data:
        name = str(data["name"] or "").strip()
        if not name:
            errors.append("Crop name cannot be empty.")
        elif len(name) > 100:
            errors.append("Crop name cannot exceed 100 characters.")
        else:
            existing = Crop.query.filter(Crop.name == name, Crop.id != crop_id).first()
            if existing:
                raise DuplicateCropNameError()
            crop.name = name

    if "category" in data:
        cat = data["category"]
        if cat is not None:
            cat_str = str(cat).strip()
            if len(cat_str) > 80:
                errors.append("Category cannot exceed 80 characters.")
            else:
                crop.category = cat_str if cat_str else None
        else:
            crop.category = None

    if "is_active" in data:
        crop.is_active = bool(data["is_active"])
    elif "active" in data:
        crop.is_active = bool(data["active"])

    if errors:
        raise CropValidationError("Crop update failed validation.", errors=errors)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise CropError(f"Database error updating crop: {exc}")

    try:
        from app.services.audit_service import create_audit_log
        create_audit_log(
            action="UPDATE_CROP",
            entity_type="CROP",
            entity_id=crop.id,
            description=f"Updated crop '{crop.name}'",
            metadata={"crop_id": crop.id, "is_active": crop.is_active},
        )
    except Exception:
        pass

    return crop


def deactivate_crop(crop_id: int) -> Crop:
    """Soft delete / deactivate a crop.

    Args:
        crop_id: Database ID of crop to deactivate.

    Returns:
        Deactivated Crop instance.
    """
    crop = db.session.get(Crop, crop_id)
    if not crop:
        raise CropValidationError("Crop not found.", errors=["Crop not found."])

    crop.is_active = False
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise CropError(f"Database error deactivating crop: {exc}")

    try:
        from app.services.audit_service import create_audit_log
        create_audit_log(
            action="DEACTIVATE_CROP",
            entity_type="CROP",
            entity_id=crop.id,
            description=f"Deactivated crop '{crop.name}'",
            metadata={"crop_id": crop.id},
        )
    except Exception:
        pass

    return crop
