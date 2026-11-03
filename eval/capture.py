"""Save the tool results the calibration set is graded against. Free: no model calls.

Run with `uv run python -m eval.capture` while the `db` container is up. Each set
is what the coach called for one real question, so the judge sees the same kind
of results it sees in a live run: whole comparisons, one theme, or player stats.
"""

import asyncio
import json
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.tools import ToolContext, run_tool
from benchmarks.models import create_benchmark_engine
from ingestion.players import load_player
from ingestion.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"
CONTEXTS = {
    # "What should I work on to win more games?"
    "work_on": [
        ("data_coverage", {}),
        ("compare_to_benchmark", {"cohort": "silver", "champion": None, "theme": None}),
        ("compare_to_benchmark", {"cohort": "emerald", "champion": None, "theme": None}),
    ],
    # "Do I die too much compared with Silver?": one theme, so other rows are absent.
    "deaths": [
        ("compare_to_benchmark", {"cohort": "silver", "champion": None, "theme": "deaths"}),
        ("deaths_by_phase", {"champion": None}),
    ],
    # "How do my wins compare with my losses?"
    # The same question when the coach called the comparison alone, as in the
    # second live run: the phase boundaries are only in an uncalled tool.
    "deaths_theme_only": [
        ("compare_to_benchmark", {"cohort": "silver", "champion": None, "theme": "deaths"}),
    ],
    "wins": [
        ("lane_diff", {"champion": None}),
        ("win_rate_by_gold_diff", {"champion": None}),
        ("win_rates", {"champion": None}),
    ],
}


async def main() -> None:
    settings = Settings()
    sessions = async_sessionmaker(create_async_engine(settings.database_url))
    benchmark = async_sessionmaker(create_benchmark_engine(settings))
    # Always the owner: other synced players' games must never enter the fixtures.
    async with sessions() as session:
        owner = await load_player(session)
    if owner is None:
        raise SystemExit("No owner synced yet: run POST /sync first.")
    context = ToolContext(sessions, benchmark, (owner.puuid,), owner)
    saved = {}
    for name, calls in CONTEXTS.items():
        saved[name] = []
        for tool, arguments in calls:
            result = await run_tool(context, tool, arguments)
            saved[name].append({"name": tool, "arguments": arguments, "content": result.content})
    path = FIXTURES / "tool_outputs.json"
    path.write_text(json.dumps(saved, indent=1) + "\n", encoding="utf-8")
    for name, outputs in saved.items():
        print(f"{name}: {sum(len(o['content']) for o in outputs):,} characters")


if __name__ == "__main__":
    asyncio.run(main())
