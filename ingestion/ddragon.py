"""Champion static data from Riot's Data Dragon.

Data Dragon is a public file CDN, not the Riot API: it takes no key and has no
rate limit, so these requests don't go through the rate limiter. champion.json
is stored as it came (ddragon_files) next to the parsed rows (champions), one
set per Data Dragon version, so champion tags never change under a running app
without a new version being stored.
"""

from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ingestion.models import Champion, DdragonFile

VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
CHAMPIONS_URL = "https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion.json"
CHAMPIONS_FILE = "champion.json"

# Fetches a URL and returns its JSON. Tests pass a fake, so they make no requests.
GetJson = Callable[[str], Awaitable[Any]]


async def get_json(url: str) -> Any:
    async with httpx.AsyncClient(timeout=10.0) as http:
        response = await http.get(url)
        response.raise_for_status()
        return response.json()


def parse_champions(version: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """champion.json's `data` as rows: id, display name, tags and Riot's ratings."""
    return [
        {
            "version": version,
            "champion": entry["id"],
            "name": entry["name"],
            "tags": list(entry["tags"]),
            "attack": entry["info"]["attack"],
            "magic": entry["info"]["magic"],
            "defense": entry["info"]["defense"],
        }
        for entry in payload["data"].values()
    ]


async def refresh_champions(session: AsyncSession, fetch: GetJson = get_json) -> str:
    """Store the latest version's champions if they aren't stored yet; return it."""
    version = (await fetch(VERSIONS_URL))[0]
    stored = await session.scalar(
        select(DdragonFile.version).where(
            DdragonFile.version == version, DdragonFile.file == CHAMPIONS_FILE
        )
    )
    if stored:
        return version
    payload = await fetch(CHAMPIONS_URL.format(version=version))
    # Raw first, so a parser bug can be fixed without fetching again.
    await session.execute(
        insert(DdragonFile).values(version=version, file=CHAMPIONS_FILE, payload=payload)
    )
    await session.execute(insert(Champion).values(parse_champions(version, payload)))
    await session.commit()
    return version


async def load_champions(session: AsyncSession) -> tuple[str | None, dict[str, Champion]]:
    """The most recently stored version's champions, by id. (None, {}) if none."""
    version = await session.scalar(
        select(DdragonFile.version)
        .where(DdragonFile.file == CHAMPIONS_FILE)
        .order_by(DdragonFile.fetched_at.desc())
        .limit(1)
    )
    if version is None:
        return None, {}
    rows = await session.scalars(select(Champion).where(Champion.version == version))
    return version, {row.champion: row for row in rows}
