"""Several synced players: who a request is about, and which benchmarks fit them."""

import json
from datetime import UTC, datetime

import pytest
from fakes import FakeModel, calls, says
from fastapi.testclient import TestClient
from sqlalchemy import insert
from test_analytics import add_frames, add_game
from test_benchmarks import EMERALD, add_sampled_game, benchmark_sessions, fill_cohort  # noqa: F401

from agent.coach import ask_coach
from agent.tools import ToolContext, run_tool
from benchmarks.cohorts import why_no_benchmark
from ingestion.models import Player
from ingestion.players import list_players, load_player
from main import create_app

ME, FRIEND = "me", "friend"


async def add_player(session, puuid, name, owner=False, tier="SILVER"):
    await session.execute(
        insert(Player),
        [
            {
                "puuid": puuid,
                "game_name": name,
                "tag_line": "EUW",
                "region": "europe",
                "raw_account": {},
                "is_owner": owner,
                "rank_tier": tier,
                "rank_checked_at": datetime.now(UTC),
            }
        ],
    )
    await session.commit()


async def two_players(sessions, friend_tier="GOLD", friend_role="JUNGLE"):
    """The owner: 3 Viego jungle games. The friend: 2 Ornn games in `friend_role`."""
    async with sessions() as session:
        await add_player(session, ME, "Me", owner=True)
        await add_player(session, FRIEND, "Friend7", tier=friend_tier)
        for n in range(3):
            await add_game(session, f"EUW1_M{n}", champion="Viego", patch="16.21")
            await add_frames(session, f"EUW1_M{n}", 1, {})
        for n in range(2):
            await add_game(
                session, f"EUW1_F{n}", puuid=FRIEND, champion="Ornn", role=friend_role, patch="16.21"
            )
            await add_frames(session, f"EUW1_F{n}", 1, {})


# Which benchmarks fit whom


@pytest.mark.parametrize(
    ("cohort", "tier", "role", "fits"),
    [
        ("silver", "SILVER", "JUNGLE", True),
        ("silver", "GOLD", "JUNGLE", False),
        ("silver", "BRONZE", "JUNGLE", False),
        ("emerald", "SILVER", "JUNGLE", True),
        ("emerald", "IRON", "JUNGLE", True),
        ("emerald", "PLATINUM", "JUNGLE", True),
        ("emerald", "EMERALD", "JUNGLE", False),
        ("emerald", "DIAMOND", "JUNGLE", False),
        ("silver", "SILVER", "MIDDLE", False),
        ("emerald", "SILVER", "UTILITY", False),
        ("silver", None, "JUNGLE", False),
        ("silver", "SILVER", None, False),
    ],
)
def test_a_cohort_fits_only_its_audience(cohort, tier, role, fits):
    assert (why_no_benchmark(cohort, tier, role) is None) == fits


def test_an_unchecked_rank_isnt_called_unranked():
    reason = why_no_benchmark("silver", None, "JUNGLE", rank_checked=False)
    assert "hasn't been checked" in reason


def test_the_reason_names_the_role_and_rank():
    assert "mostly plays mid" in why_no_benchmark("silver", "SILVER", "MIDDLE")
    assert "this player is Gold" in why_no_benchmark("silver", "GOLD", "JUNGLE")
    assert "unranked" in why_no_benchmark("emerald", None, "JUNGLE")


# Who a request is about


async def test_players_list_the_owner_first_with_main_role_and_games(sessions):
    await two_players(sessions, friend_role="TOP")
    async with sessions() as session:
        rows = await list_players(session)

    assert [(r["puuid"], r["main_role"], r["games"], r["jungle_games"]) for r in rows] == [
        (ME, "JUNGLE", 3, 3),
        (FRIEND, "TOP", 2, 0),
    ]


async def test_no_player_named_means_the_owner(sessions):
    await two_players(sessions)
    async with sessions() as session:
        assert (await load_player(session)).puuid == ME
        assert (await load_player(session, FRIEND)).game_name == "Friend7"
        assert await load_player(session, "nobody") is None


async def test_stats_never_mix_two_players_games(sessions, benchmark_sessions):  # noqa: F811
    await two_players(sessions)
    async with sessions() as session:
        me, friend = await load_player(session, ME), await load_player(session, FRIEND)

    async def champions(player):
        context = ToolContext(sessions, benchmark_sessions, (player.puuid,), player)
        result = await run_tool(context, "champion_stats", {"role": None})
        return {r["champion"]: r["games"] for r in json.loads(result.content)["rows"]}

    assert await champions(me) == {"Viego": 3}
    assert await champions(friend) == {"Ornn": 2}


# Benchmarks for another player


async def test_another_rank_gets_no_benchmark_not_the_owners(sessions, benchmark_sessions):  # noqa: F811
    await two_players(sessions, friend_tier="GOLD")
    async with benchmark_sessions() as bench:
        await fill_cohort(bench)
        for n in range(30):
            await add_sampled_game(bench, f"EUW1_E{n}", f"player-{n % 10}", cohort=EMERALD, patch="16.21")
    async with sessions() as session:
        friend = await load_player(session, FRIEND)
    context = ToolContext(sessions, benchmark_sessions, (FRIEND,), friend)

    silver = json.loads((await run_tool(context, "compare_to_benchmark", {"cohort": "silver"})).content)
    emerald = json.loads((await run_tool(context, "compare_to_benchmark", {"cohort": "emerald"})).content)
    coverage = json.loads((await run_tool(context, "data_coverage", {})).content)

    # Gold: Silver isn't their peers, so there's no comparison at all.
    assert silver["status"] == "no_benchmark"
    assert silver["rows"] == [] and silver["themes"] == []
    assert any("this player is Gold" in n for n in silver["notes"])
    # Emerald is still a target for a Gold player.
    assert emerald["status"] == "ok"
    assert coverage["cohorts"]["silver"].startswith("The Silver benchmark")
    assert coverage["cohorts"]["emerald"] == "available"


async def test_a_non_jungler_gets_no_benchmark(test_settings, sessions, benchmark_sessions):  # noqa: F811
    await two_players(sessions, friend_tier="SILVER", friend_role="MIDDLE")
    async with benchmark_sessions() as bench:
        await fill_cohort(bench)
    app = create_app(test_settings)
    with TestClient(app) as client:
        result = client.get("/benchmarks/compare", params={"cohort": "silver", "player": FRIEND}).json()
        mine = client.get("/benchmarks/compare", params={"cohort": "silver"}).json()

    assert result["status"] == "no_benchmark"
    assert any("mostly plays mid" in n for n in result["notes"])
    # The owner's own comparison is untouched.
    assert mine["status"] == "ok"


# The API


async def test_the_api_serves_the_player_asked_for(test_settings, sessions):
    await two_players(sessions)
    with TestClient(create_app(test_settings)) as client:
        players = client.get("/players").json()
        friend = client.get("/player", params={"player": FRIEND}).json()
        owner = client.get("/player").json()
        stats = client.get("/stats/champion_stats", params={"player": FRIEND}).json()
        missing = client.get("/player", params={"player": "nobody"})

    assert [p["game_name"] for p in players] == ["Me", "Friend7"]
    assert players[1]["benchmarks"]["silver"] is not None
    assert (friend["game_name"], friend["rank_tier"], friend["is_owner"]) == ("Friend7", "GOLD", False)
    assert friend["benchmarks"]["emerald"] is None
    assert owner["puuid"] == ME
    assert [r["champion"] for r in stats["rows"]] == ["Ornn"]
    assert missing.status_code == 404


# The coach


async def test_the_coach_is_told_whose_games_these_are(sessions, benchmark_sessions):  # noqa: F811
    await two_players(sessions)
    async with sessions() as session:
        friend = await load_player(session, FRIEND)
    context = ToolContext(sessions, benchmark_sessions, (FRIEND,), friend)
    model = FakeModel(calls(("champion_stats", {"role": None})), says("Friend7#EUW plays 2 games of Ornn."))

    answer = await ask_coach(model, context, "How is this player doing?")

    first = model.sent[0][0]["content"]
    assert "Friend7#EUW" in first and "not the person asking" in first
    # The 7 in the name isn't a made-up number.
    assert answer.status == "verified"


async def test_the_owner_is_asked_about_as_before(sessions, benchmark_sessions):  # noqa: F811
    await two_players(sessions)
    async with sessions() as session:
        me = await load_player(session)
    context = ToolContext(sessions, benchmark_sessions, (ME,), me)
    model = FakeModel(says("Play more games."))

    await ask_coach(model, context, "How am I doing?")

    assert model.sent[0][0]["content"] == "How am I doing?"


def test_no_tool_lets_the_model_choose_a_player():
    from agent.tools import tool_definitions

    for tool in tool_definitions():
        names = set(tool["input_schema"].get("properties", {}))
        assert not names & {"player", "puuid", "puuids"}, tool["name"]
