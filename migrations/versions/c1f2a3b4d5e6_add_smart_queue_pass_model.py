"""add smart queue pass model

Revision ID: c1f2a3b4d5e6
Revises: d8a9e0f12345
Create Date: 2026-09-16 12:00:00.000000

SIH 26032 stage 1 - Smart Queue Pass (QR-based digital mandi entry pass).

Creates `smart_queue_passes`:
  * one pass per booking (UNIQUE booking_id),
  * a UNIQUE cryptographically random `secure_pass_id` that is safe to use as a
    QR payload (no phone number, farmer/booking id, token or bank data),
  * status lifecycle ACTIVE / VERIFIED / CANCELLED,
  * entry verification fields (verified_at / verified_by / verification_centre_id).

No existing table, column or row is modified by this migration.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1f2a3b4d5e6'
down_revision = 'd8a9e0f12345'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'smart_queue_passes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('booking_id', sa.Integer(), nullable=False),
        sa.Column('secure_pass_id', sa.String(length=80), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('verified_by', sa.Integer(), nullable=True),
        sa.Column('verification_centre_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['verified_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['verification_centre_id'], ['centres.id'], ondelete='SET NULL'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('booking_id', name='uq_smart_queue_pass_booking_id'),
        sa.UniqueConstraint('secure_pass_id', name='uq_smart_queue_pass_secure_id'),
    )
    with op.batch_alter_table('smart_queue_passes', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_smart_queue_passes_status'), ['status'], unique=False
        )


def downgrade():
    with op.batch_alter_table('smart_queue_passes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_smart_queue_passes_status'))

    op.drop_table('smart_queue_passes')
