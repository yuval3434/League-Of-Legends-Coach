"""The Matches page's data: a player's games, and one game's two teams."""

from datetime import timedelta

from fastapi.testclient import TestClient
from test_analytics import ME, START, add_game
from test_players import FRIEND, two_players

from analytics.matches import match_detail, recent_matches
from main import create_app


async def test_recent_games_come_newest_first_with_the_total(session):
    for n in range(3):
        await add_game(
            session, f"EUW1_{n}", start=START + timedelta(days=n), champion="Viego",
            kills=n, lane_cs=10, jungle_cs=150,
        )
    await add_game(session, "EUW1_other", puuid="someone-else")

    page = await recent_matches(session, ME, limit=2)

    assert page["total"] == 3
    assert [m["match_id"] for m in page["matches"]] == ["EUW1_2", "EUW1_1"]
    first = page["matches"][0]
    assert (first["champion"], first["role"], first["kills"], first["cs"]) == ("Viego", "JUNGLE", 2, 160)
    rest = await recent_matches(session, ME, limit=2, offset=2)
    assert [m["match_id"] for m in rest["matches"]] == ["EUW1_0"]


async def test_a_game_shows_both_teams_by_role_with_no_identities(session):
    await add_game(session, "EUW1_1", role="JUNGLE", win=False, duration_s=1800,
                   champion="Viego", lane_cs=12, jungle_cs=168)

    game = await match_detail(session, ME, "EUW1_1")

    assert game["duration_s"] == 1800
    players = game["players"]
    assert [p["side"] for p in players] == ["ally"] * 5 + ["enemy"] * 5
    assert [p["role"] for p in players[:5]] == ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
    me = players[1]
    assert (me["is_me"], me["champion"], me["win"], me["cs"], me["cs_per_min"]) == (
        True, "Viego", False, 180, 6.0,
    )
    assert sum(p["is_me"] for p in players) == 1
    assert all(p["win"] for p in players[5:])
    assert "puuid" not in str(game) and "ally-TOP" not in str(game)


async def test_a_game_the_player_wasnt_in_is_not_shown(session):
    await add_game(session, "EUW1_1", puuid="someone-else")
    assert await match_detail(session, ME, "EUW1_1") is None


async def test_the_endpoints_follow_the_player_asked_for(test_settings, sessions):
    await two_players(sessions)  # the owner's games are EUW1_M*, the friend's EUW1_F*
    with TestClient(create_app(test_settings)) as client:
        mine = client.get("/matches").json()
        theirs = client.get("/matches", params={"player": FRIEND}).json()
        game = client.get("/matches/EUW1_M0")
        not_theirs = client.get("/matches/EUW1_M0", params={"player": FRIEND})
        too_many = client.get("/matches", params={"limit": 500})

    assert mine["total"] == 3 and {m["match_id"][:6] for m in mine["matches"]} == {"EUW1_M"}
    assert theirs["total"] == 2 and theirs["matches"][0]["champion"] == "Ornn"
    assert game.status_code == 200 and game.json()["players"][1]["is_me"]
    assert not_theirs.status_code == 404
    assert too_many.status_code == 422
    assert "puuid" not in game.text.lower()
