"""The tool layer: schemas without a database, and each tool against Postgres."""

import json

import pytest
from test_analytics import add_event, add_frames, add_game
from test_benchmarks import (  # noqa: F401
    add_sampled_game,
    benchmark_sessions,
    fill_cohort,
)

from agent.tools import TOOLS, ToolContext, run_tool, tool_definitions

ME = "me"
BY_CHAMPION = [t.name for t in TOOLS if "champion" in t.properties and t.name != "compare_to_benchmark"]


@pytest.fixture
def context(sessions, benchmark_sessions):  # noqa: F811
    return ToolContext(sessions, benchmark_sessions, (ME,))


async def call(context, name, **arguments):
    result = await run_tool(context, name, arguments)
    assert not result.is_error, result.content
    return json.loads(result.content)


async def add_two_champions(sessions):
    """A game each on Viego and Quinn, with everything the stats need to find rows."""
    async with sessions() as session:
        for match_id, champion in (("EUW1_1", "Viego"), ("EUW1_2", "Quinn")):
            await add_game(session, match_id, champion=champion, patch="16.21", kills=2)
            for minute in (10, 15, 20):
                await add_frames(session, match_id, minute, {2: 1000, 7: 900})
            await add_event(
                session, match_id, "ELITE_MONSTER_KILL", 600_000,
                killerTeamId=100, monsterType="DRAGON",
            )
        await session.commit()


def test_every_tool_is_strict_and_requires_all_its_properties():
    for tool in tool_definitions():
        schema = tool["input_schema"]
        assert tool["strict"] is True
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])


def test_no_tool_lets_the_model_choose_the_player():
    assert "puuid" not in json.dumps(tool_definitions()).lower()


def test_tool_names_are_unique():
    names = [t["name"] for t in tool_definitions()]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("name", [t.name for t in TOOLS])
async def test_every_tool_runs(context, sessions, name):
    await add_two_champions(sessions)
    arguments = {"cohort": "silver"} if name == "compare_to_benchmark" else {}
    await call(context, name, **arguments)


@pytest.mark.parametrize("name", BY_CHAMPION)
async def test_a_champion_filter_narrows_the_games(context, sessions, name):
    await add_two_champions(sessions)

    everything = await call(context, name, champion=None)
    viego = await call(context, name, champion="Viego")

    assert everything["rows"], "this stat needs more test data"
    assert sum(r["games"] for r in viego["rows"]) < sum(
        r["games"] for r in everything["rows"]
    )


async def test_a_champion_with_no_games_says_so(context, sessions):
    await add_two_champions(sessions)
    result = await call(context, "win_rates", champion="Dr. Mundo")
    assert result["rows"] == []
    assert "data_coverage" in result["note"]


async def test_only_the_tracked_player_is_read(context, sessions):
    async with sessions() as session:
        await add_game(session, "EUW1_1", puuid=ME)
        await add_game(session, "EUW1_2", puuid="someone-else")
        await session.commit()
    result = await call(context, "win_rates")
    role = next(r for r in result["rows"] if r["dimension"] == "role")
    assert role["games"] == 1


async def test_coverage_lists_games_champions_and_benchmarks(
    context, sessions, benchmark_sessions  # noqa: F811
):
    await add_two_champions(sessions)
    async with benchmark_sessions() as session:
        await fill_cohort(session)
        await session.commit()

    result = await call(context, "data_coverage")

    assert result["player"]["games"] == 2
    assert result["player"]["patches"] == ["16.21"]
    assert {c["champion"]: c["games"] for c in result["champions"]} == {
        "Viego": 1,
        "Quinn": 1,
    }
    benchmark = {
        (b["cohort"], b.get("champion")): b["has_benchmark"]
        for b in result["benchmarks"]
    }
    assert benchmark[("silver", None)] is True
    assert benchmark[("silver", "Viego")] is True
    assert ("silver", "Quinn") not in benchmark


async def test_patches_in_coverage_sort_as_numbers(context, sessions):
    async with sessions() as session:
        await add_game(session, "EUW1_1", patch="16.9")
        await add_game(session, "EUW1_2", patch="16.10")
        await session.commit()
    result = await call(context, "data_coverage")
    assert result["player"]["patches"] == ["16.9", "16.10"]


async def test_comparison_rows_can_be_narrowed_to_a_theme(
    context, sessions, benchmark_sessions  # noqa: F811
):
    await add_two_champions(sessions)
    async with benchmark_sessions() as session:
        await fill_cohort(session)
        await session.commit()

    result = await call(context, "compare_to_benchmark", cohort="silver", theme="vision")

    assert result["rows"]
    assert {r["theme"] for r in result["rows"]} == {"vision"}
    assert len(result["themes"]) == 5


async def test_results_leave_out_empty_values(context, sessions):
    await add_two_champions(sessions)
    result = await call(context, "win_rates")
    # Two games on two champions: one game each has no margin and a low sample.
    row = next(r for r in result["rows"] if r["value"] == "Viego")
    assert "margin_win_rate_pct" not in row
    assert row["low_sample"] is True


async def test_low_sample_is_only_mentioned_when_true(context, sessions):
    async with sessions() as session:
        for n in range(10):
            await add_game(session, f"EUW1_{n}")
        await session.commit()
    result = await call(context, "win_rates")
    role = next(r for r in result["rows"] if r["dimension"] == "role")
    assert "low_sample" not in role


@pytest.mark.parametrize(
    ("name", "arguments", "expected"),
    [
        ("no_such_tool", {}, "no tool"),
        ("win_rates", {"puuid": "someone-else"}, "Unknown arguments"),
        ("compare_to_benchmark", {"cohort": "gold"}, "must be one of"),
        ("win_rates", {"champion": 7}, "must be text"),
    ],
)
async def test_bad_calls_become_errors_for_the_model(context, name, arguments, expected):
    result = await run_tool(context, name, arguments)
    assert result.is_error
    assert expected in result.content


async def test_a_failing_tool_becomes_an_error_for_the_model(sessions):
    def broken():
        raise RuntimeError("database is down")

    context = ToolContext(broken, broken, (ME,))
    result = await run_tool(context, "win_rates", {})
    assert result.is_error
    assert "database is down" not in result.content
