"""Compare the tracked player's stats with a benchmark cohort.

Both sides run the same stat functions on real games. Nothing here produces a
number of its own, and a sample below the floors returns no benchmark rather
than a substitute.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.jungle import kill_participation, objective_control, wards_per_minute
from analytics.stats import (
    MIN_GAMES,
    Row,
    Scope,
    deaths_by_phase,
    gold_cs_at_minute,
    lane_diff,
    overall_cs_per_minute,
    win_rates,
)
from benchmarks.cohorts import COHORTS, MIN_BENCHMARK_GAMES, MIN_BENCHMARK_PLAYERS

ROLE = "JUNGLE"


@dataclass(frozen=True)
class Metric:
    name: str
    stat: Callable[[AsyncSession, Scope], Awaitable[list[Row]]]
    keys: tuple[str, ...]
    values: tuple[str, ...]
    only: dict[str, Any] = field(default_factory=dict)
    # The count a value really rests on, when that isn't games. A share of Elder
    # dragons over 30 games may rest on 3 dragons.
    sample: str = "games"


ABSOLUTE_METRICS = (
    Metric(
        "gold_cs_at_minute",
        gold_cs_at_minute,
        ("minute",),
        ("avg_gold", "median_gold", "avg_cs", "median_cs"),
    ),
    Metric(
        "cs_per_minute",
        overall_cs_per_minute,
        (),
        ("avg_cs_per_min", "median_cs_per_min"),
    ),
    Metric(
        "deaths_by_phase",
        deaths_by_phase,
        ("phase",),
        ("avg_deaths", "median_deaths", "deaths_per_10_min"),
    ),
    Metric(
        "kill_participation",
        kill_participation,
        (),
        ("avg_kill_participation_pct", "median_kill_participation_pct"),
    ),
    Metric(
        "wards_per_minute",
        wards_per_minute,
        (),
        (
            "avg_placed_per_min",
            "median_placed_per_min",
            "avg_destroyed_per_min",
            "median_destroyed_per_min",
        ),
    ),
)

# Measured against the opponent, so they only compare at the same opponent level.
RELATIVE_METRICS = (
    Metric(
        "lane_diff",
        lane_diff,
        ("minute", "result"),
        ("avg_gold_diff", "median_gold_diff", "avg_cs_diff", "median_cs_diff"),
    ),
    Metric("win_rate", win_rates, (), ("win_rate_pct",), {"dimension": "role"}),
    Metric(
        "objective_share",
        objective_control,
        ("objective",),
        ("team_share_pct",),
        sample="objectives",
    ),
)

ZERO_SUM_NOTE = (
    "Across all champions, a same-rank benchmark's gold difference and win rate "
    "sit near 0 and 50% by construction: every game has one winner and the two "
    "junglers' differences mirror each other."
)

SAMPLE_SIZE = """
SELECT count(*) AS games,
       count(DISTINCT s.puuid) AS players,
       array_agg(DISTINCT m.patch) AS patches
FROM sample s
JOIN matches m ON m.match_id = s.match_id
WHERE s.cohort = :cohort
  AND (CAST(:champion AS text) IS NULL OR s.champion_name = :champion)
  AND (CAST(:champion AS text) IS NOT NULL OR s.in_overall)
"""


def _patch_order(patch: str) -> list[int]:
    return [int(part) for part in patch.split(".")]


def _keyed(rows: list[Row], metric: Metric) -> dict[tuple[Any, ...], Row]:
    return {
        tuple(row[key] for key in metric.keys): row
        for row in rows
        if all(row[k] == v for k, v in metric.only.items())
    }


def _compare_metric(metric: Metric, mine: list[Row], theirs: list[Row]) -> list[Row]:
    my_rows = _keyed(mine, metric)
    their_rows = _keyed(theirs, metric)
    rows = []
    for key in sorted(my_rows.keys() | their_rows.keys(), key=str):
        my_row, their_row = my_rows.get(key), their_rows.get(key)
        my_sample = my_row[metric.sample] if my_row else 0
        benchmark_sample = their_row[metric.sample] if their_row else 0
        enough = benchmark_sample >= MIN_BENCHMARK_GAMES
        for value in metric.values:
            rows.append(
                {
                    "metric": metric.name,
                    **dict(zip(metric.keys, key)),
                    "value": value,
                    "sample_unit": metric.sample,
                    "my_value": my_row[value] if my_row else None,
                    "my_sample": my_sample,
                    "my_low_sample": my_sample < MIN_GAMES,
                    "benchmark_value": their_row[value] if enough else None,
                    "benchmark_sample": benchmark_sample,
                    "status": "ok" if enough else "no_benchmark",
                }
            )
    return rows


async def compare(
    my_session: AsyncSession,
    benchmark_session: AsyncSession,
    puuids: list[str],
    cohort: str,
    champion: str | None = None,
) -> dict[str, Any]:
    """Compare jungle stats with `cohort`, for one champion or all of them.

    Every row shows the sample size on both sides. All-champion comparisons use
    the player's games on the benchmark's patches. Champion comparisons use all
    the player's games on that champion, because few are on recent patches, and
    a note says so.
    """
    size = (
        await benchmark_session.execute(
            text(SAMPLE_SIZE), {"cohort": cohort, "champion": champion}
        )
    ).one()
    patches = sorted(size.patches or [], key=_patch_order)
    result: dict[str, Any] = {
        "cohort": cohort,
        "tier": COHORTS[cohort].tier,
        "champion": champion,
        "role": ROLE,
        "benchmark_games": size.games,
        "benchmark_players": size.players,
        "benchmark_patches": patches,
        "rows": [],
        "notes": [],
    }
    if size.games < MIN_BENCHMARK_GAMES or size.players < MIN_BENCHMARK_PLAYERS:
        result["status"] = "no_benchmark"
        result["notes"].append(
            f"A benchmark needs {MIN_BENCHMARK_GAMES} games and "
            f"{MIN_BENCHMARK_PLAYERS} players. Don't substitute another number."
        )
        return result

    result["status"] = "ok"
    metrics = ABSOLUTE_METRICS
    if COHORTS[cohort].relative_stats:
        metrics += RELATIVE_METRICS
        if champion is None:
            result["notes"].append(ZERO_SUM_NOTE)
    else:
        result["not_comparable"] = [m.name for m in RELATIVE_METRICS]
        result["notes"].append(
            "Gold difference, win rate and objective share aren't compared: "
            "this cohort's opponents are a different level from the player's."
        )
    if champion:
        result["notes"].append(
            "The player's side covers all their games on this champion. "
            f"The benchmark covers patches {', '.join(patches)}."
        )

    my_scope = Scope(
        puuids=tuple(puuids),
        role=ROLE,
        champion=champion,
        patches=None if champion else tuple(patches),
    )
    benchmark_scope = Scope(cohort=cohort, role=ROLE, champion=champion)
    for metric in metrics:
        result["rows"] += _compare_metric(
            metric,
            await metric.stat(my_session, my_scope),
            await metric.stat(benchmark_session, benchmark_scope),
        )
    return result
