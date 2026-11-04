"""Gold and CS by stretch of the game, against the enemy jungler and each cohort.

A stretch is 0-10, 10-15 or 15-20 minutes. Against the enemy jungler, the
player's own games say how much they lost in each stretch. Against a cohort, the
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

from analytics.jungle import farm_gained_by_stretch, farm_vs_jungler_by_stretch
from analytics.stats import Scope
from benchmarks.cohorts import COHORTS, MIN_BENCHMARK_GAMES, MIN_BENCHMARK_PLAYERS
from benchmarks.compare import ROLE, SAMPLE_SIZE, Metric, _compare_metric, _patch_order

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
    "so their game count can differ from the enemy jungler rows, which use every "
    "jungle game.",
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
    result: dict[str, Any] = {
        "cohort": cohort,
        "tier": COHORTS[cohort].tier,
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
    mine = await farm_gained_by_stretch(my_session, Scope(puuids=tuple(puuids), role=ROLE, patches=patches))
    theirs = await farm_gained_by_stretch(benchmark_session, Scope(cohort=cohort, role=ROLE))
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
) -> dict[str, Any]:
    """Gold and CS per stretch: lost to the enemy jungler, and against each cohort.

    `not_for_player` maps each cohort to why it doesn't fit the player, or None
    when it does (see cohorts.why_no_benchmark).
    """
    return {
        "vs_enemy_jungler": await farm_vs_jungler_by_stretch(
            my_session, Scope(puuids=tuple(puuids), role=ROLE)
        ),
        "benchmarks": {
            cohort: await _against_cohort(
                my_session, benchmark_session, puuids, cohort, not_for_player.get(cohort)
            )
            for cohort in COHORTS
        },
        "notes": list(NOTES),
    }
