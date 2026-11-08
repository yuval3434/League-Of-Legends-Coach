"""Export the demo's benchmark snapshot from the real database. Free: no API calls.

Run with `uv run python -m demo.export_benchmark`. It keeps, for each cohort the
tracked player is compared with, only what a comparison reads: each metric's
averages, medians, margins and sample sizes, and the cohort's game, player and
patch counts. It writes nothing if a player ID or match ID from the cohort's games
appears anywhere in the output.
"""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from benchmarks.cohorts import cohorts_for
from benchmarks.models import create_benchmark_engine
from benchmarks.snapshot import build, dumps
from ingestion.config import Settings

SNAPSHOT = Path(__file__).parent / "benchmark.json"
# The demo's games are the tracked player's jungle games.
ROLE = "JUNGLE"


async def main() -> int:
    settings = Settings()
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        ranks = (
            await connection.execute(text("SELECT rank_tier FROM players WHERE is_owner"))
        ).scalars().all()
    await engine.dispose()
    if len(ranks) != 1 or ranks[0] is None:
        print(f"Expected one ranked owner, found {ranks}.")
        return 1
    [rank] = ranks

    benchmark = async_sessionmaker(create_benchmark_engine(settings))
    cohorts = cohorts_for(rank, ROLE)
    async with benchmark() as session:
        snapshots = [await build(session, cohort) for cohort in cohorts]
        ids = await session.execute(
            text("SELECT puuid, match_id FROM sample WHERE cohort = ANY(:cohorts)"),
            {"cohorts": cohorts},
        )
        banned = {value for row in ids for value in row}

    output = dumps({"rank": rank, "snapshots": snapshots})
    left = [value for value in banned if value in output]
    if left:
        print(f"Not written: {len(left)} player or match IDs are in the output.")
        return 1
    SNAPSHOT.write_text(output, encoding="utf-8")
    sizes = ", ".join(f"{s['cohort']} {s['size']['games']} games" for s in snapshots)
    print(f"{SNAPSHOT}: {sizes}; {len(banned)} IDs checked, none in the output.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
