"""Save the tool results the calibration set is graded against. Free: no model calls.

Run with `uv run python -m eval.capture` while the `db` container is up. These are
the results behind the second real coach question, "What should I work on to win
more games?", which called the same three tools.
"""

import asyncio
import json
from pathlib import Path

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.tools import ToolContext, run_tool
from benchmarks.models import create_benchmark_engine
from benchmarks.pull import tracked_puuids
from ingestion.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"
CALLS = [
    ("data_coverage", {}),
    ("compare_to_benchmark", {"cohort": "silver", "champion": None, "theme": None}),
    ("compare_to_benchmark", {"cohort": "emerald", "champion": None, "theme": None}),
]


async def main() -> None:
    settings = Settings()
    sessions = async_sessionmaker(create_async_engine(settings.database_url))
    benchmark = async_sessionmaker(create_benchmark_engine(settings))
    async with sessions() as session:
        puuids = tuple(sorted(await tracked_puuids(session)))
    context = ToolContext(sessions, benchmark, puuids)
    outputs = []
    for name, arguments in CALLS:
        result = await run_tool(context, name, arguments)
        outputs.append({"name": name, "arguments": arguments, "content": result.content})
    path = FIXTURES / "tool_outputs.json"
    path.write_text(json.dumps(outputs, indent=1) + "\n", encoding="utf-8")
    print(f"{path}: {sum(len(o['content']) for o in outputs):,} characters")


if __name__ == "__main__":
    asyncio.run(main())
