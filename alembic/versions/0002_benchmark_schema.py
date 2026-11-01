"""benchmark schema

Other players' games live in their own schema, so they can't mix with the
tracked player's. The first five tables copy the public ones, which lets the
parser and analytics run on them unchanged.

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

COPIED_TABLES = (
    "raw_responses",
    "matches",
    "match_participants",
    "timeline_frames",
    "timeline_events",
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA benchmark")
    for table in COPIED_TABLES:
        op.execute(f"CREATE TABLE benchmark.{table} (LIKE public.{table} INCLUDING ALL)")
    # LIKE doesn't copy foreign keys, and parsing relies on the cascade.
    for table in ("match_participants", "timeline_frames", "timeline_events"):
        op.execute(
            f"ALTER TABLE benchmark.{table} ADD FOREIGN KEY (match_id) "
            "REFERENCES benchmark.matches (match_id) ON DELETE CASCADE"
        )

    op.create_table(
        "cohort_players",
        sa.Column("cohort", sa.Text(), primary_key=True),
        sa.Column("puuid", sa.Text(), primary_key=True),
        sa.Column("listed_at", sa.DateTime(timezone=True)),
        schema="benchmark",
    )
    op.create_table(
        "player_ranks",
        sa.Column("puuid", sa.Text(), primary_key=True),
        sa.Column("tier", sa.Text()),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        schema="benchmark",
    )
    op.create_table(
        "scan_queue",
        sa.Column("cohort", sa.Text(), primary_key=True),
        sa.Column("match_id", sa.Text(), primary_key=True),
        sa.Column("outcome", sa.Text()),
        schema="benchmark",
    )
    op.create_table(
        "sample",
        sa.Column("cohort", sa.Text(), primary_key=True),
        sa.Column("match_id", sa.Text(), primary_key=True),
        sa.Column("participant_id", sa.Integer(), nullable=False),
        sa.Column("puuid", sa.Text(), nullable=False),
        sa.Column("champion_name", sa.Text(), nullable=False),
        sa.Column("in_overall", sa.Boolean(), nullable=False),
        schema="benchmark",
    )
    op.create_index(
        "ix_sample_cohort_champion",
        "sample",
        ["cohort", "champion_name"],
        schema="benchmark",
    )


def downgrade() -> None:
    op.execute("DROP SCHEMA benchmark CASCADE")
