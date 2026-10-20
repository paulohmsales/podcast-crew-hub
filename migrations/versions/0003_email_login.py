"""email is the login; first login sets the password; no usernames or reset links

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_password_resets_member_id", table_name="password_resets")
    op.drop_table("password_resets")
    with op.batch_alter_table("members") as batch:
        batch.drop_constraint("uq_members_username", type_="unique")
        batch.drop_column("username")


def downgrade() -> None:
    with op.batch_alter_table("members") as batch:
        batch.add_column(sa.Column("username", sa.String(40), nullable=True))
    op.execute("UPDATE members SET username = 'membro' || id")
    with op.batch_alter_table("members") as batch:
        batch.alter_column("username", existing_type=sa.String(40), nullable=False)
        batch.create_unique_constraint("uq_members_username", ["username"])
    op.create_table(
        "password_resets",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_password_resets_member_id", "password_resets", ["member_id"])
