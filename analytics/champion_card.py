"""The champion card on the Draft page: the player's stats on one champion next
to their overall jungle average, each cohort's benchmark on that champion, and
Riot's text about it from Data Dragon.

Every number comes from the existing stat functions. The champion's games are
part of the overall average, so the two are shown side by side and never
subtracted: a difference between a part and its whole isn't a fair comparison.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from analytics.jungle import kill_participation
from analytics.stats import (
    MIN_GAMES,
    Row,
    Scope,
    deaths_by_phase,
    gold_cs_at_minute,
    overall_cs_per_minute,
    win_rates,
)
from benchmarks.cohorts import COHORTS, MIN_BENCHMARK_GAMES, MIN_BENCHMARK_PLAYERS
from benchmarks.compare import SAMPLE_SIZE
from analytics.draft import resolve
from ingestion.ddragon import load_champions, load_details
from ingestion.models import ChampionDetail

ROLE = "JUNGLE"

# Emerald players face Emerald opponents, so a win rate there says nothing about
# how a lower-ranked player's games go. The same rule as compare_to_benchmark.
NOT_COMPARABLE_WIN_RATE = {"emerald"}


@dataclass(frozen=True)
class Stat:
    id: str
    label: str
    stat: Callable[[AsyncSession, Scope], Awaitable[list[Row]]]
    value: str
    keep: dict[str, Any]


STATS = (
    Stat("cs_per_min", "CS per minute", overall_cs_per_minute, "cs_per_min", {}),
    Stat("gold_at_15", "Gold at 15 minutes", gold_cs_at_minute, "gold", {"minute": 15}),
    Stat("deaths_early", "Deaths before 15:00", deaths_by_phase, "deaths", {"phase": "early"}),
    Stat("deaths_mid", "Deaths from 15:00 to 25:00", deaths_by_phase, "deaths", {"phase": "mid"}),
    Stat("deaths_late", "Deaths after 25:00", deaths_by_phase, "deaths", {"phase": "late"}),
    Stat(
        "kill_participation",
        "Kill participation (%)",
        kill_participation,
        "kill_participation_pct",
        {},
    ),
)

SPELLING = """
SELECT p.champion_name
FROM match_participants p
WHERE lower(p.champion_name) = lower(:champion)
LIMIT 1
"""

LAST_PLAYED = """
SELECT max(m.game_start_at)::date AS last_played
FROM match_participants p
JOIN matches m ON m.match_id = p.match_id
WHERE p.puuid = ANY(:puuids) AND p.champion_name = :champion
  AND p.team_position = 'JUNGLE' AND NOT m.is_remake
"""


def _side(rows: list[Row], stat: Stat) -> Row | None:
    row = next((r for r in rows if all(r.get(k) == v for k, v in stat.keep.items())), None)
    if row is None:
        return None
    return {
        "value": row[f"avg_{stat.value}"],
        "margin": row[f"margin_{stat.value}"],
        "games": row["games"],
        "low_sample": row["low_sample"],
    }


async def _mine(session: AsyncSession, puuids: tuple[str, ...], champion: str) -> list[Row]:
    rows = []
    for stat in STATS:
        one = await stat.stat(session, Scope(puuids=puuids, role=ROLE, champion=champion))
        everything = await stat.stat(session, Scope(puuids=puuids, role=ROLE))
        rows.append(
            {
                "stat": stat.id,
                "label": stat.label,
                "champion": _side(one, stat),
                "overall": _side(everything, stat),
            }
        )
    return rows


async def _benchmark(
    session: AsyncSession, cohort: str, champion: str, not_for_player: str | None
) -> Row:
    size = (await session.execute(text(SAMPLE_SIZE), {"cohort": cohort, "champion": champion})).one()
    result: Row = {
        "cohort": cohort,
        "tier": COHORTS[cohort].tier,
        "benchmark_games": size.games,
        "benchmark_players": size.players,
    }
    if not_for_player:
        return result | {"status": "no_benchmark", "note": f"No benchmark for this player. {not_for_player}"}
    if size.games < MIN_BENCHMARK_GAMES or size.players < MIN_BENCHMARK_PLAYERS:
        return result | {
            "status": "no_benchmark",
            "note": (
                f"A benchmark on one champion needs {MIN_BENCHMARK_GAMES} games from "
                f"{MIN_BENCHMARK_PLAYERS} players."
            ),
        }
    scope = Scope(cohort=cohort, champion=champion, role=ROLE)
    cs = (await overall_cs_per_minute(session, scope))[0]
    result |= {
        "status": "ok",
        "benchmark_patches": sorted(size.patches or []),
        "cs_per_min": {"value": cs["avg_cs_per_min"], "margin": cs["margin_cs_per_min"]},
    }
    if cohort in NOT_COMPARABLE_WIN_RATE:
        return result | {"win_rate": "not_comparable"}
    rate = next(r for r in await win_rates(session, scope) if r["dimension"] == "champion")
    return result | {
        "win_rate": {"value": rate["win_rate_pct"], "margin": rate["margin_win_rate_pct"]}
    }


def describe_detail(detail: ChampionDetail | None) -> Row | None:
    """Riot's text about a champion, as Data Dragon has it."""
    if detail is None:
        return None
    return {
        "title": detail.title,
        "abilities": detail.abilities,
        "ally_tips": list(detail.ally_tips),
        "enemy_tips": list(detail.enemy_tips),
    }


RIOT_NOTE = (
    "Riot's own text from Data Dragon. The abilities are current for this version; "
    "the tips can be older than a champion's current abilities, so use a tip only "
    "if it agrees with them."
)


async def riot_notes(session: AsyncSession, names: list[str]) -> Row:
    """Riot's abilities and tips for these champions. Raises ValueError on a name
    Data Dragon doesn't have."""
    version, champions = await load_champions(session)
    if not champions:
        raise ValueError("Champion data from Data Dragon isn't loaded yet.")
    found = resolve(names, champions)
    details = await load_details(session, version, [c.champion for c in found])
    return {
        "data_dragon_version": version,
        "champions": [
            {"champion": c.champion, "name": c.name} | (describe_detail(details.get(c.champion)) or {})
            for c in found
        ],
        "note": RIOT_NOTE,
    }


async def champion_card(
    my_session: AsyncSession,
    benchmark_session: AsyncSession,
    puuids: tuple[str, ...],
    champion: str,
    not_for_player: dict[str, str | None],
    detail: ChampionDetail | None,
) -> Row | None:
    """One champion's card, or None if no game anywhere has this champion."""
    # Match data's spelling, which can differ from Data Dragon's (FiddleSticks).
    spelling = await my_session.scalar(text(SPELLING), {"champion": champion})
    if spelling is None:
        return None
    rows = await _mine(my_session, puuids, spelling)
    last = await my_session.scalar(
        text(LAST_PLAYED), {"puuids": list(puuids), "champion": spelling}
    )
    games = next((r["champion"]["games"] for r in rows if r["stat"] == "cs_per_min" and r["champion"]), 0)
    return {
        "champion": spelling,
        "games": games,
        "low_sample": games < MIN_GAMES,
        "last_played": last,
        "rows": rows,
        "benchmarks": {
            cohort: await _benchmark(benchmark_session, cohort, spelling, not_for_player[cohort])
            for cohort in COHORTS
        },
        "riot": describe_detail(detail),
        "notes": [
            "The champion's games are part of the overall average, so the two are "
            "shown side by side, not compared.",
            "Riot's tips can be older than the champion's current abilities.",
        ],
    }
