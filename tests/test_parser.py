from datetime import UTC, datetime

from factories import make_match, make_timeline
from ingestion.parser import parse_match, parse_timeline


def test_parse_match_fields():
    match, participants = parse_match(make_match(queue=440))

    assert match["match_id"] == "EUW1_1"
    assert match["queue_id"] == 440
    assert match["patch"] == "14.20"
    assert match["duration_s"] == 1800
    assert match["is_remake"] is False
    assert match["game_start_at"] == datetime.fromtimestamp(1_700_000_060, UTC)


def test_parse_match_keeps_all_ten_players():
    _, participants = parse_match(make_match())

    assert [p["participant_id"] for p in participants] == list(range(1, 11))
    assert participants[0]["lane_cs"] == 180
    assert participants[0]["jungle_cs"] == 12
    assert participants[0]["win"] is True
    assert participants[9]["win"] is False


def test_duration_in_milliseconds_is_converted():
    raw = make_match()
    del raw["info"]["gameEndTimestamp"]
    raw["info"]["gameDuration"] = 1_800_000

    match, _ = parse_match(raw)

    assert match["duration_s"] == 1800


def test_remake_is_detected():
    raw = make_match()
    raw["info"]["participants"][4]["gameEndedInEarlySurrender"] = True

    match, _ = parse_match(raw)

    assert match["is_remake"] is True


def test_parse_timeline_frames():
    frames, _ = parse_timeline(make_timeline())

    assert len(frames) == 20  # 2 frames x 10 players
    last = frames[-1]
    assert last["participant_id"] == 10
    assert last["minute"] == 1
    assert last["timestamp_ms"] == 60_012
    assert last["lane_cs"] == 40
    assert last["damage_to_champions"] == 800


def test_frame_without_position_is_stored_as_null():
    raw = make_timeline()
    del raw["info"]["frames"][0]["participantFrames"]["1"]["position"]

    frames, _ = parse_timeline(raw)

    assert frames[0]["position_x"] is None


def test_event_indexes_run_across_frames():
    _, events = parse_timeline(make_timeline())

    assert [e["event_index"] for e in events] == [0, 1, 2, 3, 4]


def test_event_columns_and_leftover_data():
    _, events = parse_timeline(make_timeline())
    kill = events[1]

    assert kill["actor_id"] == 3
    assert kill["victim_id"] == 7
    assert kill["position_x"] == 5000
    assert kill["data"] == {"bounty": 300}


def test_killer_zero_becomes_null():
    _, events = parse_timeline(make_timeline())

    assert events[2]["actor_id"] is None
    assert events[2]["victim_id"] == 2


def test_actor_comes_from_creator_and_participant_fields():
    _, events = parse_timeline(make_timeline())

    assert events[3]["actor_id"] == 4
    assert events[4]["actor_id"] == 1
