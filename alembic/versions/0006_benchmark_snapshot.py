"""benchmark snapshot

A benchmark kept as its aggregated numbers only, without the games behind
them: what the demo ships instead of other players' matches. The real
database leaves it empty.

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "snapshot",
        sa.Column("cohort", sa.Text(), primary_key=True),
        sa.Column("part", sa.Text(), primary_key=True),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        schema="benchmark",
    )


def downgrade() -> None:
    op.drop_table("snapshot", schema="benchmark")
