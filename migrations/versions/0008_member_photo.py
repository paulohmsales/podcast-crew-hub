"""member photo

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-20 16:30:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('members', schema=None) as batch_op:
        batch_op.add_column(sa.Column('photo', sa.String(length=80), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('members', schema=None) as batch_op:
        batch_op.drop_column('photo')
