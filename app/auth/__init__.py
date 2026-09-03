"""Authentication package.

Supabase Auth (JWT) -> Flask verifies token -> local users record -> role authorization
Routes under /api/auth. Backend never trusts a role sent by the frontend.
"""

from app.auth.service import get_supabase_client
from app.auth.decorators import login_required, role_required, roles_required

__all__ = ["get_supabase_client", "login_required", "role_required", "roles_required"]