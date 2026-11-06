"""Sync every tracked player on a timer, while the API runs.

A round syncs each player in the players table, owner first, through the same
sync_player as a manual sync, so every call goes through the rate limiter. A
player with no new games costs about four calls.

It runs even while a benchmark pull does: the limiter is shared and reserves
each call's slot with no wait between check and reservation, so the two
together stay within Riot's limits; a pull just slows by a few calls. It skips
a round while a manual sync runs, and stops a round at a refused key, which
ends every call until a new key is set.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ingestion.players import list_players
from ingestion.riot_client import RiotAuthError, RiotClient, RiotError, RiotNotFound
from ingestion.sync import sync_player

logger = logging.getLogger(__name__)

KEY_REFUSED = (
    "Riot refused the API key, so auto-sync is paused. Development keys expire "
    "every 24 hours: set a new one in Settings."
)


@dataclass(frozen=True)
class SyncSettings:
    region: str
    queues: list[int]
    count: int


async def sync_round(
    sessions: async_sessionmaker[AsyncSession], riot: RiotClient, how: SyncSettings
) -> dict[str, Any]:
    """Sync every tracked player once. Returns the round's outcome for the status."""
    async with sessions() as session:
        players = await list_players(session)
    synced = new_games = 0
    failed: list[str] = []
    for player in players:
        try:
            result = await sync_player(
                sessions,
                riot,
                player["game_name"],
                player["tag_line"],
                how.region,
                how.queues,
                how.count,
            )
        except RiotAuthError:
            return {"state": "key_refused", "error": KEY_REFUSED, "players": synced, "new_games": new_games}
        except RiotNotFound:
            # Riot IDs can change; a manual sync with the new one fixes it.
            failed.append(f"{player['game_name']}#{player['tag_line']} wasn't found")
            continue
        except RiotError as error:
            logger.warning("Auto-sync of one player failed: %s", error)
            failed.append(f"{player['game_name']}#{player['tag_line']}: {error}")
            continue
        synced += 1
        new_games += result.matches_parsed
    return {
        "state": "ok" if not failed else "partly_failed",
        "players": synced,
        "new_games": new_games,
        "failed": failed,
    }


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
