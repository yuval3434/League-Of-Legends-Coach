"""Fetch a player's matches and store them, raw first and then parsed.

Safe to run again after an interruption: it fetches only what's missing.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ingestion.models import (
    Match,
    MatchParticipant,
    Player,
    RawResponse,
    TimelineEvent,
    TimelineFrame,
)
from ingestion.parser import parse_match, parse_timeline
from ingestion.riot_client import RiotClient, RiotNotFound, RiotRequestFailed

logger = logging.getLogger(__name__)

KINDS = ("match", "timeline")


@dataclass
class SyncResult:
    puuid: str
    matches_found: int = 0
    matches_parsed: int = 0
    matches_failed: int = 0


def _newest_first(match_ids: set[str]) -> list[str]:
    """Sort 'EUW1_123' style IDs by their number, which rises over time."""
    return sorted(match_ids, key=lambda m: int(m.rsplit("_", 1)[1]), reverse=True)


async def _save_player(
    session: AsyncSession, account: dict[str, Any], region: str
) -> None:
    values = {
        "puuid": account["puuid"],
        "game_name": account["gameName"],
        "tag_line": account["tagLine"],
        "region": region,
        "raw_account": account,
    }
    statement = pg_insert(Player).values(values)
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[Player.puuid],
            set_={
                "game_name": statement.excluded.game_name,
                "tag_line": statement.excluded.tag_line,
                "raw_account": statement.excluded.raw_account,
            },
        )
    )
    await session.commit()


async def _fetch_raw(
    session: AsyncSession, riot: RiotClient, match_id: str, kind: str
) -> None:
    """Fetch one response and save it. A 404 is saved too, so it isn't retried."""
    fetch = riot.get_match if kind == "match" else riot.get_timeline
    try:
        payload, status = await fetch(match_id), 200
    except RiotNotFound:
        logger.warning("%s: %s not found", match_id, kind)
        payload, status = None, 404

    await session.execute(
        pg_insert(RawResponse)
        .values(match_id=match_id, kind=kind, http_status=status, payload=payload)
        .on_conflict_do_nothing()
    )
    await session.commit()


async def parse_stored_match(session: AsyncSession, match_id: str) -> bool:
    """Rebuild a match's parsed rows from its raw responses.

    Replaces any existing rows, so it also serves to re-parse after a parser
    fix without calling Riot. Returns False if there's no match payload.
    """
    rows = await session.execute(
        select(RawResponse.kind, RawResponse.payload).where(
            RawResponse.match_id == match_id
        )
    )
    raw = {row.kind: row.payload for row in rows}
    if not raw.get("match"):
        return False

    match, participants = parse_match(raw["match"])
    frames, events = parse_timeline(raw["timeline"]) if raw.get("timeline") else ([], [])

    await session.execute(delete(Match).where(Match.match_id == match_id))
    await session.execute(insert(Match), [match])
    await session.execute(insert(MatchParticipant), participants)
    if frames:
        await session.execute(insert(TimelineFrame), frames)
    if events:
        await session.execute(insert(TimelineEvent), events)
    await session.commit()
    return True


async def sync_player(
    sessions: async_sessionmaker[AsyncSession],
    riot: RiotClient,
    game_name: str,
    tag_line: str,
    region: str,
    queues: list[int],
    count: int,
) -> SyncResult:
    """Sync a player's newest `count` matches across `queues`.

    Calls run one at a time, so only one is ever in flight while the limiter
    is still learning an endpoint's limits. RiotAuthError stops the whole sync;
    other failures skip that match, and the next sync picks it up.
    """
    account = await riot.get_account(game_name, tag_line)
    puuid = account["puuid"]

    match_ids: set[str] = set()
    for queue in queues:
        match_ids.update(await riot.get_match_ids(puuid, queue, count))
    newest = _newest_first(match_ids)[:count]
    result = SyncResult(puuid=puuid, matches_found=len(newest))

    async with sessions() as session:
        await _save_player(session, account, region)

        stored = await session.execute(
            select(RawResponse.match_id, RawResponse.kind).where(
                RawResponse.match_id.in_(newest)
            )
        )
        have_raw = {(row.match_id, row.kind) for row in stored}
        parsed = await session.scalars(
            select(Match.match_id).where(Match.match_id.in_(newest))
        )
        already_parsed = set(parsed.all())

        for match_id in newest:
            try:
                for kind in KINDS:
                    if (match_id, kind) not in have_raw:
                        await _fetch_raw(session, riot, match_id, kind)
                if match_id in already_parsed:
                    continue
                if await parse_stored_match(session, match_id):
                    result.matches_parsed += 1
                else:
                    result.matches_failed += 1
            except RiotRequestFailed:
                logger.exception("%s: fetch failed", match_id)
                await session.rollback()
                result.matches_failed += 1
            except (KeyError, TypeError, ValueError):
                # Raw data is safe; fix the parser and re-parse without Riot.
                logger.exception("%s: parse failed", match_id)
                await session.rollback()
                result.matches_failed += 1

        await session.execute(
            update(Player)
            .where(Player.puuid == puuid)
            .values(last_synced_at=datetime.now(UTC))
        )
        await session.commit()

    return result
