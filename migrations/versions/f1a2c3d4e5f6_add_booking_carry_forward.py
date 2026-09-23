"""add booking carry-forward status + history table."""

revision = 'f1a2c3d4e5f6'
down_revision = 'c1f2a3b4d5e6'
branch_labels = None
depends_on = None


def upgrade():
    import sqlalchemy as sa
    from alembic import op
    op.create_table(
        'booking_carry_forwards',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('original_booking_id', sa.Integer(), nullable=False),
        sa.Column('new_booking_id', sa.Integer(), nullable=False),
        sa.Column('farmer_id', sa.Integer(), nullable=False),
        sa.Column('centre_id', sa.Integer(), nullable=False),
        sa.Column('original_procurement_date', sa.Date(), nullable=False),
        sa.Column('new_procurement_date', sa.Date(), nullable=False),
        sa.Column('reason', sa.String(length=100), nullable=False),
        sa.Column('carried_forward_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['original_booking_id'], ['bookings.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['new_booking_id'], ['bookings.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['farmer_id'], ['farmers.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['centre_id'], ['centres.id'],
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['carried_forward_by'], ['users.id'],
                                ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('original_booking_id',
                            name='uq_carry_forward_original_booking'),
    )
    with op.batch_alter_table('booking_carry_forwards', schema=None) as b:
        b.create_index('idx_carry_forward_original', ['original_booking_id'])
        b.create_index('idx_carry_forward_new', ['new_booking_id'])
        b.create_index('idx_carry_forward_centre', ['centre_id'])
        b.create_index('idx_carry_forward_original_date',
                       ['original_procurement_date'])
        b.create_index('idx_carry_forward_new_date', ['new_procurement_date'])
        b.create_index(b.f('ix_booking_carry_forwards_farmer_id'),
                       ['farmer_id'], unique=False)


def downgrade():
    from alembic import op
    with op.batch_alter_table('booking_carry_forwards', schema=None) as b:
        b.drop_index('ix_booking_carry_forwards_farmer_id')
        b.drop_index('idx_carry_forward_new_date')
        b.drop_index('idx_carry_forward_original_date')
        b.drop_index('idx_carry_forward_centre')
        b.drop_index('idx_carry_forward_new')
        b.drop_index('idx_carry_forward_original')
    op.drop_table('booking_carry_forwards')
