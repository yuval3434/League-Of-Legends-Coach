"""The Draft page's champion card, and Data Dragon's per-champion files."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_analytics import ME, START, add_game
from test_benchmarks import EMERALD, SILVER, add_sampled_game, benchmark_sessions, fill_cohort  # noqa: F401
from test_draft import champ, fake_ddragon

from analytics.champion_card import champion_card
from ingestion.ddragon import (
    DETAIL_URL,
    load_details,
    parse_detail,
    plain_text,
    refresh_champion_details,
    refresh_champions,
)
from ingestion.models import DdragonFile
from main import create_app

FITS = {SILVER: None, EMERALD: None}


def detail_file(champion="MonkeyKing"):
    part = lambda name: {"name": name, "description": f"{name} text."}  # noqa: E731
    return {
        "data": {
            champion: {
                "id": champion,
                "title": "the Monkey King",
                "passive": {"name": "Stone Skin", "description": "Gains <b>armor</b>.<br><br>More."},
                "spells": [part("Crushing Blow"), part("Warrior Trickster"), part("Nimbus Strike"), part("Cyclone")],
                "allytips": ["Use Decoy to escape."],
                "enemytips": ["Wait for Cyclone before engaging."],
            }
        }
    }


def test_ability_text_loses_its_markup_but_keeps_its_breaks():
    assert plain_text("Gains <b>armor</b> &amp; speed.<br><br>More.") == "Gains armor & speed.\n\nMore."


def test_a_champion_file_becomes_abilities_and_tips():
    row = parse_detail("1.0.1", detail_file())
    assert [a["key"] for a in row["abilities"]] == ["Passive", "Q", "W", "E", "R"]
    assert row["abilities"][0] == {"key": "Passive", "name": "Stone Skin", "description": "Gains armor.\n\nMore."}
    assert (row["ally_tips"], row["enemy_tips"]) == (["Use Decoy to escape."], ["Wait for Cyclone before engaging."])


async def test_champion_files_are_stored_raw_and_parsed_once(session):
    calls = []
    fetch = fake_ddragon("1.0.1", calls)

    async def with_details(url):
        if url == DETAIL_URL.format(version="1.0.1", champion="MonkeyKing"):
            calls.append(url)
            return detail_file()
        return await fetch(url)

    await refresh_champions(session, with_details)
    assert await refresh_champion_details(session, "1.0.1", with_details) == 1
    assert await refresh_champion_details(session, "1.0.1", with_details) == 0
    assert calls.count(DETAIL_URL.format(version="1.0.1", champion="MonkeyKing")) == 1
    assert await session.scalar(select(func.count()).select_from(DdragonFile)) == 2
    details = await load_details(session, "1.0.1", ["MonkeyKing", "Teemo"])
    assert list(details) == ["MonkeyKing"] and details["MonkeyKing"].title == "the Monkey King"


async def play(session, champion, games, first=0, **kw):
    for n in range(games):
        await add_game(
            session, f"EUW1_{champion}_{first + n}", champion=champion,
            start=START + timedelta(days=first + n), win=n % 2 == 0, **kw,
        )


async def test_the_card_puts_the_champion_beside_the_overall_average(session, benchmark_sessions):  # noqa: F811
    await play(session, "Viego", 12, jungle_cs=180)
    await play(session, "Quinn", 3, first=20, jungle_cs=120)
    async with benchmark_sessions() as bench:
        card = await champion_card(session, bench, (ME,), "viego", FITS, None)
        few = await champion_card(session, bench, (ME,), "Quinn", FITS, None)

    assert (card["champion"], card["games"], card["low_sample"]) == ("Viego", 12, False)
    assert str(card["last_played"]) == str((START + timedelta(days=11)).date())
    cs = next(r for r in card["rows"] if r["stat"] == "cs_per_min")
    assert (cs["champion"]["games"], cs["overall"]["games"]) == (12, 15)
    assert cs["champion"]["value"] == 6.0 and cs["overall"]["value"] == 5.6
    assert few["low_sample"] is True
    assert all(r["champion"] is None or r["champion"]["low_sample"] for r in few["rows"])


async def test_a_benchmark_needs_30_games_and_emerald_win_rates_arent_compared(session, benchmark_sessions):  # noqa: F811
    await play(session, "Viego", 3)
    await play(session, "Quinn", 3, first=10)
    async with benchmark_sessions() as bench:
        await fill_cohort(bench)  # 30 Silver Viego games from 10 players
        for n in range(30):
            await add_sampled_game(
                bench, f"EUW1_E{n}", f"emerald-{n % 10}", cohort=EMERALD, patch="16.21"
            )
        viego = await champion_card(session, bench, (ME,), "Viego", FITS, None)
        quinn = await champion_card(session, bench, (ME,), "Quinn", FITS, None)
        unfit = await champion_card(
            session, bench, (ME,), "Viego", {SILVER: "This player is Gold.", EMERALD: None}, None
        )

    silver, emerald = viego["benchmarks"][SILVER], viego["benchmarks"][EMERALD]
    assert (silver["status"], silver["benchmark_games"], silver["benchmark_players"]) == ("ok", 30, 10)
    assert set(silver["win_rate"]) == {"value", "margin"} and set(silver["cs_per_min"]) == {"value", "margin"}
    assert emerald["status"] == "ok" and emerald["win_rate"] == "not_comparable"
    assert quinn["benchmarks"][SILVER]["status"] == "no_benchmark"
    assert "30 games from 10 players" in quinn["benchmarks"][SILVER]["note"]
    assert unfit["benchmarks"][SILVER]["status"] == "no_benchmark"
    assert "This player is Gold." in unfit["benchmarks"][SILVER]["note"]


async def test_the_card_finds_match_datas_spelling(session, benchmark_sessions):  # noqa: F811
    await play(session, "FiddleSticks", 3)
    async with benchmark_sessions() as bench:
        card = await champion_card(session, bench, (ME,), "Fiddlesticks", FITS, None)
        none = await champion_card(session, bench, (ME,), "Teemo", FITS, None)
    assert card["champion"] == "FiddleSticks" and card["games"] == 3
    assert none is None


async def test_the_endpoint_returns_the_card_and_riots_text(test_settings, sessions, benchmark_sessions):  # noqa: F811
    from test_players import two_players

    await two_players(sessions)  # the owner has 3 Viego games
    async with sessions() as session:
        await refresh_champions(session, fake_ddragon("1.0.1", []))
        from ingestion.models import ChampionDetail

        session.add(champ("Viego", ["Assassin", "Fighter"], 6, 2))
        session.add(ChampionDetail(**parse_detail("1.0.1", detail_file("Viego"))))
        await session.commit()
    with TestClient(create_app(test_settings)) as client:
        card = client.get("/draft/champion/Viego")
        missing = client.get("/draft/champion/Teemo")

    assert card.status_code == 200
    body = card.json()
    assert body["games"] == 3 and body["low_sample"] is True
    assert body["riot"]["enemy_tips"] == ["Wait for Cyclone before engaging."]
    assert missing.status_code == 404
    assert "puuid" not in card.text.lower()


async def test_a_card_in_another_role_shows_that_roles_cohorts(session, benchmark_sessions):  # noqa: F811
    await play(session, "Ahri", 4, role="MIDDLE")
    await play(session, "Ahri", 2, first=10)  # jungle Ahri: not this card's games
    fits = FITS | {"gold_middle": None}
    async with benchmark_sessions() as bench:
        card = await champion_card(session, bench, (ME,), "Ahri", fits, None, "MIDDLE")

    assert (card["role"], card["games"]) == ("MIDDLE", 4)
    assert list(card["benchmarks"]) == ["gold_middle"]
