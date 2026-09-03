"""add booking model

Revision ID: a8d7e6f54321
Revises: 32326afe2d27
Create Date: 2026-09-02 21:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8d7e6f54321'
down_revision = '32326afe2d27'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bookings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('farmer_id', sa.Integer(), nullable=False),
        sa.Column('slot_id', sa.Integer(), nullable=False),
        sa.Column('booking_date', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['farmer_id'], ['farmers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['slot_id'], ['slots.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_bookings_farmer_id'), ['farmer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_slot_id'), ['slot_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_bookings_status'), ['status'], unique=False)
        batch_op.create_index('idx_booking_farmer_slot_status', ['farmer_id', 'slot_id', 'status'], unique=False)


def downgrade():
    with op.batch_alter_table('bookings', schema=None) as batch_op:
        batch_op.drop_index('idx_booking_farmer_slot_status')
        batch_op.drop_index(batch_op.f('ix_bookings_status'))
        batch_op.drop_index(batch_op.f('ix_bookings_slot_id'))
        batch_op.drop_index(batch_op.f('ix_bookings_farmer_id'))

    op.drop_table('bookings')
