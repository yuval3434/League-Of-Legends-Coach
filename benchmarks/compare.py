"""Compare the tracked player's stats with a benchmark cohort.

Both sides run the same stat functions on real games. The only numbers added
here are the gap between them and its margin, so the LLM never has to work them
out. A sample below the floors returns no benchmark rather than a substitute.
"""

import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.timeline_stats import (
    damage_share,
    kill_participation,
    lane_plates,
    objective_control,
    roams,
    solo_kills,
    wards_per_minute,
)
from analytics.stats import (
    MIN_GAMES,
    Row,
    Scope,
    deaths_by_phase,
    gold_cs_at_minute,
    lane_diff,
    overall_cs_per_minute,
    player_coverage,
    win_rates,
)
from benchmarks.cohorts import (
    MIN_BENCHMARK_GAMES,
    MIN_BENCHMARK_PLAYERS,
    ROLE_GROUPS,
    get_cohort,
)
from benchmarks import snapshot
from benchmarks.themes import summarize_themes

# A lone gap this many times its margin is too big to put down to chance.
STRONG_GAP_MULTIPLE = 2


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
    theme: str | None = None
    higher_is_better: bool = True
    # Values shown beside the theme but never judged: their rows get no
    # clear_gap, so they can't make or support a finding.
    context: tuple[str, ...] = ()


JUNGLE_ABSOLUTE = (
    Metric(
        "gold_cs_at_minute",
        gold_cs_at_minute,
        ("minute",),
        ("avg_gold", "median_gold", "avg_cs", "median_cs"),
        theme="economy",
    ),
    Metric(
        "cs_per_minute",
        overall_cs_per_minute,
        (),
        ("avg_cs_per_min", "median_cs_per_min"),
        theme="economy",
    ),
    Metric(
        "deaths_by_phase",
        deaths_by_phase,
        ("phase",),
        ("avg_deaths", "median_deaths", "deaths_per_10_min"),
        theme="deaths",
        higher_is_better=False,
    ),
    Metric(
        "kill_participation",
        kill_participation,
        (),
        ("avg_kill_participation_pct", "median_kill_participation_pct"),
        theme="fights",
    ),
    Metric(
        "wards_per_minute",
        wards_per_minute,
        (),
        (
            "avg_control_placed_per_min",
            "median_control_placed_per_min",
            "avg_destroyed_per_min",
            "median_destroyed_per_min",
            "avg_trinket_placed_per_min",
            "oracle_lens_pct",
            "avg_vision_score_per_min",
        ),
        theme="vision",
        # Trinket wards mostly measure trinket choice, and vision score's formula
        # isn't public: see DECISIONS.md.
        context=("avg_trinket_placed_per_min", "oracle_lens_pct", "avg_vision_score_per_min"),
    ),
)

# Measured against the opponent, so they only compare at the same opponent level.
JUNGLE_RELATIVE = (
    Metric(
        "lane_diff",
        lane_diff,
        ("minute", "result"),
        ("avg_gold_diff", "median_gold_diff", "avg_cs_diff", "median_cs_diff"),
        theme="economy",
    ),
    Metric("win_rate", win_rates, (), ("win_rate_pct",), {"dimension": "role"}),
    Metric(
        "objective_share",
        objective_control,
        ("objective",),
        ("team_share_pct",),
        sample="objectives",
        theme="objectives",
    ),
)

# The other roles. A metric whose values are all context is shown, never judged.
GOLD_CS, CS_PER_MINUTE, DEATHS, KILL_PARTICIPATION, WARDS = JUNGLE_ABSOLUTE
LANE_DIFF, WIN_RATE, _OBJECTIVE_SHARE = JUNGLE_RELATIVE


def _context(metric: Metric) -> Metric:
    return replace(metric, context=metric.values)


SOLO_KILLS = Metric(
    "solo_kills", solo_kills, (), ("avg_solo_kills", "avg_solo_kills_before_15"), theme="fights"
)
LANE_PLATES = Metric(
    "lane_plates",
    lane_plates,
    (),
    ("avg_lane_plates", "avg_my_plates"),
    theme="objectives",
    # Minions take many plates, so who last hit them is context.
    context=("avg_my_plates",),
)
DAMAGE_SHARE = Metric(
    "damage_share",
    damage_share,
    (),
    ("avg_damage_share_pct", "median_damage_share_pct"),
    theme="fights",
)
ROAMS = _context(Metric("roams", roams, (), ("avg_roam_takedowns",), theme="fights"))
# A support's own wards include the support item's, so all placed wards are judged.
SUPPORT_WARDS = Metric(
    "wards_per_minute",
    wards_per_minute,
    (),
    (
        "avg_placed_per_min",
        "median_placed_per_min",
        "avg_control_placed_per_min",
        "median_control_placed_per_min",
        "avg_destroyed_per_min",
        "median_destroyed_per_min",
        "avg_support_item_placed_per_min",
        "oracle_lens_pct",
        "avg_vision_score_per_min",
    ),
    theme="vision",
    context=("avg_support_item_placed_per_min", "oracle_lens_pct", "avg_vision_score_per_min"),
)

# Per role: (absolute metrics, compared with any rank; relative ones, peers only).
ROLE_METRICS: dict[str, tuple[tuple[Metric, ...], tuple[Metric, ...]]] = {
    "JUNGLE": (JUNGLE_ABSOLUTE, JUNGLE_RELATIVE),
    "TOP": (
        (GOLD_CS, CS_PER_MINUTE, DEATHS, KILL_PARTICIPATION, WARDS, SOLO_KILLS, LANE_PLATES,
         _context(DAMAGE_SHARE)),
        (LANE_DIFF, WIN_RATE),
    ),
    "MIDDLE": (
        (GOLD_CS, CS_PER_MINUTE, DEATHS, KILL_PARTICIPATION, WARDS, DAMAGE_SHARE, ROAMS),
        (LANE_DIFF, WIN_RATE),
    ),
    "BOTTOM": (
        (GOLD_CS, CS_PER_MINUTE, DEATHS, _context(KILL_PARTICIPATION), WARDS, LANE_PLATES),
        (LANE_DIFF, WIN_RATE),
    ),
    # Supports aren't meant to farm, so gold and CS are context.
    "UTILITY": (
        (_context(GOLD_CS), _context(CS_PER_MINUTE), DEATHS, KILL_PARTICIPATION, SUPPORT_WARDS),
        (_context(LANE_DIFF), WIN_RATE),
    ),
}

def zero_sum_note(tier: str, role: str) -> str:
    """Why same-rank win rate and gold difference say little across all champions."""
    return (
        f"Win rate and gold difference against {tier.capitalize()} {ROLE_GROUPS[role]} always "
        "come out near 50% and 0 overall, because every game has one winner — so "
        "they only tell you something per champion."
    )

VISION_NOTE = (
    "Vision is judged on control wards placed and wards destroyed. Trinket wards "
    "mostly show which trinket a player holds: one who swaps to Oracle Lens places "
    "few. Vision score is Riot's own number and its formula isn't public. So "
    "trinket wards, the Oracle Lens share and vision score are context only."
)
SUPPORT_VISION_NOTE = (
    "A support's vision is judged on all the wards they place, the support item's "
    "included, control wards and wards destroyed. Vision score is Riot's own "
    "number and its formula isn't public, so it's context only."
)
ROLE_NOTES = {
    "TOP": "Damage share is context: a tank top laner deals little by design.",
    "MIDDLE": "Roams are context: kills and assists away from mid before 14:00, "
    "which show only the roams that paid off.",
    "BOTTOM": "Kill participation is context: a bot laner's job is to farm and survive.",
    "UTILITY": "Gold and CS are context: supports aren't meant to farm.",
}

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


BENCHMARK_COVERAGE = """
SELECT cohort, NULL AS champion,
       count(*) FILTER (WHERE in_overall) AS games,
       count(DISTINCT puuid) FILTER (WHERE in_overall) AS players
FROM sample
GROUP BY cohort
UNION ALL
SELECT cohort, champion_name, count(*), count(DISTINCT puuid)
FROM sample
WHERE champion_name = ANY(:champions)
GROUP BY cohort, champion_name
ORDER BY cohort, champion NULLS FIRST
"""


COHORT_SIZES = """
SELECT c.cohort,
       (SELECT count(*) FROM scan_queue q
        WHERE q.cohort = c.cohort AND q.outcome IS NOT NULL) AS checked,
       (SELECT count(*) FROM sample s
        WHERE s.cohort = c.cohort AND s.in_overall) AS games,
       (SELECT count(DISTINCT s.puuid) FROM sample s
        WHERE s.cohort = c.cohort AND s.in_overall) AS players
FROM (SELECT cohort FROM scan_queue UNION SELECT cohort FROM sample) c
"""


async def cohort_sizes(benchmark_session: AsyncSession) -> dict[str, dict[str, int]]:
    """Each cohort's all-champion games and players, and matches checked. A
    cohort with no games of its own takes its snapshot's size, if it has one."""
    rows = await benchmark_session.execute(text(COHORT_SIZES))
    found = {row.cohort: dict(row._mapping) for row in rows}
    for cohort, size in (await snapshot.sizes(benchmark_session)).items():
        if not found.get(cohort, {}).get("games"):
            found[cohort] = {"cohort": cohort, "checked": 0, **size}
    return found


def _patch_order(patch: str) -> list[int]:
    return [int(part) for part in patch.split(".")]


def _keyed(rows: list[Row], metric: Metric) -> dict[tuple[Any, ...], Row]:
    return {
        tuple(row[key] for key in metric.keys): row
        for row in rows
        if all(row[k] == v for k, v in metric.only.items())
    }


def _percent(value: str, difference: float, theirs: float) -> int | None:
    """The gap as a whole percentage of the benchmark, where that means something.

    Not for differences against an opponent, where the benchmark sits near zero,
    or for values already in percent, where "points" is the clearer unit.
    """
    if value.endswith(("_diff", "_pct")) or theirs <= 0:
        return None
    return round(100 * difference / theirs)


def _gap(
    value: str, my_row: Row | None, their_row: Row | None, enough: bool
) -> dict[str, Any]:
    """The gap between the two sides and its 95% margin, where a margin exists.

    `difference` is there whenever both sides have a value, so the LLM never has
    to subtract. `clear_gap` is true when the gap is bigger than the noise on both
    sides combined, and `strong_gap` when it's STRONG_GAP_MULTIPLE times that.
    Both are None when there's no margin to judge by. The margin for `avg_x` or
    `x` is `margin_x`, so a stat with no such column has none.
    """
    margin = "margin_" + value.removeprefix("avg_")
    mine = my_row.get(value) if my_row else None
    theirs = their_row.get(value) if their_row and enough else None
    my_margin = my_row.get(margin) if my_row else None
    their_margin = their_row.get(margin) if their_row and enough else None
    gap = {
        "my_margin": my_margin,
        "benchmark_margin": their_margin,
        "difference": None,
        "difference_pct": None,
        "difference_margin": None,
        "clear_gap": None,
        "strong_gap": None,
    }
    if mine is None or theirs is None:
        return gap
    difference = mine - theirs
    gap["difference"] = round(difference, 3)
    gap["difference_pct"] = _percent(value, difference, theirs)
    if my_margin is not None and their_margin is not None:
        combined = math.hypot(my_margin, their_margin)
        clear = abs(difference) > combined
        gap |= {
            "difference_margin": round(combined, 3),
            "clear_gap": clear,
            "strong_gap": clear and abs(difference) >= STRONG_GAP_MULTIPLE * combined,
        }
    return gap


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
            gap = _gap(value, my_row, their_row, enough)
            if value in metric.context:
                gap |= {"clear_gap": None, "strong_gap": None}
            rows.append(
                {
                    "metric": metric.name,
                    "theme": metric.theme,
                    "higher_is_better": metric.higher_is_better,
                    **dict(zip(metric.keys, key)),
                    "value": value,
                    "sample_unit": metric.sample,
                    "my_value": my_row[value] if my_row else None,
                    "my_sample": my_sample,
                    "my_low_sample": my_sample < MIN_GAMES,
                    "benchmark_value": their_row[value] if enough else None,
                    "benchmark_sample": benchmark_sample,
                    **gap,
                    "status": "ok" if enough else "no_benchmark",
                    **({"context_only": True} if value in metric.context else {}),
                }
            )
    return rows


async def coverage(
    my_session: AsyncSession, benchmark_session: AsyncSession, puuids: list[str]
) -> dict[str, Any]:
    """What the player has played, and which of it has a benchmark."""
    player = await player_coverage(my_session, puuids)
    player["patches"] = sorted(player["patches"] or [], key=_patch_order)
    champions = [
        {"champion": row["value"], "games": row["games"]}
        for row in await win_rates(my_session, puuids)
        if row["dimension"] == "champion"
    ]
    rows = await benchmark_session.execute(
        text(BENCHMARK_COVERAGE), {"champions": [c["champion"] for c in champions]}
    )
    found = [dict(row) for row in rows.mappings()]
    # A cohort kept only as a snapshot has its all-champion size, and no champions.
    sampled = {row["cohort"] for row in found}
    for cohort, size in (await snapshot.sizes(benchmark_session)).items():
        if cohort not in sampled:
            found.append({"cohort": cohort, "champion": None, **size})
    benchmarks = [
        {
            **row,
            "has_benchmark": row["games"] >= MIN_BENCHMARK_GAMES
            and row["players"] >= MIN_BENCHMARK_PLAYERS,
        }
        for row in sorted(found, key=lambda r: (r["cohort"], r["champion"] is not None, r["champion"] or ""))
    ]
    return {"player": player, "champions": champions, "benchmarks": benchmarks}


async def compare(
    my_session: AsyncSession,
    benchmark_session: AsyncSession,
    puuids: list[str],
    cohort: str,
    champion: str | None = None,
    not_for_player: str | None = None,
) -> dict[str, Any]:
    """Compare stats in the cohort's role with `cohort`, for one champion or all of them.

    Every row shows the sample size on both sides. All-champion comparisons use
    the player's games on the benchmark's patches. Champion comparisons use all
    the player's games on that champion, because few are on recent patches, and
    a note says so. `not_for_player` is why this cohort doesn't fit the player
    (see cohorts.why_no_benchmark): then there's no benchmark, never another one.
    """
    sampled = (
        await benchmark_session.execute(
            text(SAMPLE_SIZE), {"cohort": cohort, "champion": champion}
        )
    ).one()
    size = {"games": sampled.games, "players": sampled.players, "patches": sampled.patches}
    # With no games of its own, an all-champion benchmark may be kept as a snapshot.
    kept = None if sampled.games or champion else await snapshot.read(benchmark_session, cohort)
    if kept:
        size = kept[snapshot.SIZE]
    patches = sorted(size["patches"] or [], key=_patch_order)
    group = get_cohort(cohort)
    result: dict[str, Any] = {
        "cohort": cohort,
        "tier": group.tier,
        "champion": champion,
        "role": group.role,
        "benchmark_games": size["games"],
        "benchmark_players": size["players"],
        "benchmark_patches": patches,
        "rows": [],
        "themes": [],
        "notes": [],
    }
    if not_for_player:
        result["status"] = "no_benchmark"
        result["notes"].append(
            f"No benchmark for this player. {not_for_player} "
            "Don't substitute another cohort or another player's comparison."
        )
        return result
    if size["games"] < MIN_BENCHMARK_GAMES or size["players"] < MIN_BENCHMARK_PLAYERS:
        result["status"] = "no_benchmark"
        result["notes"].append(
            f"A benchmark needs {MIN_BENCHMARK_GAMES} games and "
            f"{MIN_BENCHMARK_PLAYERS} players. Don't substitute another number."
        )
        return result

    result["status"] = "ok"
    result["notes"].append(SUPPORT_VISION_NOTE if group.role == "UTILITY" else VISION_NOTE)
    if group.role in ROLE_NOTES:
        result["notes"].append(ROLE_NOTES[group.role])
    absolute, relative = ROLE_METRICS[group.role]
    metrics = absolute
    if group.relative_stats:
        metrics += relative
        if champion is None:
            result["notes"].append(zero_sum_note(group.tier, group.role))
    else:
        result["not_comparable"] = [m.name for m in relative]
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
        role=group.role,
        champion=champion,
        patches=None if champion else tuple(patches),
    )
    benchmark_scope = Scope(cohort=cohort, role=group.role, champion=champion)
    for metric in metrics:
        theirs = (
            kept["metrics"][metric.name]
            if kept
            else await metric.stat(benchmark_session, benchmark_scope)
        )
        result["rows"] += _compare_metric(metric, await metric.stat(my_session, my_scope), theirs)
    result["themes"] = summarize_themes(result["rows"])
    return result
