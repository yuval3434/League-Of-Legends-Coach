"""player owner and rank

Several players can be synced now, so one is marked as the owner: the default
everywhere, and the one the eval runs on. Each player's current solo/duo rank
decides which benchmarks they get, so it's stored with Riot's raw response.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column("is_owner", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("players", sa.Column("rank_tier", sa.Text(), nullable=True))
    op.add_column("players", sa.Column("raw_league", postgresql.JSONB(), nullable=True))
    op.add_column(
        "players", sa.Column("rank_checked_at", sa.DateTime(timezone=True), nullable=True)
    )
    # At most one owner.
    op.create_index(
        "ix_players_one_owner",
        "players",
        ["is_owner"],
        unique=True,
        postgresql_where=sa.text("is_owner"),
    )
    # Until now only one player could be synced, so an existing one is the owner.
    op.execute(
        "UPDATE players SET is_owner = true WHERE (SELECT count(*) FROM players) = 1"
    )


def downgrade() -> None:
    op.drop_index("ix_players_one_owner", table_name="players")
    for column in ("rank_checked_at", "raw_league", "rank_tier", "is_owner"):
        op.drop_column("players", column)
