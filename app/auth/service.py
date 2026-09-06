"""Supabase Auth service layer.

Handles all interactions with Supabase Auth:
- User registration (sign up)
- User login (sign in)
- Token verification
- User logout
- Local user synchronization
"""

import httpx

from flask import current_app
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import User, Farmer, UserRole
from app.auth.exceptions import (
    AuthError,
    SupabaseConfigError,
    InvalidCredentialsError,
    DuplicateUserError,
    TokenError,
    UserSynchronizationError,
    SupabaseUnavailableError,
)

# Imported here so tests can mock this module-level reference.
from supabase import create_client
from supabase.lib.client_options import SyncClientOptions
from supabase_auth.errors import (
    AuthApiError,
    AuthRetryableError,
    AuthWeakPasswordError,
)


def _build_supabase_http_client() -> httpx.Client:
    """Build the httpx client used for all Supabase API calls.

    The supabase-auth / gotrue SDK hard-codes ``http2=True`` on the internal
    httpx client it creates.  HTTP/2 (h2 framing) over the Render ->
    Supabase (Cloudflare edge) path is unreliable and surfaces as
    ``httpx.RemoteProtocolError: illegal request line`` — h11's parser sees
    the TLS/close handshake bytes that land on the socket when the edge
    tears the HTTP/2 connection down, and mis-parses them as an HTTP/1.1
    request line.  Supabase works reliably over plain HTTP/1.1 (the default
    for every other Supabase client), so HTTP/2 is explicitly disabled here.

    A fresh client is created per call (``get_supabase_client`` returns a new
    client for every request), so no connection is ever shared across
    threads (gthread / threading-mode safe).

    Timeouts are raised above httpx's 5s default to tolerate cold Supabase
    edge starts and slow TLS setup from cloud datacenters.
    """
    return httpx.Client(
        http1=True,
        http2=False,  # force HTTP/1.1 (ALPN http/1.1) - see module docstring
        follow_redirects=True,  # keep SDK behaviour
        timeout=httpx.Timeout(30.0, connect=10.0),
        limits=httpx.Limits(
            max_connections=10,
            max_keepalive_connections=5,
            keepalive_expiry=5.0,
        ),
    )


def get_supabase_client():
    """Create a Supabase client using server-side credentials.

    Prefers the service role key (allows admin operations such as
    per-token sign-out), falling back to the anon key.

    The SDK's own httpx client is replaced with a hardened one that
    disables HTTP/2 (see ``_build_supabase_http_client``).

    Raises:
        SupabaseConfigError: if SUPABASE_URL or keys are missing.
    """
    url = (current_app.config.get("SUPABASE_URL") or "").strip().strip("'\"")
    key = (
        current_app.config.get("SUPABASE_SERVICE_ROLE_KEY")
        or current_app.config.get("SUPABASE_ANON_KEY")
    )
    if not url or not key:
        raise SupabaseConfigError(
            "Supabase URL and key are required. "
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY)."
        )
    options = SyncClientOptions(httpx_client=_build_supabase_http_client())
    return create_client(url, key, options=options)


def register_farmer(email: str, password: str, name: str, phone: str | None = None):
    """Register a new farmer through Supabase Auth.

    1. Creates a Supabase Auth user.
    2. Creates a local User record (role=FARMER).
    3. Creates a local Farmer profile.

    Returns:
        tuple: (supabase_user, supabase_session)

    Raises:
        DuplicateUserError: if the email is already registered.
        AuthError: if Supabase registration fails.
        UserSynchronizationError: if local record creation fails.
    """
    client = get_supabase_client()

    try:
        response = client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "name": name,
                    "phone": phone or "",
                    "role": UserRole.FARMER,
                }
            },
        })
    except AuthApiError as exc:
        error_msg = str(exc).lower()
        error_code = getattr(exc, "code", None)
        if (
            error_code
            in {"email_exists", "phone_exists", "user_already_exists", "identity_already_exists"}
        ) or (
            "already" in error_msg or "duplicate" in error_msg or "exists" in error_msg
        ):
            raise DuplicateUserError()
        raise AuthError(f"Registration failed: {exc}")
    except (AuthRetryableError, AuthWeakPasswordError) as exc:
        # Retryable 5xx / rate-limit responses and weak-password rejections
        # must surface as clean 4xx/5xx AuthErrors, never as raw 500s.
        raise AuthError(f"Registration failed: {exc}")
    except httpx.HTTPError as exc:
        # Transport-level failures (e.g. httpx.RemoteProtocolError from the
        # flaky HTTP/2 path, connect/read timeouts) => clean 503.
        raise SupabaseUnavailableError() from exc

    if not response.user:
        raise AuthError("Registration failed: no user returned from Supabase")

    supabase_user_id = response.user.id

    # Synchronize local user record
    try:
        local_user = User(
            supabase_user_id=supabase_user_id,
            role=UserRole.FARMER,
            is_active=True,
        )
        db.session.add(local_user)
        db.session.flush()  # get the user ID without committing

        farmer = Farmer(
            user_id=local_user.id,
            name=name,
            phone=phone,
        )
        db.session.add(farmer)
        db.session.commit()
    except IntegrityError as exc:
        # Local unique constraints (farmers.phone, users.supabase_user_id):
        # a duplicate phone/identity at the database level must be a 409,
        # not a generic 500.
        db.session.rollback()
        raise DuplicateUserError(
            "An account with this phone number already exists"
        ) from exc
    except Exception as exc:
        db.session.rollback()
        raise UserSynchronizationError(
            f"Failed to create local user record: {exc}"
        )

    return response.user, response.session

def login_user(email: str, password: str):
    """Authenticate a user through Supabase Auth.

    Args:
        email: user's email address.
        password: user's password.

    Returns:
        tuple: (supabase_user, supabase_session)

    Raises:
        InvalidCredentialsError: if credentials are invalid.
        AuthError: if Supabase authentication fails.
    """
    client = get_supabase_client()

    try:
        response = client.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
    except AuthApiError as exc:
        raise InvalidCredentialsError()
    except httpx.HTTPError as exc:
        # Transport-level failures (RemoteProtocolError, timeouts, ...) =>
        # clean 503 instead of an uncaught 500.
        raise SupabaseUnavailableError() from exc

    if not response.user or not response.session:
        raise InvalidCredentialsError()

    # Sync local user if needed (idempotent)
    local_user = _ensure_local_user(response.user)
    if not local_user.is_active:
        raise AuthError("Account disabled", code="ACCOUNT_DISABLED")

    return response.user, response.session


def _ensure_local_user(supabase_user):
    """Ensure a local User record exists for the given Supabase user.

    If no local user exists, auto-create a FARMER record. Staff and admin
    accounts must be pre-provisioned by an administrator.

    This is idempotent - safe to call multiple times.
    """
    supabase_user_id = supabase_user.id
    existing = User.query.filter_by(supabase_user_id=supabase_user_id).first()
    if existing:
        return existing

    # Auto-create as FARMER for the prototype
    user_metadata = getattr(supabase_user, "user_metadata", {}) or {}
    name = user_metadata.get("name", supabase_user.email)
    phone = user_metadata.get("phone")

    local_user = User(
        supabase_user_id=supabase_user_id,
        role=UserRole.FARMER,
        is_active=True,
    )
    db.session.add(local_user)
    db.session.flush()

    farmer = Farmer(
        user_id=local_user.id,
        name=name,
        phone=phone,
    )
    db.session.add(farmer)
    db.session.commit()

    return local_user


def verify_token(access_token: str):
    """Verify a Supabase JWT access token.

    Uses Supabase's auth server to cryptographically verify the token.
    This is NOT just a local decode - the token is validated by Supabase.

    Args:
        access_token: the JWT access token (without "Bearer " prefix).

    Returns:
        Supabase user object if valid, None otherwise.
    """
    if not access_token:
        return None

    client = get_supabase_client()
    try:
        response = client.auth.get_user(access_token)
        return response.user
    except Exception:
        return None


def logout_user(access_token: str):
    """Sign out a user by revoking their token.

    Uses the Supabase admin auth API (requires service role key) to
    invalidate the specific token. Best-effort: failure doesn't raise.

    Note: Supabase JWTs are stateless. True logout requires token
    revocation on the server. The frontend should also clear its tokens.
    """
    if not access_token:
        return

    client = get_supabase_client()
    try:
        # This requires the service role key
        if hasattr(client.auth, "admin"):
            client.auth.admin.sign_out(access_token)
    except Exception:
        # Best-effort logout - don't fail the request
        current_app.logger.debug("Server-side token revocation failed (best-effort)")


def get_local_user(supabase_user_id: str):
    """Look up a local User by their Supabase Auth user ID.

    Returns:
        User object or None.
    """
    return User.query.filter_by(supabase_user_id=supabase_user_id).first()


