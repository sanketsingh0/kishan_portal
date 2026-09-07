"""add active booking unique index

Revision ID: d8a9e0f12345
Revises: 5b01b9a44435
Create Date: 2026-09-07 20:50:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd8a9e0f12345'
down_revision = '5b01b9a44435'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1. Check for existing duplicate active bookings before creating the index
    duplicate_check = conn.execute(
        sa.text(
            "SELECT farmer_id, slot_id, COUNT(*) FROM bookings "
            "WHERE status IN ('PENDING', 'CONFIRMED') "
            "GROUP BY farmer_id, slot_id HAVING COUNT(*) > 1"
        )
    ).fetchall()

    if duplicate_check:
        dups_desc = ", ".join(f"(farmer_id={r[0]}, slot_id={r[1]}, count={r[2]})" for r in duplicate_check)
        raise RuntimeError(
            f"Migration aborted: Duplicate active bookings exist in the database: {dups_desc}. "
            "Please resolve duplicate active bookings before applying this index."
        )

    # 2. Create dialect-appropriate partial unique index
    dialect_name = conn.dialect.name
    if dialect_name == "postgresql":
        op.create_index(
            "uq_active_booking_farmer_slot",
            "bookings",
            ["farmer_id", "slot_id"],
            unique=True,
            postgresql_where=sa.text("status IN ('PENDING', 'CONFIRMED')"),
        )
    else:
        op.create_index(
            "uq_active_booking_farmer_slot",
            "bookings",
            ["farmer_id", "slot_id"],
            unique=True,
            sqlite_where=sa.text("status IN ('PENDING', 'CONFIRMED')"),
        )


def downgrade():
    op.drop_index("uq_active_booking_farmer_slot", table_name="bookings")
