from collections import Counter

import pytest
from sqlalchemy import func, select, update

from factories import make_match, make_timeline
from ingestion.models import (
    Match,
    MatchParticipant,
    Player,
    RawResponse,
    TimelineEvent,
    TimelineFrame,
)
from ingestion.riot_client import RiotAuthError, RiotNotFound, RiotRequestFailed
from ingestion.sync import parse_stored_match, sync_player

ACCOUNT = {"puuid": "puuid-1", "gameName": "yuval34", "tagLine": "34343"}


class FakeRiot:
    """Stands in for RiotClient, and counts the calls it receives."""

    def __init__(self, ids_by_queue: dict[int, list[str]]) -> None:
        self.ids_by_queue = ids_by_queue
        self.calls: Counter[str] = Counter()
        self.failures: dict[tuple[str, str], Exception] = {}

    async def get_account(self, game_name, tag_line):
        return ACCOUNT

    async def get_match_ids(self, puuid, queue, count):
        return self.ids_by_queue.get(queue, [])[:count]

    def _maybe_fail(self, kind, match_id):
        self.calls[kind] += 1
        if error := self.failures.get((kind, match_id)):
            raise error

    async def get_match(self, match_id):
        self._maybe_fail("match", match_id)
        return make_match(match_id)

    async def get_timeline(self, match_id):
        self._maybe_fail("timeline", match_id)
        return make_timeline(match_id)


async def run(sessions, riot, count=100, queues=(420, 440)):
    return await sync_player(
        sessions, riot, "yuval34", "34343", "europe", list(queues), count
    )


async def count(sessions, model) -> int:
    async with sessions() as session:
        return await session.scalar(select(func.count()).select_from(model))


async def test_sync_stores_raw_and_parsed_rows(sessions):
    riot = FakeRiot({420: ["EUW1_2"], 440: ["EUW1_1"]})

    result = await run(sessions, riot)

    assert (result.matches_found, result.matches_parsed) == (2, 2)
    assert await count(sessions, RawResponse) == 4
    assert await count(sessions, Match) == 2
    assert await count(sessions, MatchParticipant) == 20
    assert await count(sessions, TimelineFrame) == 40
    assert await count(sessions, TimelineEvent) == 10
    async with sessions() as session:
        player = await session.get(Player, "puuid-1")
    assert player.game_name == "yuval34"
    assert player.last_synced_at is not None


async def test_only_requested_queues_are_fetched(sessions):
    riot = FakeRiot({420: ["EUW1_1"], 450: ["EUW1_2"]})

    result = await run(sessions, riot, queues=(420,))

    assert result.matches_found == 1


async def test_count_keeps_the_newest_across_queues(sessions):
    riot = FakeRiot({420: ["EUW1_9", "EUW1_100"], 440: ["EUW1_50"]})

    await run(sessions, riot, count=2)

    async with sessions() as session:
        stored = await session.scalars(select(Match.match_id))
        assert set(stored.all()) == {"EUW1_100", "EUW1_50"}


async def test_second_sync_makes_no_match_calls(sessions):
    riot = FakeRiot({420: ["EUW1_1"]})
    await run(sessions, riot)
    riot.calls.clear()

    result = await run(sessions, riot)

    assert not riot.calls
    assert result.matches_parsed == 0


async def test_interrupted_sync_resumes_with_only_the_missing_call(sessions):
    riot = FakeRiot({420: ["EUW1_1"]})
    riot.failures["timeline", "EUW1_1"] = RiotRequestFailed("gave up")

    first = await run(sessions, riot)

    assert first.matches_failed == 1
    assert await count(sessions, Match) == 0

    riot.failures.clear()
    riot.calls.clear()
    second = await run(sessions, riot)

    assert second.matches_parsed == 1
    assert riot.calls == {"timeline": 1}


async def test_one_failure_does_not_stop_other_matches(sessions):
    riot = FakeRiot({420: ["EUW1_2", "EUW1_1"]})
    riot.failures["match", "EUW1_2"] = RiotRequestFailed("gave up")

    result = await run(sessions, riot)

    assert (result.matches_parsed, result.matches_failed) == (1, 1)


async def test_timeline_404_is_recorded_and_not_retried(sessions):
    riot = FakeRiot({420: ["EUW1_1"]})
    riot.failures["timeline", "EUW1_1"] = RiotNotFound("gone")

    result = await run(sessions, riot)

    assert result.matches_parsed == 1
    assert await count(sessions, TimelineFrame) == 0
    async with sessions() as session:
        raw = await session.get(RawResponse, ("EUW1_1", "timeline"))
    assert (raw.http_status, raw.payload) == (404, None)

    riot.calls.clear()
    await run(sessions, riot)
    assert not riot.calls


async def test_auth_error_stops_the_sync(sessions):
    riot = FakeRiot({420: ["EUW1_2", "EUW1_1"]})
    riot.failures["match", "EUW1_2"] = RiotAuthError("expired")

    with pytest.raises(RiotAuthError):
        await run(sessions, riot)

    assert riot.calls == {"match": 1}


async def test_parser_failure_keeps_raw_data(sessions):
    riot = FakeRiot({420: ["EUW1_1"]})
    good_get_match = riot.get_match

    async def broken_get_match(match_id):
        raw = await good_get_match(match_id)
        del raw["info"]["queueId"]
        return raw

    riot.get_match = broken_get_match

    result = await run(sessions, riot)

    assert result.matches_failed == 1
    assert await count(sessions, Match) == 0
    assert await count(sessions, RawResponse) == 2


async def test_reparse_rebuilds_rows_from_raw_without_riot(sessions):
    riot = FakeRiot({420: ["EUW1_1"]})
    await run(sessions, riot)
    async with sessions() as session:
        await session.execute(update(Match).values(queue_id=999))
        await session.commit()
    riot.calls.clear()

    async with sessions() as session:
        assert await parse_stored_match(session, "EUW1_1")

    assert not riot.calls
    assert await count(sessions, MatchParticipant) == 10
    assert await count(sessions, TimelineFrame) == 20
    async with sessions() as session:
        match = await session.get(Match, "EUW1_1")
    assert match.queue_id == 420
