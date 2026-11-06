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
from ingestion.ddragon import refresh_champions
from test_draft import champ, fake_ddragon

ME = "me"
# Lane plates has no rows for jungle games, which is all this test data has.
BY_CHAMPION = [
    t.name for t in TOOLS if "champion" in t.properties and t.name not in ("compare_to_benchmark", "role_measures")
]


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
            await add_game(session, match_id, champion=champion, patch="16.21", kills=2, damage=1000)
            for minute in (10, 15, 20):
                await add_frames(session, match_id, minute, {2: 1000, 7: 900})
            await add_event(
                session, match_id, "ELITE_MONSTER_KILL", 600_000,
                killerTeamId=100, monsterType="DRAGON",
            )
        await session.commit()


async def store_champions(sessions, *champions):
    """Data Dragon's champions as the app stores them at startup, with no request."""
    async with sessions() as session:
        await refresh_champions(session, fake_ddragon("1.0.1", []))
        for champion in champions:
            session.add(champion)
        await session.commit()


def test_every_tool_is_strict_and_requires_all_its_properties():
    for tool in tool_definitions():
        schema = tool["input_schema"]
        assert tool["strict"] is True
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])


def test_the_api_accepts_this_many_strict_tools():
    """Anthropic's API refuses a request with more than 20 strict tools."""
    assert sum(1 for tool in tool_definitions() if tool["strict"]) <= 20


def test_the_api_accepts_this_many_union_parameters():
    """Strict tools may have at most 16 parameters with union types in all."""
    unions = [
        (tool["name"], name)
        for tool in tool_definitions()
        for name, spec in tool["input_schema"]["properties"].items()
        if "anyOf" in spec or isinstance(spec.get("type"), list)
    ]
    assert len(unions) <= 16, unions


def test_no_enum_sits_next_to_a_list_of_types():
    """The API rejects this in strict mode: use anyOf with a null branch instead."""
    for tool in tool_definitions():
        for spec in tool["input_schema"]["properties"].values():
            assert not ("enum" in spec and isinstance(spec.get("type"), list)), tool["name"]


@pytest.mark.parametrize("theme", ["economy", None])
async def test_a_theme_can_be_named_or_left_out(context, theme):
    arguments = {"cohort": "silver", "champion": None, "theme": theme}
    from agent.tools import _BY_NAME, _problem

    assert _problem(_BY_NAME["compare_to_benchmark"], arguments) is None


def test_no_tool_lets_the_model_choose_the_player():
    assert "puuid" not in json.dumps(tool_definitions()).lower()


def test_tool_names_are_unique():
    names = [t["name"] for t in tool_definitions()]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("name", [t.name for t in TOOLS])
async def test_every_tool_runs(context, sessions, name):
    await add_two_champions(sessions)
    await store_champions(sessions)
    arguments = {
        "compare_to_benchmark": {"cohort": "silver"},
        "draft_board": {"allies": [], "enemies": [], "bans": []},
        "riot_notes": {"champions": ["Wukong"]},
    }.get(name, {})
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
        ("compare_to_benchmark", {"cohort": "gold"}, "no cohort called gold"),
        ("win_rates", {"champion": 7}, "must be text"),
        ("draft_board", {"allies": "Ahri", "enemies": [], "bans": []}, "list of names"),
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


async def test_the_draft_board_takes_champions_and_explains_bad_boards(context, sessions):
    await store_champions(sessions, champ("Ahri", ["Mage"], 3, 8))
    async with sessions() as session:
        for n in range(3):
            await add_game(session, f"EUW1_{n}", champion="MonkeyKing")

    board = await call(context, "draft_board", allies=["Ahri"], enemies=[], bans=[])
    assert board["data_dragon_version"] == "1.0.1"
    assert board["pool"][0]["fills"] == ["no_frontline", "no_physical_damage"]

    result = await run_tool(
        context, "draft_board", {"allies": ["Ahri"], "enemies": ["Ahri"], "bans": []}
    )
    assert result.is_error
    assert result.content == "A champion can only be picked once: Ahri."


async def test_the_draft_board_never_fetches(context):
    result = await run_tool(context, "draft_board", {"allies": [], "enemies": [], "bans": []})
    assert result.is_error
    assert "isn't loaded yet" in result.content
