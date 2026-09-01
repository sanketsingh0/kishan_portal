"""
User model.

Represents any logged-in person (farmer, staff or admin). The model is
designed to mirror a Supabase Auth identity: `supabase_user_id` will hold the
UUID of the matching Supabase Auth user once the authentication module is
implemented.

No passwords are ever stored here - Supabase Auth owns password handling.
"""

from app.extensions import db
from app.models.common import TimestampMixin, UserRole

# Shared Enum instance so every model file using it stays in sync.
UserRoleEnum = db.Enum(
    *UserRole.choices,
    name="user_role",
    native_enum=False,
    create_constraint=True,
)


class User(TimestampMixin, db.Model):
    __tablename__ = "users"  # "user" is a reserved word in PostgreSQL

    id = db.Column(db.Integer, primary_key=True)
    supabase_user_id = db.Column(db.String(255), unique=True, nullable=True)
    role = db.Column(UserRoleEnum, nullable=False, default=UserRole.FARMER, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    farmer = db.relationship("Farmer", back_populates="user", uselist=False)
    staff = db.relationship("Staff", back_populates="user", uselist=False)

    def __repr__(self) -> str:
        return (
            f"<User id={self.id} role={self.role} "
            f"supabase={self.supabase_user_id!r} active={self.is_active}>"
        )