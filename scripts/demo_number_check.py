"""Show the number check catching made-up numbers. Makes no paid calls.

Run with `uv run python scripts/demo_number_check.py` while the `db` container
is up and a player is synced. The model is a script that lies on purpose. The
tools, the loop and the check are the real ones, reading the real database.
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# The scripted model lives with the tests, which aren't a package.
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

from fakes import FakeModel, calls, says  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from agent.coach import CoachAnswer, ask_coach  # noqa: E402
from agent.tools import ToolContext, run_tool  # noqa: E402
from benchmarks.models import create_benchmark_engine  # noqa: E402
from ingestion.players import load_player  # noqa: E402
from ingestion.config import Settings  # noqa: E402

QUESTION = "How is my farming compared with Silver?"
COMPARE = (
    "compare_to_benchmark",
    {"cohort": "silver", "champion": None, "theme": "economy"},
)


def show(title: str, model: FakeModel, answer: CoachAnswer) -> None:
    print(f"\n=== {title}")
    for messages in model.sent:
        last = messages[-1]
        if isinstance(last["content"], str) and "automatic check" in last["content"]:
            print(f"Retry sent:     {last['content']}")
    print(f"Numbers caught: {answer.caught_numbers or 'none'}")
    print(f"Status:         {answer.status}")
    print(f"Shown to user:  {answer.text}")


async def main() -> None:
    settings = Settings()
    mine = async_sessionmaker(create_async_engine(settings.database_url))
    bench = async_sessionmaker(create_benchmark_engine(settings))
    async with mine() as session:
        owner = await load_player(session)
    if owner is None:
        sys.exit("No player synced yet: run POST /sync first.")
    context = ToolContext(mine, bench, (owner.puuid,), owner)

    result = await run_tool(context, *COMPARE)
    row = next(
        r for r in json.loads(result.content)["rows"] if r["value"] == "avg_cs_per_min"
    )
    you, games = row["my_value"], row["my_sample"]
    silver, silver_games = row["benchmark_value"], row["benchmark_sample"]
    print("The real row from compare_to_benchmark:")
    print(f"  CS per minute: you {you} ({games} games), Silver {silver} ({silver_games})")

    honest = (
        f"You average {you} CS per minute over {games} games, "
        f"against {silver} over {silver_games} Silver games."
    )
    cases = [
        (
            "1. A made-up number, fixed on the retry",
            [calls(COMPARE), says("You average 7.91 CS per minute, ahead of Silver."), says(honest)],
        ),
        (
            "2. A made-up number twice: shown with a warning",
            [calls(COMPARE), says("You average 7.91 CS per minute."), says("It's 8.2 a minute.")],
        ),
        (
            "3. A real number, but no tool was called",
            [says(f"You average {you} CS per minute."), says("I'd need to check your data first.")],
        ),
        ("4. An honest answer: no retry", [calls(COMPARE), says(honest)]),
    ]
    for title, replies in cases:
        model = FakeModel(*replies)
        show(title, model, await ask_coach(model, context, QUESTION))


if __name__ == "__main__":
    asyncio.run(main())
