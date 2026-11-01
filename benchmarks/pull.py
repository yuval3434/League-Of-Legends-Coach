"""Build a cohort's benchmark sample from real matches.

Riot can't list matches by champion or rank, so the pull works in three steps:
1. Take random ladder players from the cohort's tier.
2. Queue a few of each player's recent matches. They're a way into the cohort's
   lobbies; the player themselves may not be the jungler.
3. Check each match, and keep at most one jungler who is in the cohort's tier.

Every step is saved as it goes, so a pull can stop at any point, such as when a
development key expires, and carry on from there next time.
"""

import hashlib
import logging
import random
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from benchmarks.cohorts import (
    COHORTS,
    MAX_GAMES_PER_PLAYER_CHAMPION,
    MIN_TARGET_CHAMPION_GAMES,
    TARGET_OVERALL,
    TARGET_PER_CHAMPION,
    WINDOW_DAYS,
    Cohort,
)
from benchmarks.models import CohortPlayer, PlayerRank, Sample, ScanQueue
from ingestion.models import Match, MatchParticipant, Player, RawResponse
from ingestion.parser import parse_match
from ingestion.riot_client import RiotClient, RiotRequestFailed
from ingestion.sync import fetch_raw, parse_stored_match

logger = logging.getLogger(__name__)

RANKED_SOLO = 420
DIVISIONS = ("I", "II", "III", "IV")
MAX_LADDER_PAGE = 50
MATCHES_PER_SEED_PLAYER = 6

Row = dict[str, Any]


@dataclass
class Quotas:
    """How many games the sample already has, to stop at the targets."""

    overall: int = 0
    per_champion: Counter[str] = field(default_factory=Counter)
    per_player: Counter[tuple[str, str]] = field(default_factory=Counter)

    def wants(self, jungler: Row, targets: set[str]) -> bool:
        champion = jungler["champion_name"]
        if self.per_player[(jungler["puuid"], champion)] >= (
            MAX_GAMES_PER_PLAYER_CHAMPION
        ):
            return False
        return self.overall < TARGET_OVERALL or (
            champion in targets and self.per_champion[champion] < TARGET_PER_CHAMPION
        )


def order_junglers(
    match_id: str, junglers: Iterable[Row], targets: set[str]
) -> list[Row]:
    """Put the jungler to try first at the front.

    Target champions go first, and a hash of the match decides ties. Nothing
    here may look at the result: choosing by who won would bias the win rate.
    """

    def key(jungler: Row) -> tuple[bool, str]:
        seed = f"{match_id}:{jungler['participant_id']}".encode()
        return jungler["champion_name"] not in targets, hashlib.sha256(seed).hexdigest()

    return sorted(junglers, key=key)


async def target_champions(session: AsyncSession) -> set[str]:
    """The tracked players' jungle champions with enough games to compare."""
    rows = await session.execute(
        select(MatchParticipant.champion_name)
        .join(Match, Match.match_id == MatchParticipant.match_id)
        .join(Player, Player.puuid == MatchParticipant.puuid)
        .where(MatchParticipant.team_position == "JUNGLE", Match.is_remake.is_(False))
        .group_by(MatchParticipant.champion_name)
        .having(func.count() >= MIN_TARGET_CHAMPION_GAMES)
    )
    return set(rows.scalars())


async def tracked_puuids(session: AsyncSession) -> set[str]:
    return set((await session.scalars(select(Player.puuid))).all())


async def _add_seed_players(
    session: AsyncSession, riot: RiotClient, name: str, cohort: Cohort, skip: set[str]
) -> None:
    for division in DIVISIONS:
        page = random.randint(1, MAX_LADDER_PAGE)
        entries = await riot.get_ladder_page(cohort.tier, division, page)
        rows = [
            {"cohort": name, "puuid": entry["puuid"]}
            for entry in entries
            if entry["puuid"] not in skip and not entry.get("inactive")
        ]
        if rows:
            await session.execute(
                pg_insert(CohortPlayer).values(rows).on_conflict_do_nothing()
            )
    await session.commit()


async def _queue_matches(
    session: AsyncSession,
    riot: RiotClient,
    name: str,
    cohort: Cohort,
    needed: int,
    skip: set[str],
) -> None:
    """List seed players' matches until `needed` are waiting to be checked."""
    since = int(time.time()) - WINDOW_DAYS * 86400
    empty_ladder_tries = 0
    while True:
        waiting = await session.scalar(
            select(func.count())
            .select_from(ScanQueue)
            .where(ScanQueue.cohort == name, ScanQueue.outcome.is_(None))
        )
        if waiting >= needed or empty_ladder_tries == 3:
            return

        puuid = await session.scalar(
            select(CohortPlayer.puuid)
            .where(CohortPlayer.cohort == name, CohortPlayer.listed_at.is_(None))
            .order_by(func.md5(CohortPlayer.puuid))
            .limit(1)
        )
        if puuid is None:
            await _add_seed_players(session, riot, name, cohort, skip)
            empty_ladder_tries += 1
            continue
        empty_ladder_tries = 0

        match_ids = await riot.get_match_ids(puuid, RANKED_SOLO, 100, since)
        chosen = random.sample(match_ids, min(MATCHES_PER_SEED_PLAYER, len(match_ids)))
        if chosen:
            await session.execute(
                pg_insert(ScanQueue)
                .values([{"cohort": name, "match_id": m} for m in chosen])
                .on_conflict_do_nothing()
            )
        await session.execute(
            update(CohortPlayer)
            .where(CohortPlayer.cohort == name, CohortPlayer.puuid == puuid)
            .values(listed_at=datetime.now(UTC))
        )
        await session.commit()


async def _load_quotas(session: AsyncSession, name: str) -> Quotas:
    quotas = Quotas()
    rows = await session.execute(
        select(Sample.puuid, Sample.champion_name, Sample.in_overall).where(
            Sample.cohort == name
        )
    )
    for puuid, champion, in_overall in rows:
        quotas.overall += in_overall
        quotas.per_champion[champion] += 1
        quotas.per_player[(puuid, champion)] += 1
    return quotas


async def _raw_payload(
    session: AsyncSession, riot: RiotClient, match_id: str, kind: str
) -> dict[str, Any] | None:
    """Return a stored response, fetching it first if needed."""

    async def stored() -> tuple[bool, dict[str, Any] | None]:
        row = (
            await session.execute(
                select(RawResponse.payload).where(
                    RawResponse.match_id == match_id, RawResponse.kind == kind
                )
            )
        ).first()
        return row is not None, row.payload if row else None

    found, payload = await stored()
    if not found:
        await fetch_raw(session, riot, match_id, kind)
        _, payload = await stored()
    return payload


async def _tier(session: AsyncSession, riot: RiotClient, puuid: str) -> str | None:
    row = (
        await session.execute(
            select(PlayerRank.tier).where(PlayerRank.puuid == puuid)
        )
    ).first()
    if row:
        return row.tier
    tier = await riot.get_rank(puuid)
    await session.execute(
        pg_insert(PlayerRank).values(puuid=puuid, tier=tier).on_conflict_do_nothing()
    )
    await session.commit()
    return tier


async def _check_match(
    session: AsyncSession,
    riot: RiotClient,
    name: str,
    cohort: Cohort,
    match_id: str,
    targets: set[str],
    skip: set[str],
    quotas: Quotas,
) -> str:
    """Check one match, adding to the sample if it fits. Returns the outcome."""
    payload = await _raw_payload(session, riot, match_id, "match")
    if payload is None:
        return "not_found"
    match, participants = parse_match(payload)
    if match["is_remake"]:
        return "remake"
    if skip & {p["puuid"] for p in participants}:
        return "tracked_player"
    junglers = [p for p in participants if p["team_position"] == "JUNGLE"]
    if len(junglers) != 2:
        return "no_jungler_pair"

    for jungler in order_junglers(match_id, junglers, targets):
        if not quotas.wants(jungler, targets):
            continue
        if await _tier(session, riot, jungler["puuid"]) != cohort.tier:
            continue
        if await _raw_payload(session, riot, match_id, "timeline") is None:
            return "no_timeline"
        await parse_stored_match(session, match_id)

        in_overall = quotas.overall < TARGET_OVERALL
        await session.execute(
            pg_insert(Sample)
            .values(
                cohort=name,
                match_id=match_id,
                participant_id=jungler["participant_id"],
                puuid=jungler["puuid"],
                champion_name=jungler["champion_name"],
                in_overall=in_overall,
            )
            .on_conflict_do_nothing()
        )
        quotas.overall += in_overall
        quotas.per_champion[jungler["champion_name"]] += 1
        quotas.per_player[(jungler["puuid"], jungler["champion_name"])] += 1
        return "sampled"
    return "no_fit"


async def pull_cohort(
    sessions: async_sessionmaker[AsyncSession],
    riot: RiotClient,
    name: str,
    max_matches: int,
    targets: set[str],
    skip_puuids: set[str],
) -> dict[str, int]:
    """Check matches until the cohort has `max_matches` checked in total.

    `skip_puuids` are the tracked players: they never join a cohort, and matches
    they played in aren't used. RiotAuthError stops the pull. A failed match
    stays in the queue for the next run.
    """
    cohort = COHORTS[name]
    async with sessions() as session:
        checked = await session.scalar(
            select(func.count())
            .select_from(ScanQueue)
            .where(ScanQueue.cohort == name, ScanQueue.outcome.is_not(None))
        )
        remaining = max_matches - checked
        if remaining > 0:
            await _queue_matches(session, riot, name, cohort, remaining, skip_puuids)
            quotas = await _load_quotas(session, name)
            queued = await session.scalars(
                select(ScanQueue.match_id)
                .where(ScanQueue.cohort == name, ScanQueue.outcome.is_(None))
                .order_by(func.md5(ScanQueue.match_id))
                .limit(remaining)
            )
            for match_id in queued.all():
                try:
                    outcome = await _check_match(
                        session,
                        riot,
                        name,
                        cohort,
                        match_id,
                        targets,
                        skip_puuids,
                        quotas,
                    )
                except RiotRequestFailed:
                    logger.exception("%s: fetch failed", match_id)
                    await session.rollback()
                    continue
                except (KeyError, TypeError, ValueError):
                    logger.exception("%s: parse failed", match_id)
                    await session.rollback()
                    outcome = "parse_failed"
                await session.execute(
                    update(ScanQueue)
                    .where(ScanQueue.cohort == name, ScanQueue.match_id == match_id)
                    .values(outcome=outcome)
                )
                await session.commit()

        outcomes = await session.execute(
            select(ScanQueue.outcome, func.count())
            .where(ScanQueue.cohort == name, ScanQueue.outcome.is_not(None))
            .group_by(ScanQueue.outcome)
        )
        return {outcome: count for outcome, count in outcomes}
