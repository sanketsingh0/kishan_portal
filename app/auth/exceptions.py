"""Custom exceptions for the authentication module."""


class AuthError(Exception):
    """Base exception for authentication errors."""

    def __init__(self, message: str, code: str = "AUTH_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class SupabaseConfigError(AuthError):
    """Raised when Supabase credentials are missing or invalid."""

    def __init__(self, message: str = "Supabase is not configured"):
        super().__init__(message, code="SUPABASE_CONFIG_ERROR")


class InvalidCredentialsError(AuthError):
    """Raised when login credentials are invalid."""

    def __init__(self, message: str = "Invalid email or password"):
        super().__init__(message, code="INVALID_CREDENTIALS")


class DuplicateUserError(AuthError):
    """Raised when attempting to register an already-existing email."""

    def __init__(self, message: str = "An account with this email already exists"):
        super().__init__(message, code="DUPLICATE_USER")


class TokenError(AuthError):
    """Raised when a JWT is missing, malformed, or invalid."""

    def __init__(self, message: str = "Invalid or expired token"):
        super().__init__(message, code="TOKEN_ERROR")


class UserSynchronizationError(AuthError):
    """Raised when local user record cannot be synced."""

    def __init__(self, message: str = "Failed to synchronize user record"):
        super().__init__(message, code="USER_SYNC_ERROR")
