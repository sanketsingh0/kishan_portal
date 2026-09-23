"""add farmer/centre district + tehsil for location eligibility.

Revision ID: a3b4c5d6e7f8
Revises: f1a2c3d4e5f6
Create Date: 2026-09-23

Adds nullable district/tehsil columns consumed by the farmer booking
location-eligibility rule (tehsil match OR district match). Nullable so all
existing rows remain valid; no data backfill or guessed values.
"""

revision = 'a3b4c5d6e7f8'
down_revision = 'f1a2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    import sqlalchemy as sa
    from alembic import op
    with op.batch_alter_table('farmers', schema=None) as b:
        b.add_column(sa.Column('district', sa.String(length=100), nullable=True))
        b.add_column(sa.Column('tehsil', sa.String(length=100), nullable=True))
    with op.batch_alter_table('centres', schema=None) as b:
        b.add_column(sa.Column('district', sa.String(length=100), nullable=True))
        b.add_column(sa.Column('tehsil', sa.String(length=100), nullable=True))


def downgrade():
    from alembic import op
    with op.batch_alter_table('centres', schema=None) as b:
        b.drop_column('tehsil')
        b.drop_column('district')
    with op.batch_alter_table('farmers', schema=None) as b:
        b.drop_column('tehsil')
        b.drop_column('district')
