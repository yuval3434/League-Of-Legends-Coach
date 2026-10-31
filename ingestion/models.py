from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Player(Base):
    """A tracked player. Riot IDs can change, so the PUUID is the key."""

    __tablename__ = "players"

    puuid: Mapped[str] = mapped_column(Text, primary_key=True)
    game_name: Mapped[str] = mapped_column(Text)
    tag_line: Mapped[str] = mapped_column(Text)
    region: Mapped[str] = mapped_column(Text)
    raw_account: Mapped[dict[str, Any]] = mapped_column(JSONB)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RawResponse(Base):
    """Riot's response, saved before parsing so a parser bug costs no API quota.

    A row with no payload records a failed fetch, such as a timeline 404,
    so that sync doesn't retry it forever.
    """

    __tablename__ = "raw_responses"
    __table_args__ = (
        CheckConstraint("kind IN ('match', 'timeline')", name="kind_valid"),
    )

    match_id: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, primary_key=True)
    http_status: Mapped[int]
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Match(Base):
    __tablename__ = "matches"

    match_id: Mapped[str] = mapped_column(Text, primary_key=True)
    platform: Mapped[str] = mapped_column(Text)
    queue_id: Mapped[int] = mapped_column(index=True)
    patch: Mapped[str] = mapped_column(Text)
    game_version: Mapped[str] = mapped_column(Text)
    game_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_s: Mapped[int]
    is_remake: Mapped[bool]


class MatchParticipant(Base):
    """One row per player per match, for all 10 players.

    `puuid` has no foreign key to `players`: most participants aren't tracked.
    """

    __tablename__ = "match_participants"
    __table_args__ = (Index("ix_match_participants_puuid", "puuid"),)

    match_id: Mapped[str] = mapped_column(
        ForeignKey("matches.match_id", ondelete="CASCADE"), primary_key=True
    )
    participant_id: Mapped[int] = mapped_column(primary_key=True)
    puuid: Mapped[str] = mapped_column(Text)
    team_id: Mapped[int]
    team_position: Mapped[str] = mapped_column(Text)
    champion_id: Mapped[int]
    champion_name: Mapped[str] = mapped_column(Text)
    win: Mapped[bool]
    kills: Mapped[int]
    deaths: Mapped[int]
    assists: Mapped[int]
    lane_cs: Mapped[int]
    jungle_cs: Mapped[int]
    gold_earned: Mapped[int]
    damage_to_champions: Mapped[int]
    vision_score: Mapped[int]


class TimelineFrame(Base):
    """One player's state at one timeline frame (about one per minute).

    `minute` is the frame's position in the list. The last frame lands on the
    game's end rather than a whole minute, so use `timestamp_ms` for exact times.
    """

    __tablename__ = "timeline_frames"

    match_id: Mapped[str] = mapped_column(
        ForeignKey("matches.match_id", ondelete="CASCADE"), primary_key=True
    )
    participant_id: Mapped[int] = mapped_column(primary_key=True)
    minute: Mapped[int] = mapped_column(primary_key=True)
    timestamp_ms: Mapped[int] = mapped_column(BigInteger)
    total_gold: Mapped[int]
    xp: Mapped[int]
    level: Mapped[int]
    lane_cs: Mapped[int]
    jungle_cs: Mapped[int]
    damage_to_champions: Mapped[int | None]
    position_x: Mapped[int | None]
    position_y: Mapped[int | None]


class TimelineEvent(Base):
    """One timeline event. Fields not promoted to columns stay in `data`.

    `actor_id` and `victim_id` are NULL when no player was involved; Riot
    reports those as 0 (for example, a kill by a tower).
    """

    __tablename__ = "timeline_events"

    match_id: Mapped[str] = mapped_column(
        ForeignKey("matches.match_id", ondelete="CASCADE"), primary_key=True
    )
    event_index: Mapped[int] = mapped_column(primary_key=True)
    timestamp_ms: Mapped[int] = mapped_column(BigInteger)
    type: Mapped[str] = mapped_column(Text)
    actor_id: Mapped[int | None]
    victim_id: Mapped[int | None]
    position_x: Mapped[int | None]
    position_y: Mapped[int | None]
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
