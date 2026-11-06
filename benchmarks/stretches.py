"""Gold and CS by stretch of the game, against the lane opponent and each cohort.

A stretch is 0-10, 10-15 or 15-20 minutes. Against the lane opponent, the enemy
player in the same position, the player's own games say how much they lost in
each stretch. Against a cohort, the
gold and CS gained in each stretch are compared with the same rows and rules as
compare_to_benchmark: both sample sizes, the gap and its margin, and no benchmark
rather than a substitute.

Stretch rows never feed the findings in benchmarks/themes.py. Gold gained from 10
to 15 is the same data as gold at 10 and gold at 15, so counting it as another
metric would make one gap look like two agreeing ones.
"""

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.timeline_stats import farm_gained_by_stretch, farm_vs_opponent_by_stretch
from analytics.stats import Scope
from benchmarks.cohorts import MIN_BENCHMARK_GAMES, MIN_BENCHMARK_PLAYERS, get_cohort
from benchmarks.compare import SAMPLE_SIZE, Metric, _compare_metric, _patch_order

STRETCH_METRIC = Metric(
    "farm_gained_by_stretch",
    farm_gained_by_stretch,
    ("stretch",),
    ("avg_gold_gained", "avg_cs_gained"),
)

NOTES = (
    "A stretch counts only games that lasted to its end, so later stretches can "
    "have fewer games.",
    "Against a cohort, the player's games are limited to the cohort's patches, "
    "so their game count can differ from the lane opponent rows, which use every "
    "game in the role.",
    "Stretch rows have margins but never make a finding on their own: they're the "
    "same data as gold and CS at minutes 10, 15 and 20.",
)


async def _against_cohort(
    my_session: AsyncSession,
    benchmark_session: AsyncSession,
    puuids: list[str],
    cohort: str,
    not_for_player: str | None,
) -> dict[str, Any]:
    size = (
        await benchmark_session.execute(text(SAMPLE_SIZE), {"cohort": cohort, "champion": None})
    ).one()
    group = get_cohort(cohort)
    result: dict[str, Any] = {
        "cohort": cohort,
        "tier": group.tier,
        "audience": group.audience,
        "benchmark_games": size.games,
        "benchmark_players": size.players,
        "rows": [],
    }
    if not_for_player:
        return result | {"status": "no_benchmark", "note": f"No benchmark for this player. {not_for_player}"}
    if size.games < MIN_BENCHMARK_GAMES or size.players < MIN_BENCHMARK_PLAYERS:
        return result | {
            "status": "no_benchmark",
            "note": f"A benchmark needs {MIN_BENCHMARK_GAMES} games and {MIN_BENCHMARK_PLAYERS} players.",
        }
    patches = tuple(sorted(size.patches or [], key=_patch_order))
    mine = await farm_gained_by_stretch(
        my_session, Scope(puuids=tuple(puuids), role=group.role, patches=patches)
    )
    theirs = await farm_gained_by_stretch(benchmark_session, Scope(cohort=cohort, role=group.role))
    rows = _compare_metric(STRETCH_METRIC, mine, theirs)
    for row in rows:
        # Never part of a theme, so never part of a finding.
        del row["theme"]
    return result | {"status": "ok", "benchmark_patches": list(patches), "rows": rows}


async def farm_by_stretch(
    my_session: AsyncSession,
    benchmark_session: AsyncSession,
    puuids: list[str],
    not_for_player: dict[str, str | None],
    role: str = "JUNGLE",
) -> dict[str, Any]:
    """Gold and CS per stretch in `role`: lost to the lane opponent, and against
    each of that role's cohorts.

    `not_for_player` maps each cohort that could fit the player to why it
    doesn't, or None when it does (see cohorts.cohort_fits).
    """
    return {
        "role": role,
        "vs_opponent": await farm_vs_opponent_by_stretch(
            my_session, Scope(puuids=tuple(puuids), role=role)
        ),
        "benchmarks": {
            cohort: await _against_cohort(my_session, benchmark_session, puuids, cohort, reason)
            for cohort, reason in not_for_player.items()
            if get_cohort(cohort).role == role
        },
        "notes": list(NOTES),
    }
