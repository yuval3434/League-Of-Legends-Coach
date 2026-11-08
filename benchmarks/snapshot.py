"""A benchmark's aggregated numbers, kept without the games behind them.

The demo ships no other player's games, only what a comparison reads from a
benchmark: each metric's averages, medians, margins and sample sizes, and the
cohort's game, player and patch counts. `build` makes one from a real cohort;
`compare` and `coverage` read it when a cohort has no games of its own. The
real database never has a snapshot, so there a comparison is computed as before.
"""

import json
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.stats import Scope
from benchmarks.cohorts import get_cohort
from benchmarks.models import Snapshot

SIZE = "size"
# Fields a snapshot may never hold: they would identify a player or a game.
IDENTIFYING = ("puuid", "match_id", "game_name", "tag_line", "summoner", "riot_id")


def _plain(value: Any) -> Any:
    """Postgres numbers as JSON ones: a Decimal becomes a float."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    return value


def identifying_keys(data: Any) -> list[str]:
    """Every key in `data` that names a player or a game."""
    found: list[str] = []
    if isinstance(data, dict):
        for key, value in data.items():
            if any(word in key.lower() for word in IDENTIFYING):
                found.append(key)
            found += identifying_keys(value)
    elif isinstance(data, list):
        for value in data:
            found += identifying_keys(value)
    return found


async def build(session: AsyncSession, cohort: str) -> dict[str, Any]:
    """One cohort's all-champion benchmark, as `compare` reads it, from its games."""
    # Imported here: compare imports this module to read snapshots.
    from benchmarks.compare import ROLE_METRICS, SAMPLE_SIZE

    group = get_cohort(cohort)
    size = (await session.execute(text(SAMPLE_SIZE), {"cohort": cohort, "champion": None})).one()
    absolute, relative = ROLE_METRICS[group.role]
    scope = Scope(cohort=cohort, role=group.role)
    metrics = {}
    for metric in (*absolute, *relative):
        assert metric.name not in metrics, f"two metrics called {metric.name}"
        rows = await metric.stat(session, scope)
        # Only the rows a comparison reads: win_rate's role row, not each champion's.
        kept = [row for row in rows if all(row[k] == v for k, v in metric.only.items())]
        metrics[metric.name] = _plain(kept)
    snapshot = {
        "cohort": cohort,
        SIZE: {"games": size.games, "players": size.players, "patches": sorted(size.patches or [])},
        "metrics": metrics,
    }
    if identifying_keys(snapshot):
        raise ValueError(f"A snapshot can't hold {identifying_keys(snapshot)}")
    return snapshot


async def save(session: AsyncSession, snapshots: list[dict[str, Any]]) -> None:
    """Replace every stored snapshot with these."""
    await session.execute(delete(Snapshot))
    rows = []
    for snap in snapshots:
        if identifying_keys(snap):
            raise ValueError(f"A snapshot can't hold {identifying_keys(snap)}")
        rows.append({"cohort": snap["cohort"], "part": SIZE, "data": snap[SIZE]})
        rows += [
            {"cohort": snap["cohort"], "part": name, "data": metric_rows}
            for name, metric_rows in snap["metrics"].items()
        ]
    if rows:
        await session.execute(insert(Snapshot), rows)
    await session.commit()


async def read(session: AsyncSession, cohort: str) -> dict[str, Any] | None:
    """A cohort's snapshot: its size and each metric's rows, or None if it has none."""
    parts = dict(
        (await session.execute(select(Snapshot.part, Snapshot.data).where(Snapshot.cohort == cohort))).all()
    )
    if SIZE not in parts:
        return None
    size = parts.pop(SIZE)
    return {"cohort": cohort, SIZE: size, "metrics": parts}


async def sizes(session: AsyncSession) -> dict[str, dict[str, int]]:
    """Every snapshot's games and players, by cohort."""
    rows = await session.execute(select(Snapshot.cohort, Snapshot.data).where(Snapshot.part == SIZE))
    return {cohort: {"games": data["games"], "players": data["players"]} for cohort, data in rows}


def dumps(data: Any) -> str:
    return json.dumps(data, sort_keys=True, indent=1) + "\n"
