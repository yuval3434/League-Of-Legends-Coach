"""champion data from Data Dragon

The champion-select helper needs each champion's tags (Tank, Mage, ...) and
Riot's 0-10 attack and magic ratings. Data Dragon's champion.json is stored as
it came, with the parsed rows next to it, one set per Data Dragon version.

Revision ID: 0004
Revises: 0003
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ddragon_files",
        sa.Column("version", sa.Text(), primary_key=True),
        sa.Column("file", sa.Text(), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_table(
        "champions",
        sa.Column("version", sa.Text(), primary_key=True),
        sa.Column("champion", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("attack", sa.Integer(), nullable=False),
        sa.Column("magic", sa.Integer(), nullable=False),
        sa.Column("defense", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("champions")
    op.drop_table("ddragon_files")
