"""add token fields to booking

Revision ID: b9e8f7a65432
Revises: a8d7e6f54321
Create Date: 2026-09-03 09:16:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b9e8f7a65432'
down_revision = 'a8d7e6f54321'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.add_column(sa.Column('token_number', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('token_generated_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.create_index(batch_op.f('ix_bookings_token_number'), ['token_number'], unique=False)


def downgrade():
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_bookings_token_number'))
        batch_op.drop_column('token_generated_at')
        batch_op.drop_column('token_number')
