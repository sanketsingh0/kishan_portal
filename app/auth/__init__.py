"""Authentication package.

Planned design (locked stack):

    User login -> Supabase Auth (JWT) -> Flask route verifies token
    -> Flask reads role claim -> role-based authorization

Routes under /api/auth. Backend never trusts a role sent by the frontend.

No authentication is implemented yet - this module ships as an empty package.
"""