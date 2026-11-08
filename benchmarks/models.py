"""Tables that exist only in the benchmark schema.

They declare no schema: the benchmark engine's search_path puts them, and the
ingestion tables it shares with the public schema, in `benchmark`.
"""

from datetime import datetime

from typing import Any

from sqlalchemy import DateTime, Index, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ingestion.config import Settings


class Base(DeclarativeBase):
    pass


class CohortPlayer(Base):
    """A ladder player whose recent matches are a way into a cohort's games."""

    __tablename__ = "cohort_players"

    cohort: Mapped[str] = mapped_column(Text, primary_key=True)
    puuid: Mapped[str] = mapped_column(Text, primary_key=True)
    listed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlayerRank(Base):
    """A player's solo queue tier when checked. NULL tier means unranked."""

    __tablename__ = "player_ranks"

    puuid: Mapped[str] = mapped_column(Text, primary_key=True)
    tier: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ScanQueue(Base):
    """A match to check. `outcome` stays NULL until it has been checked."""

    __tablename__ = "scan_queue"

    cohort: Mapped[str] = mapped_column(Text, primary_key=True)
    match_id: Mapped[str] = mapped_column(Text, primary_key=True)
    outcome: Mapped[str | None] = mapped_column(Text)


class Sample(Base):
    """The one jungler a benchmark uses from a match.

    The primary key allows one row per cohort per match, so two benchmark
    players can never be lane opponents and cancel each other out.
    `in_overall` marks rows counted towards the all-champion benchmark.
    """

    __tablename__ = "sample"
    __table_args__ = (Index("ix_sample_cohort_champion", "cohort", "champion_name"),)

    cohort: Mapped[str] = mapped_column(Text, primary_key=True)
    match_id: Mapped[str] = mapped_column(Text, primary_key=True)
    participant_id: Mapped[int]
    puuid: Mapped[str] = mapped_column(Text)
    champion_name: Mapped[str] = mapped_column(Text)
    in_overall: Mapped[bool]


class Snapshot(Base):
    """One part of a cohort's benchmark kept without its games: its size, or one
    metric's aggregated rows. Only the demo database has any (see snapshot.py)."""

    __tablename__ = "snapshot"

    cohort: Mapped[str] = mapped_column(Text, primary_key=True)
    # "size", or a metric's name.
    part: Mapped[str] = mapped_column(Text, primary_key=True)
    data: Mapped[Any] = mapped_column(JSONB)


def create_benchmark_engine(settings: Settings) -> AsyncEngine:
    """An engine whose every query runs in the benchmark schema."""
    return create_async_engine(
        settings.database_url,
        connect_args={"server_settings": {"search_path": "benchmark"}},
    )
