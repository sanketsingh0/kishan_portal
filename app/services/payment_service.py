"""Payment service layer.

Handles business logic and database operations for Payment status tracking.
NOTE: Status tracking only. No live payment gateway or online transactions.
"""

from datetime import datetime, date
from decimal import Decimal
from app.extensions import db
from app.models import Booking, Payment, PaymentStatus
from app.services.farmer_service import get_farmer_by_user_id
from app.queue.events import emit_payment_update


class PaymentError(Exception):
    """Base exception for payment operations."""

    def __init__(self, message="Payment operation failed"):
        self.message = message
        super().__init__(self.message)


class PaymentNotFoundError(PaymentError):
    """Raised when a requested payment or booking record is not found."""

    def __init__(self, message="Payment record not found"):
        super().__init__(message)


class PaymentConflictError(PaymentError):
    """Raised when attempting to create a duplicate payment record."""

    def __init__(self, message="Payment record already exists for this booking"):
        super().__init__(message)


class PaymentValidationError(PaymentError):
    """Raised when validation of payment fields fails."""

    def __init__(self, errors):
        self.errors = errors
        message = "; ".join(errors) if isinstance(errors, list) else str(errors)
        super().__init__(message)


def parse_date_value(val):
    """Parse date string (YYYY-MM-DD) or date object."""
    if val is None:
        return None
    if isinstance(val, date):
        return val
    if isinstance(val, str):
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d").date()
        except ValueError:
            raise PaymentValidationError(["Invalid payment_date format. Expected YYYY-MM-DD."])
    raise PaymentValidationError(["Invalid payment_date type."])


def get_payment_by_booking(booking_id: int, user_id: str | None = None) -> Payment | None:
    """Retrieve payment record for a booking.

    If user_id is provided, verifies that the booking belongs to the farmer.
    """
    booking = db.session.get(Booking, booking_id)
    if not booking:
        return None

    if user_id is not None:
        farmer = get_farmer_by_user_id(user_id)
        if not farmer or booking.farmer_id != farmer.id:
            return None

    return booking.payment


def create_payment(booking_id: int, data: dict) -> Payment:
    """Create a new payment record for a booking (STAFF/ADMIN)."""
    if not isinstance(data, dict):
        raise PaymentValidationError(["Request body must be a JSON object."])

    booking = db.session.get(Booking, booking_id)
    if not booking:
        raise PaymentNotFoundError(f"Booking {booking_id} not found.")

    if booking.payment:
        raise PaymentConflictError(f"Payment record already exists for booking {booking_id}.")

    errors = []
    status = data.get("payment_status", PaymentStatus.PENDING)
    if status not in PaymentStatus.choices:
        errors.append(f"Invalid payment_status '{status}'. Choices: {', '.join(PaymentStatus.choices)}.")

    amount = data.get("amount")
    if amount is not None:
        try:
            amount_val = float(amount)
            if amount_val < 0:
                errors.append("amount must be greater than or equal to 0.")
            else:
                amount = Decimal(str(amount_val))
        except (ValueError, TypeError):
            errors.append("amount must be a valid numeric value.")

    payment_reference = data.get("payment_reference")
    if payment_reference is not None:
        if not isinstance(payment_reference, str) or len(payment_reference) > 100:
            errors.append("payment_reference must be a string up to 100 characters.")
        else:
            payment_reference = payment_reference.strip()

    payment_date = None
    if "payment_date" in data and data["payment_date"]:
        try:
            payment_date = parse_date_value(data["payment_date"])
        except PaymentValidationError as pve:
            errors.extend(pve.errors)

    remarks = data.get("remarks")
    if remarks is not None:
        if not isinstance(remarks, str) or len(remarks) > 255:
            errors.append("remarks must be a string up to 255 characters.")

    if errors:
        raise PaymentValidationError(errors)

    payment = Payment(
        booking_id=booking.id,
        payment_status=status,
        amount=amount,
        payment_reference=payment_reference,
        payment_date=payment_date,
        remarks=remarks,
    )

    try:
        db.session.add(payment)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise PaymentError(f"Database error while saving payment: {exc}")

    # Emit realtime event post-commit
    centre_id = booking.slot.centre_id if booking.slot else None
    slot_date = booking.slot.slot_date if booking.slot else None
    emit_payment_update(booking.id, centre_id, slot_date, reason="PAYMENT_CREATED")

    try:
        from app.services.audit_service import create_audit_log
        create_audit_log(
            action="CREATE_PAYMENT",
            entity_type="PAYMENT",
            entity_id=payment.id,
            description=f"Created payment for booking #{booking.id} with status {status}",
            metadata={"booking_id": booking.id, "amount": float(amount) if amount else None, "status": status},
        )
    except Exception:
        pass

    try:
        if booking.farmer and booking.farmer.user_id:
            from app.services.notification_service import create_notification
            from app.models import NotificationType

            create_notification(
                user_id=booking.farmer.user_id,
                notification_type=NotificationType.PAYMENT_UPDATE,
                title=f"Payment Status: {status}",
                message=f"Payment status for token {booking.token_number or ''} updated to {status.replace('_', ' ')}.",
                booking_id=booking.id,
            )
    except Exception:
        pass

    return payment


def update_payment(booking_id: int, data: dict) -> Payment:
    """Update an existing payment record for a booking (STAFF/ADMIN)."""
    if not isinstance(data, dict):
        raise PaymentValidationError(["Request body must be a JSON object."])

    booking = db.session.get(Booking, booking_id)
    if not booking:
        raise PaymentNotFoundError(f"Booking {booking_id} not found.")

    payment = booking.payment
    if not payment:
        raise PaymentNotFoundError(f"No payment record exists for booking {booking_id}.")

    old_status = payment.payment_status
    errors = []

    if "payment_status" in data:
        status = data["payment_status"]
        if status not in PaymentStatus.choices:
            errors.append(f"Invalid payment_status '{status}'. Choices: {', '.join(PaymentStatus.choices)}.")
        else:
            payment.payment_status = status

    if "amount" in data:
        amount = data["amount"]
        if amount is not None:
            try:
                amount_val = float(amount)
                if amount_val < 0:
                    errors.append("amount must be greater than or equal to 0.")
                else:
                    payment.amount = Decimal(str(amount_val))
            except (ValueError, TypeError):
                errors.append("amount must be a valid numeric value.")
        else:
            payment.amount = None

    if "payment_reference" in data:
        payment_reference = data["payment_reference"]
        if payment_reference is not None:
            if not isinstance(payment_reference, str) or len(payment_reference) > 100:
                errors.append("payment_reference must be a string up to 100 characters.")
            else:
                payment.payment_reference = payment_reference.strip()
        else:
            payment.payment_reference = None

    if "payment_date" in data:
        if data["payment_date"]:
            try:
                payment.payment_date = parse_date_value(data["payment_date"])
            except PaymentValidationError as pve:
                errors.extend(pve.errors)
        else:
            payment.payment_date = None

    if "remarks" in data:
        remarks = data["remarks"]
        if remarks is not None:
            if not isinstance(remarks, str) or len(remarks) > 255:
                errors.append("remarks must be a string up to 255 characters.")
            else:
                payment.remarks = remarks
        else:
            payment.remarks = None

    if errors:
        raise PaymentValidationError(errors)

    new_status = payment.payment_status
    status_changed = old_status != new_status

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        raise PaymentError(f"Database error while updating payment: {exc}")

    # Emit realtime event post-commit
    centre_id = booking.slot.centre_id if booking.slot else None
    slot_date = booking.slot.slot_date if booking.slot else None
    emit_payment_update(booking.id, centre_id, slot_date, reason="PAYMENT_UPDATED")

    try:
        from app.services.audit_service import create_audit_log
        create_audit_log(
            action="UPDATE_PAYMENT",
            entity_type="PAYMENT",
            entity_id=payment.id,
            description=f"Updated payment for booking #{booking.id} to status {new_status}",
            metadata={"booking_id": booking.id, "old_status": old_status, "new_status": new_status},
        )
    except Exception:
        pass

    try:
        if status_changed and booking.farmer and booking.farmer.user_id:
            from app.services.notification_service import create_notification
            from app.models import NotificationType

            create_notification(
                user_id=booking.farmer.user_id,
                notification_type=NotificationType.PAYMENT_UPDATE,
                title=f"Payment Status: {new_status}",
                message=f"Payment status for token {booking.token_number or ''} updated to {new_status.replace('_', ' ')}.",
                booking_id=booking.id,
            )
    except Exception:
        pass

    return payment
