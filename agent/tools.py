"""The tools the coach can call, each a thin wrapper around a stat function.

No tool takes a PUUID: the server decides whose data is read, so the model can't
ask for anyone else's. Results are JSON, and every number in them comes from SQL
or from `compare`.
"""

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from analytics.jungle import (
    deaths_before_objective,
    first_lane_kill,
    kill_participation,
    objective_control,
    wards_per_minute,
)
from analytics.stats import (
    Row,
    Scope,
    after_loss_streak,
    champion_stats,
    cs_per_minute,
    deaths_by_phase,
    gold_cs_at_minute,
    lane_diff,
    win_rate_by_gold_diff,
    win_rates,
)
from benchmarks.cohorts import COHORTS
from benchmarks.compare import compare, coverage
from benchmarks.themes import THEMES

logger = logging.getLogger(__name__)

Sessions = async_sessionmaker[AsyncSession]

CHAMPION = {
    "type": ["string", "null"],
    "description": (
        "Riot's name for a champion, as data_coverage lists it, such as DrMundo. "
        "Null for all champions."
    ),
}
BY_CHAMPION = {"champion": CHAMPION}
ROLES = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
ROLE = {
    "anyOf": [{"type": "string", "enum": ROLES}, {"type": "null"}],
    "description": "Keep only games in this role. Null for every role.",
}
NO_ROWS_NOTE = "No games match. data_coverage lists the champions and their exact names."

# Absent means false for these, so a result only mentions them when they matter.
HIDE_WHEN_FALSE = {"low_sample", "my_low_sample", "strong_gap"}
HIDDEN = {"higher_is_better"}


@dataclass(frozen=True)
class ToolContext:
    sessions: Sessions
    benchmark_sessions: Sessions
    puuids: tuple[str, ...]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    properties: dict[str, Any]
    run: Callable[[ToolContext, dict[str, Any]], Awaitable[Any]]


@dataclass(frozen=True)
class ToolResult:
    content: str
    is_error: bool = False


def _stat_tool(
    name: str,
    stat: Callable[[AsyncSession, Scope], Awaitable[list[Row]]],
    description: str,
    properties: dict[str, Any] = BY_CHAMPION,
) -> Tool:
    async def run(context: ToolContext, arguments: dict[str, Any]) -> Row:
        scope = Scope(
            puuids=context.puuids,
            champion=arguments.get("champion"),
            role=arguments.get("role"),
        )
        async with context.sessions() as session:
            rows = await stat(session, scope)
        return {"rows": rows} if rows else {"rows": [], "note": NO_ROWS_NOTE}

    return Tool(name, description, properties, run)


async def _data_coverage(context: ToolContext, arguments: dict[str, Any]) -> Row:
    async with context.sessions() as mine, context.benchmark_sessions() as bench:
        return await coverage(mine, bench, list(context.puuids))


async def _compare(context: ToolContext, arguments: dict[str, Any]) -> Row:
    async with context.sessions() as mine, context.benchmark_sessions() as bench:
        result = await compare(
            mine,
            bench,
            list(context.puuids),
            arguments["cohort"],
            arguments.get("champion"),
        )
    theme = arguments.get("theme")
    if theme:
        result["rows"] = [row for row in result["rows"] if row["theme"] == theme]
    return result


TOOLS = (
    Tool(
        "data_coverage",
        "What data exists: the player's games, dates, patches and champions, and "
        "which champions have a benchmark in each cohort. Call this first if you "
        "don't know what's available.",
        {},
        _data_coverage,
    ),
    Tool(
        "compare_to_benchmark",
        "Compare the player's jungle stats with a cohort of real players. Returns "
        "`themes`, which say what counts as a finding, and `rows`, with both "
        "sample sizes, the gap and its margin. Silver is the player's peers. "
        "Emerald is a target, and gets stats that don't depend on the opponent.",
        {
            "cohort": {"type": "string", "enum": sorted(COHORTS)},
            "champion": CHAMPION,
            # Strict mode rejects an enum next to a list of types, so null is
            # its own branch.
            "theme": {
                "anyOf": [{"type": "string", "enum": list(THEMES)}, {"type": "null"}],
                "description": "Keep only this theme's rows. Null for all rows.",
            },
        },
        _compare,
    ),
    _stat_tool(
        "champion_stats",
        champion_stats,
        "Games, wins, win rate, KDA and CS per minute for each champion played, "
        "most played first. KDA is the totals' (kills + assists) / deaths. The win "
        "rate has a margin and the range it gives (win_rate_low_pct to win_rate_high_pct).",
        {"role": ROLE},
    ),
    _stat_tool(
        "win_rates",
        win_rates,
        "Win rate per champion and per role, with games, wins and a margin.",
    ),
    _stat_tool(
        "deaths_by_phase",
        deaths_by_phase,
        "Deaths in the early (before 15:00), mid (15:00 to 25:00) and late game. "
        "Compare phases with deaths_per_10_min, because they differ in length.",
    ),
    _stat_tool(
        "lane_diff",
        lane_diff,
        "Gold and CS difference against the lane opponent at minutes 10, 15 and "
        "20, per role. Jungle rows are also split by win and loss.",
    ),
    _stat_tool(
        "win_rate_by_gold_diff",
        win_rate_by_gold_diff,
        "Jungle win rate by gold difference against the enemy jungler at minute 10.",
    ),
    _stat_tool(
        "after_loss_streak",
        after_loss_streak,
        "Performance by how many losses came straight before the game. A win or "
        "a 6-hour break resets the count, and '0' is the baseline to compare with.",
        {},
    ),
    _stat_tool(
        "cs_per_minute",
        cs_per_minute,
        "CS per minute per role and patch, oldest patch first. Includes jungle camps.",
    ),
    _stat_tool(
        "gold_cs_at_minute",
        gold_cs_at_minute,
        "Total gold and CS at minutes 10, 15 and 20, per role.",
    ),
    _stat_tool(
        "objective_control",
        objective_control,
        "Objectives taken by the player's team and by the enemy, per objective, in "
        "jungle games.",
    ),
    _stat_tool(
        "deaths_before_objective",
        deaths_before_objective,
        "How often the player died in the 60 seconds before an objective was "
        "taken, with a baseline to compare with, in jungle games.",
    ),
    _stat_tool(
        "kill_participation",
        kill_participation,
        "Share of the team's kills the player took part in, in jungle games.",
    ),
    _stat_tool(
        "wards_per_minute",
        wards_per_minute,
        "Wards placed and destroyed per minute, in jungle games.",
    ),
    _stat_tool(
        "first_lane_kill",
        first_lane_kill,
        "The first kill or assist on a laner in their own lane before 15:00, per "
        "lane. This isn't gank data: a game with no such kill may still have had "
        "ganks, and failed ganks can't be seen.",
    ),
)
_BY_NAME = {tool.name: tool for tool in TOOLS}


def tool_definitions() -> list[dict[str, Any]]:
    """The tools in the API's format. Strict mode needs every property required."""
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": tool.properties,
                "required": list(tool.properties),
                "additionalProperties": False,
            },
        }
        for tool in TOOLS
    ]


def _compact(value: Any) -> Any:
    """Drop what doesn't help the model, because each row is sent on every turn."""
    if isinstance(value, dict):
        return {
            key: _compact(item)
            for key, item in value.items()
            if item is not None
            and key not in HIDDEN
            and not (key in HIDE_WHEN_FALSE and item is False)
        }
    if isinstance(value, list):
        return [_compact(item) for item in value]
    return value


def _allowed_values(spec: dict[str, Any]) -> list[Any] | None:
    """The values an enum allows, with None if a branch allows null."""
    branches = spec.get("anyOf", [spec])
    values = [value for branch in branches for value in branch.get("enum", [])]
    if not values:
        return None
    return values + [None] * any(b.get("type") == "null" for b in branches)


def _problem(tool: Tool, arguments: dict[str, Any]) -> str | None:
    """Check arguments here too, because not every model enforces a schema."""
    unknown = set(arguments) - set(tool.properties)
    if unknown:
        return f"Unknown arguments: {', '.join(sorted(unknown))}."
    for key, spec in tool.properties.items():
        value = arguments.get(key)
        allowed = _allowed_values(spec)
        if allowed and value not in allowed:
            return f"{key} must be one of: {', '.join(str(v) for v in allowed)}."
        if value is not None and not isinstance(value, str):
            return f"{key} must be text."
    return None


async def run_tool(
    context: ToolContext, name: str, arguments: dict[str, Any]
) -> ToolResult:
    """Run a tool. A failure goes back to the model as an error, not an exception."""
    tool = _BY_NAME.get(name)
    if tool is None:
        return ToolResult(f"There is no tool called {name}.", is_error=True)
    problem = _problem(tool, arguments)
    if problem:
        return ToolResult(problem, is_error=True)
    try:
        result = await tool.run(context, arguments)
    except Exception:
        # Anything can fail here, and one bad tool shouldn't end the conversation.
        logger.exception("Tool %s failed", name)
        return ToolResult("This tool failed, so this data isn't available.", is_error=True)
    return ToolResult(json.dumps(_compact(result), default=str, sort_keys=True))
