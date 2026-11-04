"""champion details from Data Dragon

Each champion's own Data Dragon file: its abilities, and Riot's tips for
playing it and against it. The raw files go in ddragon_files, next to the
parsed rows here, one set per Data Dragon version.

Revision ID: 0005
Revises: 0004
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "champion_details",
        sa.Column("version", sa.Text(), primary_key=True),
        sa.Column("champion", sa.Text(), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("abilities", postgresql.JSONB(), nullable=False),
        sa.Column("ally_tips", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("enemy_tips", postgresql.ARRAY(sa.Text()), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("champion_details")
