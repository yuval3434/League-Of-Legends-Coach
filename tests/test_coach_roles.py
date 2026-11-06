"""The coach's tools for a player in any role, and the eval's role case."""

import json

from test_analytics import add_frames, add_game
from test_benchmarks import benchmark_sessions  # noqa: F401
from test_players import add_player

from agent.coach import CoachAnswer, ToolLog
from agent.tools import ToolContext, run_tool
from eval.cases import CASES
from eval.checks import right_cohort
from eval.run import non_jungler
from ingestion.players import SelectedPlayer, list_players

ME = "me"
GOLD_MID = SelectedPlayer(
    puuid=ME,
    game_name="Me",
    tag_line="EUW",
    is_owner=True,
    rank_tier="GOLD",
    rank_checked=True,
    main_role="MIDDLE",
    role_games={"MIDDLE": 12, "JUNGLE": 3},
)


def mid_context(sessions, benchmark_sessions):  # noqa: F811
    return ToolContext(sessions, benchmark_sessions, (ME,), GOLD_MID)


async def call(context, name, **arguments):
    result = await run_tool(context, name, arguments)
    assert not result.is_error, result.content
    return json.loads(result.content)


async def test_a_role_tool_defaults_to_the_main_role(sessions, benchmark_sessions):  # noqa: F811
    async with sessions() as session:
        await add_game(session, "EUW1_1", role="MIDDLE", kills=1)
        await add_game(session, "EUW1_2", kills=1)
        await add_game(session, "EUW1_3", kills=1)
        for match_id in ("EUW1_1", "EUW1_2", "EUW1_3"):
            await add_frames(session, match_id, 1, {})
    context = mid_context(sessions, benchmark_sessions)

    mid = await call(context, "kill_participation", champion=None, role=None)
    jungle = await call(context, "kill_participation", champion=None, role="JUNGLE")

    assert (mid["rows"][0]["games"], jungle["rows"][0]["games"]) == (1, 2)


async def test_coverage_lists_the_players_roles_and_their_cohorts(sessions, benchmark_sessions):  # noqa: F811
    result = await call(mid_context(sessions, benchmark_sessions), "data_coverage")

    assert result["roles"] == [{"role": "MIDDLE", "games": 12}]
    assert result["cohorts"]["gold_middle"] == "available"
    assert "fewer than 10 jungle games" in result["cohorts"]["silver"]


async def test_any_cohort_name_works_and_a_wrong_one_is_explained(sessions, benchmark_sessions):  # noqa: F811
    context = mid_context(sessions, benchmark_sessions)

    fine = await call(context, "compare_to_benchmark", cohort="gold_middle", champion=None, theme=None)
    wrong = await run_tool(context, "compare_to_benchmark", {"cohort": "gold_mid", "champion": None, "theme": None})

    assert (fine["role"], fine["status"]) == ("MIDDLE", "no_benchmark")
    assert wrong.is_error and "data_coverage lists the cohorts" in wrong.content


async def test_wins_and_losses_runs_for_the_main_role(sessions, benchmark_sessions):  # noqa: F811
    async with sessions() as session:
        await add_game(session, "EUW1_1", role="MIDDLE", win=True, lane_cs=300)
        await add_game(session, "EUW1_2", role="MIDDLE", win=False, lane_cs=150)

    result = await call(mid_context(sessions, benchmark_sessions), "wins_and_losses", role=None)

    assert result["role"] == "MIDDLE"
    cs = next(r for r in result["rows"] if r["value"] == "avg_cs_per_min")
    assert (cs["wins"]["sample"], cs["losses"]["sample"]) == (1, 1)


# The eval's role case


def log(cohort):
    return ToolLog("compare_to_benchmark", {"cohort": cohort}, "{}", False)


def test_right_cohort_needs_only_the_players_peers():
    answer = CoachAnswer("", "verified")
    assert not right_cohort(answer, "gold_middle").passed  # no comparison at all
    answer.tool_log = [log("gold_middle")]
    assert right_cohort(answer, "gold_middle").passed
    answer.tool_log = [log("gold_middle"), log("silver")]
    assert not right_cohort(answer, "gold_middle").passed


def test_the_mid_case_checks_the_cohort_and_names_no_one():
    case = next(c for c in CASES if c.id == "mid_peers")
    assert (case.player, "right_cohort" in case.code_checks) == ("non_jungler", True)


async def test_the_non_jungler_is_shown_to_the_coach_as_you(sessions):
    async with sessions() as session:
        await add_player(session, ME, "Me", owner=True)
        await add_player(session, "friend", "RealName", tier="GOLD")
        for n in range(3):
            await add_game(session, f"EUW1_{n}", role="MIDDLE", puuid="friend")
        players = await list_players(session)

    player = await non_jungler(sessions, players)

    assert (player.puuid, player.main_role, player.is_owner) == ("friend", "MIDDLE", True)
    assert "RealName" not in (player.game_name, player.tag_line)
