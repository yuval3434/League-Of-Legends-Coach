"""The champion-select board: gap rules over Data Dragon data, and the player's pool."""

import asyncio

import pytest
from sqlalchemy import func, select

from analytics.draft import (
    GAPS,
    enemy_composition,
    NO_MATCHUP_DATA,
    damage_type,
    draft_board,
    resolve,
)
from ingestion.ddragon import (
    CHAMPIONS_URL,
    VERSIONS_URL,
    load_champions,
    refresh_champions,
)
from ingestion.models import Champion, DdragonFile
from test_analytics import ME, add_game


def champ(champion, tags, attack, magic, name=None):
    return Champion(
        version="1.0.1",
        champion=champion,
        name=name or champion,
        tags=tags,
        attack=attack,
        magic=magic,
        defense=5,
    )


CHAMPIONS = {
    c.champion: c
    for c in (
        champ("Jinx", ["Marksman"], 9, 2),
        champ("Ahri", ["Mage", "Assassin"], 3, 8),
        champ("Garen", ["Fighter", "Tank"], 7, 1),
        champ("Viego", ["Assassin", "Fighter"], 6, 2),
        champ("Nunu", ["Tank", "Mage"], 4, 7, name="Nunu & Willump"),
        champ("Diana", ["Fighter", "Mage"], 7, 8),
        champ("MonkeyKing", ["Fighter", "Tank"], 8, 2, name="Wukong"),
        champ("Ezreal", ["Marksman", "Mage"], 7, 7),
        champ("Darius", ["Fighter", "Tank"], 9, 1),
    )
}


def missing(*allies):
    team = [CHAMPIONS[a] for a in allies]
    return [gap.id for gap in GAPS if gap.missing(team)]


def test_damage_type_comes_from_riots_ratings():
    assert damage_type(CHAMPIONS["Ahri"]) == "magic"
    assert damage_type(CHAMPIONS["Jinx"]) == "physical"
    assert damage_type(CHAMPIONS["Ezreal"]) == "mixed"


def test_gap_rules():
    assert missing("Jinx", "Ahri") == ["no_frontline"]
    assert missing("Jinx", "Viego") == ["no_frontline", "no_magic_damage"]
    assert missing("Ahri") == ["no_frontline", "no_physical_damage"]
    # A Tank is a frontline; so are two Fighters, but not one.
    assert "no_frontline" not in missing("Garen")
    assert "no_frontline" not in missing("Viego", "Diana")
    # A champion rated equal for both counts as both damage types.
    assert missing("Ezreal", "Garen") == []


def test_a_champion_adds_a_piece_only_if_the_rule_then_holds():
    frontline = GAPS[0]
    no_fighters = [CHAMPIONS["Jinx"], CHAMPIONS["Ahri"]]
    # A lone Fighter is still no frontline; a Tank is one.
    assert not frontline.added_by(no_fighters, CHAMPIONS["Viego"])
    assert frontline.added_by(no_fighters, CHAMPIONS["Nunu"])
    # A second Fighter makes one.
    assert frontline.added_by([CHAMPIONS["Jinx"], CHAMPIONS["Diana"]], CHAMPIONS["Viego"])
    # Nothing adds what the team already has.
    assert not frontline.added_by([CHAMPIONS["Garen"]], CHAMPIONS["Nunu"])


def enemy(*names):
    return enemy_composition([CHAMPIONS[n] for n in names])


def test_the_enemy_damage_mix_and_frontline_follow_the_same_rules():
    found = enemy("Darius", "Jinx", "Garen", "Viego")
    assert found["damage"] == {"physical": 4, "magic": 0, "mixed": 0}
    assert found["mix"] == "mostly_physical"
    # Tanks first; Fighters that aren't also Tanks second.
    assert (found["tanks"], found["fighters"], found["has_frontline"]) == (
        ["Darius", "Garen"], ["Viego"], True,
    )
    assert found["general_advice"]["text"].startswith("Against mostly physical damage")
    assert "not from the player's games" in found["general_advice"]["source"]


def test_the_mix_needs_three_picks_and_three_quarters():
    assert enemy("Ahri", "Nunu", "Diana")["mix"] == "mostly_magic"
    two = enemy("Ahri", "Nunu")
    assert two["mix"] is None and "general_advice" not in two
    # 2 of 4 physical, with one champion rated equal for both: no single type.
    split = enemy("Jinx", "Viego", "Ahri", "Ezreal")
    assert split["damage"] == {"physical": 2, "magic": 1, "mixed": 1}
    assert split["mix"] == "mixed" and "general_advice" not in split
    assert enemy("Ahri")["has_frontline"] is False
    assert enemy_composition([]) is None


def test_names_resolve_by_id_or_display_name():
    found = resolve(["wukong", "MonkeyKing", "nunu & willump", "Nunu"], CHAMPIONS)
    assert [c.champion for c in found] == ["MonkeyKing", "MonkeyKing", "Nunu", "Nunu"]
    with pytest.raises(ValueError, match="Unknown champions: Teemo"):
        resolve(["Ahri", "Teemo"], CHAMPIONS)


@pytest.mark.parametrize(
    ("allies", "enemies", "bans", "message"),
    [
        (["Ahri", "Jinx", "Garen", "Diana", "Darius"], [], [], "At most 4"),
        (["Ahri"], ["ahri"], [], "only be picked once: Ahri"),
        (["Ahri"], [], ["Ahri"], "can't be picked: Ahri"),
    ],
)
async def test_impossible_boards_are_refused(session, allies, enemies, bans, message):
    with pytest.raises(ValueError, match=message):
        await draft_board(session, [ME], CHAMPIONS, allies, enemies, bans)


async def play(session, champion, games, role="JUNGLE", first=0):
    for n in range(games):
        await add_game(
            session, match_id=f"{champion}_{role}_{first + n}", role=role,
            champion=champion, win=n % 2 == 0,
        )


async def test_board_shows_gaps_from_the_pool_without_ranking(session):
    await play(session, "Viego", 4)
    await play(session, "Nunu", 3)
    await play(session, "Garen", 3)
    await play(session, "Diana", 2)  # under the pool's 3 games
    await play(session, "Darius", 5, role="TOP")  # not a jungle game

    board = await draft_board(
        session, [ME], CHAMPIONS, ["Jinx", "Ahri"], ["Wukong"], ["Garen"]
    )

    assert [p["champion"] for p in board["pool"]] == ["Viego", "Garen", "Nunu"]
    viego = board["pool"][0]
    assert (viego["games"], viego["wins"], viego["low_sample"]) == (4, 2, True)
    # Jinx and Ahri have no Fighter, so Viego alone isn't a frontline.
    assert viego["fills"] == []
    assert board["pool"][1]["unavailable"] == "banned"
    assert "fills" not in board["pool"][1]
    assert board["gaps"] == [
        {
            "gap": "no_frontline",
            "description": GAPS[0].description,
            "filled_by": ["Nunu"],
        }
    ]
    assert board["enemy_team"][0]["champion"] == "MonkeyKing"
    assert "matchup" not in board["enemy_team"][0]  # said once, in "matchups"
    assert board["matchups"] == NO_MATCHUP_DATA
    # Shown, never chosen: no field ranks or names a best champion.
    assert not {"best", "recommended", "score", "rank"} & (set(board) | set(viego))


async def test_match_data_names_match_data_dragon_whatever_the_case(session):
    champions = CHAMPIONS | {"Fiddlesticks": champ("Fiddlesticks", ["Mage", "Support"], 2, 9)}
    await play(session, "FiddleSticks", 3)  # how match data spells it
    board = await draft_board(session, [ME], champions, ["Jinx"], [], [])
    entry = board["pool"][0]
    assert (entry["champion"], entry["tags"], entry["fills"]) == (
        "Fiddlesticks", ["Mage", "Support"], ["no_magic_damage"],
    )
    banned = await draft_board(session, [ME], champions, ["Jinx"], [], ["Fiddlesticks"])
    assert banned["pool"][0]["unavailable"] == "banned"


async def test_no_gaps_before_the_team_picks(session):
    await play(session, "Viego", 3)
    board = await draft_board(session, [ME], CHAMPIONS, [], [], [])
    assert board["gaps"] == []
    assert "fills" in board["pool"][0] and board["pool"][0]["fills"] == []
    assert any("Nothing is picked" in note for note in board["notes"])


def fake_ddragon(version, calls):
    files = {
        VERSIONS_URL: [version, "0.9.1"],
        CHAMPIONS_URL.format(version=version): {
            "data": {
                "MonkeyKing": {
                    "id": "MonkeyKing",
                    "name": "Wukong",
                    "tags": ["Fighter", "Tank"],
                    "info": {"attack": 8, "defense": 5, "magic": 2, "difficulty": 3},
                }
            }
        },
    }

    async def fetch(url):
        calls.append(url)
        return files[url]

    return fetch


async def test_data_dragon_is_stored_raw_and_parsed_once_per_version(session):
    calls = []
    assert await load_champions(session) == (None, {})
    assert await refresh_champions(session, fake_ddragon("1.0.1", calls)) == "1.0.1"
    await refresh_champions(session, fake_ddragon("1.0.1", calls))
    # The second refresh only checks the version.
    assert calls == [VERSIONS_URL, CHAMPIONS_URL.format(version="1.0.1"), VERSIONS_URL]
    assert await session.scalar(select(func.count()).select_from(DdragonFile)) == 1

    version, champions = await load_champions(session)
    wukong = champions["MonkeyKing"]
    assert version == "1.0.1"
    assert (wukong.name, wukong.tags, wukong.attack, wukong.magic) == (
        "Wukong", ["Fighter", "Tank"], 8, 2,
    )


async def test_the_api_stores_data_dragon_at_startup_and_serves_the_board(test_settings, sessions):
    from fastapi.testclient import TestClient
    from test_players import FRIEND, two_players

    from main import create_app

    await two_players(sessions)
    with TestClient(create_app(test_settings)) as client:
        assert client.get("/draft/champions").status_code == 503

    calls = []
    with TestClient(create_app(test_settings, fetch_ddragon=fake_ddragon("1.0.1", calls))) as client:
        # The startup refresh runs in the background; wait for it here.
        client.portal.call(asyncio.wait_for, client.app.state.ddragon_task, 5)
        listed = client.get("/draft/champions").json()
        mine = client.post("/draft", json={"allies": [], "enemies": ["Wukong"], "bans": []})
        friend = client.post("/draft", json={"player": FRIEND, "enemies": [], "allies": []})
        refused = client.post("/draft", json={"enemies": ["Teemo"]})
        too_many = client.post("/draft", json={"enemies": ["Wukong"] * 6})

    assert listed == {
        "version": "1.0.1",
        "champions": [{"champion": "MonkeyKing", "name": "Wukong", "tags": ["Fighter", "Tank"]}],
    }
    board = mine.json()
    assert [p["champion"] for p in board["pool"]] == ["Viego"]
    assert board["enemy_composition"]["picked"] == 1
    # The friend's 2 Ornn games are under the pool's 3, and their games aren't mine.
    assert friend.json()["pool"] == []
    assert refused.status_code == 422 and refused.json()["detail"] == "Unknown champions: Teemo."
    assert too_many.status_code == 422
    assert "puuid" not in mine.text.lower() and "Me" not in str(board)
