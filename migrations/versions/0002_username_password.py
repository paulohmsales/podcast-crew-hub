"""username/email/password login instead of personal links

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("members") as batch:
        batch.add_column(sa.Column("username", sa.String(40), nullable=True))
        batch.add_column(sa.Column("email", sa.String(200), nullable=True))
        batch.add_column(sa.Column("password_hash", sa.String(200), nullable=True))
    # Existing members get their lowercased first name (plus id if that clashes);
    # they have no password until an admin sends one.
    conn = op.get_bind()
    seen: set[str] = set()
    for member_id, name in conn.execute(sa.text("SELECT id, name FROM members ORDER BY id")).all():
        base = "".join(c for c in name.split()[0].lower() if c.isalnum()) or "membro"
        username = base if base not in seen else f"{base}{member_id}"
        seen.add(username)
        conn.execute(sa.text("UPDATE members SET username = :u WHERE id = :i"), {"u": username, "i": member_id})
    with op.batch_alter_table("members") as batch:
        batch.alter_column("username", existing_type=sa.String(40), nullable=False)
        batch.create_unique_constraint("uq_members_username", ["username"])
        batch.create_unique_constraint("uq_members_email", ["email"])
        batch.drop_index("ix_members_token")
        batch.drop_column("token")

    op.create_table(
        "sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sessions_member_id", "sessions", ["member_id"])
    op.create_table(
        "password_resets",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("member_id", sa.Integer(), sa.ForeignKey("members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_password_resets_member_id", "password_resets", ["member_id"])


def downgrade() -> None:
    op.drop_table("password_resets")
    op.drop_table("sessions")
    with op.batch_alter_table("members") as batch:
        batch.add_column(sa.Column("token", sa.String(64), nullable=True))
    op.execute("UPDATE members SET token = lower(hex(randomblob(24)))")
    with op.batch_alter_table("members") as batch:
        batch.alter_column("token", existing_type=sa.String(64), nullable=False)
        batch.create_index("ix_members_token", ["token"], unique=True)
        batch.drop_constraint("uq_members_email", type_="unique")
        batch.drop_constraint("uq_members_username", type_="unique")
        batch.drop_column("password_hash")
        batch.drop_column("email")
        batch.drop_column("username")
