"""The demo data's anonymization, and the shipped dataset itself."""

import gzip
import json
from pathlib import Path

import pytest

from demo.anonymize import (
    DEMO_START,
    ME,
    Anonymizer,
    champion_names,
    find_originals,
    offset_for,
    originals,
)

DATASET = Path(__file__).parent.parent / "demo" / "matches.json.gz"
REAL_ME = "R" * 78
OTHER = "O" * 78


def payloads():
    def participant(pid, puuid, name):
        return {
            "participantId": pid,
            "puuid": puuid,
            "riotIdGameName": name,
            "riotIdTagline": "EUW",
            "summonerName": name,
            "summonerId": f"real-summoner-{name}-0000000000",
            "profileIcon": 4567,
            "summonerLevel": 312,
            "championName": "Ornn",
            "kills": 3,
        }

    match = {
        "metadata": {"matchId": "EUW1_7777777777", "participants": [REAL_ME, OTHER]},
        "info": {
            "gameId": 7777777777,
            "gameName": "teambuilder-match-7777777777",
            "gameCreation": 1_800_000_000_000,
            "gameStartTimestamp": 1_800_000_010_000,
            "gameEndTimestamp": 1_800_001_810_000,
            "participants": [participant(1, REAL_ME, "RealMe"), participant(2, OTHER, "Stranger")],
        },
    }
    timeline = {
        "metadata": {"matchId": "EUW1_7777777777", "participants": [REAL_ME, OTHER]},
        "info": {
            "gameId": 7777777777,
            "participants": [{"participantId": 1, "puuid": REAL_ME}, {"participantId": 2, "puuid": OTHER}],
            "frames": [
                {
                    "timestamp": 60_000,
                    "events": [
                        {"type": "PAUSE_END", "timestamp": 0, "realTimestamp": 1_800_000_010_500},
                        {"type": "GAME_END", "gameId": 7777777777, "timestamp": 1_800_000},
                    ],
                }
            ],
        },
    }
    account = {"puuid": REAL_ME, "gameName": "RealMe", "tagLine": "EUW"}
    return match, timeline, account


def anonymized():
    match, timeline, account = payloads()
    anon = Anonymizer(REAL_ME, offset_for([match]))
    return anon.walk(match, 1), anon.walk(timeline, 1), originals(match, timeline, account)


def test_no_original_identity_is_left():
    match, timeline, banned = anonymized()
    assert find_originals([match, timeline], banned) == []


def test_the_player_becomes_demo_jungler_and_others_get_numbers():
    match, timeline, _ = anonymized()
    me, other = match["info"]["participants"]
    assert (me["puuid"], me["riotIdGameName"], me["riotIdTagline"]) == (ME, "DemoJungler", "DEMO")
    assert (other["puuid"], other["riotIdGameName"]) == ("demo-player-001", "Player 1")
    assert match["metadata"]["participants"] == [ME, "demo-player-001"]
    assert timeline["info"]["participants"][1]["puuid"] == "demo-player-001"


def test_ids_and_lobby_names_are_replaced_everywhere():
    match, timeline, _ = anonymized()
    assert match["metadata"]["matchId"] == timeline["metadata"]["matchId"] == "DEMO1_0001"
    assert match["info"]["gameId"] == timeline["info"]["gameId"] == 1
    assert timeline["info"]["frames"][0]["events"][1]["gameId"] == 1
    assert match["info"]["gameName"] == "demo"


def test_clock_times_shift_together_and_game_times_dont():
    match, timeline, _ = anonymized()
    info = match["info"]
    assert info["gameStartTimestamp"] == int(DEMO_START.timestamp() * 1000)
    assert info["gameEndTimestamp"] - info["gameStartTimestamp"] == 1_800_000
    assert timeline["info"]["frames"][0]["events"][0]["realTimestamp"] - info["gameStartTimestamp"] == 500
    assert timeline["info"]["frames"][0]["events"][1]["timestamp"] == 1_800_000


def test_quasi_identifiers_are_the_same_for_everyone():
    match, _, _ = anonymized()
    assert {p["profileIcon"] for p in match["info"]["participants"]} == {29}
    assert {p["summonerLevel"] for p in match["info"]["participants"]} == {100}


def test_stats_are_kept():
    match, _, _ = anonymized()
    assert [p["kills"] for p in match["info"]["participants"]] == [3, 3]


def test_a_player_keeps_one_identity_across_matches():
    match, _, _ = payloads()
    anon = Anonymizer(REAL_ME, 0)
    first = anon.walk(match, 1)["info"]["participants"][1]["puuid"]
    second = anon.walk(match, 2)["info"]["participants"][1]["puuid"]
    assert first == second == "demo-player-001"


def test_a_missed_field_is_found():
    match, timeline, banned = anonymized()
    match["info"]["participants"][1]["nickname"] = "Stranger"
    match["info"]["note"] = f"seen {OTHER} here"
    assert find_originals(match, banned) == ["Stranger", f"seen {OTHER} here"]


def test_a_player_named_after_a_champion_is_still_renamed():
    match, timeline, account = payloads()
    match["info"]["participants"][1]["riotIdGameName"] = "Viego"
    match["info"]["participants"][1]["championName"] = "Viego"
    anon = Anonymizer(REAL_ME, 0)
    out = anon.walk(match, 1)
    assert out["info"]["participants"][1]["riotIdGameName"] == "Player 1"
    # The word stays as the champion; only the champion names are exempted.
    banned = originals(match, timeline, account) - champion_names([match])
    assert find_originals(out, banned) == []
    assert "Stranger" in banned


@pytest.mark.skipif(not DATASET.exists(), reason="demo dataset not exported yet")
def test_the_shipped_dataset_has_only_demo_identities():
    data = json.loads(gzip.decompress(DATASET.read_bytes()))
    assert len(data["matches"]) == 12
    puuids = set()
    for m in data["matches"]:
        puuids |= set(m["match"]["metadata"]["participants"])
        assert m["match"]["metadata"]["matchId"].startswith("DEMO1_")
        names = {p["riotIdGameName"] for p in m["match"]["info"]["participants"]}
        assert all(n == "DemoJungler" or n.startswith("Player ") for n in names)
    assert all(p == ME or p.startswith("demo-player-") for p in puuids)
    assert data["player"] == {"puuid": ME, "gameName": "DemoJungler", "tagLine": "DEMO"}
