"""Load the demo dataset into its own database. Free: no Riot or model calls.

Run with `uv run python -m demo.load` while the `db` container is up. It always
loads into `lolcoach_demo`, never the real database, and can be run again: it
replaces the demo data. The raw responses are stored and then parsed by the same
code a real sync uses.
"""

import asyncio
import gzip
import json
import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import delete, insert, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ingestion.config import Settings
from ingestion.models import Match, Player, RawResponse
from ingestion.sync import parse_stored_match

DEMO_DB = "lolcoach_demo"
DATASET = Path(__file__).parent / "matches.json.gz"
ROOT = Path(__file__).parent.parent


async def create_database(settings: Settings) -> None:
    engine = create_async_engine(settings.database_url, isolation_level="AUTOCOMMIT")
    async with engine.connect() as connection:
        exists = await connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": DEMO_DB}
        )
        if not exists:
            await connection.execute(text(f"CREATE DATABASE {DEMO_DB}"))
    await engine.dispose()


def migrate() -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env={**os.environ, "POSTGRES_DB": DEMO_DB},
        check=True,
    )


async def load(settings: Settings) -> int:
    data = json.loads(gzip.decompress(DATASET.read_bytes()))
    sessions = async_sessionmaker(create_async_engine(settings.database_url))
    async with sessions() as session:
        await session.execute(delete(RawResponse).where(RawResponse.match_id.like("DEMO1_%")))
        await session.execute(delete(Match).where(Match.match_id.like("DEMO1_%")))
        await session.execute(delete(Player))
        player = data["player"]
        session.add(
            Player(
                puuid=player["puuid"],
                game_name=player["gameName"],
                tag_line=player["tagLine"],
                region="euw1",
                raw_account=player,
            )
        )
        for m in data["matches"]:
            match_id = m["match"]["metadata"]["matchId"]
            await session.execute(
                insert(RawResponse),
                [
                    {"match_id": match_id, "kind": kind, "http_status": 200, "payload": m[kind]}
                    for kind in ("match", "timeline")
                ],
            )
        await session.commit()
        for m in data["matches"]:
            await parse_stored_match(session, m["match"]["metadata"]["matchId"])
    return len(data["matches"])


async def main() -> int:
    base = Settings()
    await create_database(base)
    migrate()
    loaded = await load(base.model_copy(update={"postgres_db": DEMO_DB}))
    print(f"Loaded {loaded} demo matches into {DEMO_DB}.")
    print(f"To use them, set POSTGRES_DB={DEMO_DB} in .env and restart the API.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
