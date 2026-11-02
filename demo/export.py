"""Export the demo dataset from the real database. Free: no API calls.

Run with `uv run python -m demo.export`. It takes the tracked player's 12 most
recent jungle games, chosen by that rule rather than by hand, anonymizes them,
and writes nothing if any original identity is left anywhere in the output.
"""

import asyncio
import gzip
import json
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from demo.anonymize import (
    ME,
    MY_NAME,
    TAG,
    Anonymizer,
    champion_names,
    find_originals,
    offset_for,
    originals,
)
from ingestion.config import Settings

DATASET = Path(__file__).parent / "matches.json.gz"
MATCHES = 12

CHOOSE = """
SELECT m.match_id
FROM matches m
JOIN match_participants p ON p.match_id = m.match_id
JOIN players pl ON pl.puuid = p.puuid
WHERE p.team_position = 'JUNGLE' AND NOT m.is_remake
  AND EXISTS (SELECT 1 FROM raw_responses r WHERE r.match_id = m.match_id AND r.kind = 'timeline')
ORDER BY m.game_start_at DESC
LIMIT :n
"""


async def main() -> int:
    engine = create_async_engine(Settings().database_url)
    async with engine.connect() as connection:
        players = (await connection.execute(text("SELECT raw_account FROM players"))).scalars().all()
        if len(players) != 1:
            print(f"Expected one tracked player, found {len(players)}.")
            return 1
        [account] = players
        match_ids = (await connection.execute(text(CHOOSE), {"n": MATCHES})).scalars().all()
        raw = await connection.execute(
            text("SELECT match_id, kind, payload FROM raw_responses WHERE match_id = ANY(:ids)"),
            {"ids": list(match_ids)},
        )
        payloads: dict[str, dict] = {}
        for match_id, kind, payload in raw:
            payloads.setdefault(match_id, {})[kind] = payload
    await engine.dispose()

    real = sorted(
        (payloads[m] for m in match_ids), key=lambda p: p["match"]["info"]["gameStartTimestamp"]
    )
    anon = Anonymizer(account["puuid"], offset_for([p["match"] for p in real]))
    banned: set = set()
    matches = []
    for number, p in enumerate(real, start=1):
        banned |= originals(p["match"], p["timeline"], account)
        matches.append(
            {"match": anon.walk(p["match"], number), "timeline": anon.walk(p["timeline"], number)}
        )
    dataset = {"player": {"puuid": ME, "gameName": MY_NAME, "tagLine": TAG}, "matches": matches}

    # A player named after a champion: the word stays, as the champion.
    named_like_champions = banned & champion_names([p["match"] for p in real])
    banned -= named_like_champions
    left = find_originals(dataset, banned)
    if left:
        print(f"Not written: {len(left)} original values are still in the output.")
        return 1
    data = json.dumps(dataset, sort_keys=True, separators=(",", ":")).encode()
    # A fixed mtime keeps the file identical when nothing changed.
    DATASET.write_bytes(gzip.compress(data, mtime=0))
    print(
        f"{DATASET}: {len(matches)} matches, {len(anon.puuids)} other players, "
        f"{len(banned)} original values checked ({len(named_like_champions)} names that are "
        f"also champion names exempted), {DATASET.stat().st_size / 1e6:.1f} MB"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
