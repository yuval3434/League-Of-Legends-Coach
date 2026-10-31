import re
from pathlib import Path

import httpx
import pytest
import respx

from ingestion.rate_limiter import RateLimiter
from ingestion.riot_client import (
    MAX_ATTEMPTS,
    RiotAuthError,
    RiotClient,
    RiotNotFound,
    RiotRequestFailed,
)

BASE = "https://europe.api.riotgames.com"
MATCH_URL = f"{BASE}/lol/match/v5/matches/EUW1_1"
ACCOUNT_URL = f"{BASE}/riot/account/v1/accounts/by-riot-id/yuval34/34343"


class RecordingLimiter(RateLimiter):
    """A real limiter that records its use and never really waits."""

    def __init__(self) -> None:
        async def no_sleep(_: float) -> None:
            self._paused_until.clear()

        super().__init__(sleep=no_sleep)
        self.acquired = 0
        self.pauses: list[float] = []

    async def acquire(self, region: str, method: str) -> None:
        self.acquired += 1
        await super().acquire(region, method)

    def pause(self, region: str, seconds: float) -> None:
        self.pauses.append(seconds)
        super().pause(region, seconds)


@pytest.fixture
def limiter() -> RecordingLimiter:
    return RecordingLimiter()


@pytest.fixture
async def client(limiter):
    riot = RiotClient("test-key", limiter, "europe", "europe")
    yield riot
    await riot.aclose()


@respx.mock
async def test_get_account_sends_key_and_returns_json(client):
    route = respx.get(ACCOUNT_URL).respond(json={"puuid": "abc"})

    assert await client.get_account("yuval34", "34343") == {"puuid": "abc"}
    assert route.calls.last.request.headers["X-Riot-Token"] == "test-key"


@respx.mock
async def test_riot_id_is_url_encoded(client):
    route = respx.get(
        f"{BASE}/riot/account/v1/accounts/by-riot-id/a%20b%2Fc/EUW"
    ).respond(json={"puuid": "abc"})

    await client.get_account("a b/c", "EUW")

    assert route.called


@respx.mock
async def test_get_match_ids_pages_until_count(client):
    ids_url = f"{BASE}/lol/match/v5/matches/by-puuid/abc/ids"
    route = respx.get(ids_url).mock(
        side_effect=[
            httpx.Response(200, json=[f"EUW1_{i}" for i in range(100)]),
            httpx.Response(200, json=[f"EUW1_{i}" for i in range(100, 150)]),
        ]
    )

    match_ids = await client.get_match_ids("abc", 420, 150)

    assert len(match_ids) == 150
    second = route.calls[1].request.url.params
    assert second["start"] == "100"
    assert second["count"] == "50"
    assert second["queue"] == "420"


@respx.mock
async def test_get_match_ids_stops_when_history_runs_out(client):
    ids_url = f"{BASE}/lol/match/v5/matches/by-puuid/abc/ids"
    route = respx.get(ids_url).respond(json=["EUW1_1"])

    assert await client.get_match_ids("abc", 420, 100) == ["EUW1_1"]
    assert route.call_count == 1


@respx.mock
async def test_429_pauses_for_retry_after_then_retries(client, limiter):
    respx.get(MATCH_URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )

    assert await client.get_match("EUW1_1") == {"ok": True}
    assert limiter.pauses == [7]


@respx.mock
async def test_429_without_retry_after_backs_off(client, limiter):
    respx.get(MATCH_URL).mock(
        side_effect=[httpx.Response(429), httpx.Response(200, json={"ok": True})]
    )

    assert await client.get_match("EUW1_1") == {"ok": True}
    assert 1 <= limiter.pauses[0] < 2


@respx.mock
async def test_5xx_is_retried_then_gives_up(client):
    route = respx.get(MATCH_URL).respond(503)

    with pytest.raises(RiotRequestFailed):
        await client.get_match("EUW1_1")

    assert route.call_count == MAX_ATTEMPTS


@respx.mock
async def test_network_error_is_retried(client):
    respx.get(MATCH_URL).mock(
        side_effect=[httpx.ConnectError("boom"), httpx.Response(200, json={})]
    )

    assert await client.get_match("EUW1_1") == {}


@respx.mock
@pytest.mark.parametrize("status", [401, 403])
async def test_auth_errors_stop_immediately(client, status):
    route = respx.get(MATCH_URL).respond(status)

    with pytest.raises(RiotAuthError):
        await client.get_match("EUW1_1")

    assert route.call_count == 1


@respx.mock
async def test_404_is_not_retried(client):
    route = respx.get(MATCH_URL).respond(404)

    with pytest.raises(RiotNotFound):
        await client.get_match("EUW1_1")

    assert route.call_count == 1


@respx.mock
async def test_other_4xx_is_not_retried(client):
    route = respx.get(MATCH_URL).respond(400)

    with pytest.raises(RiotRequestFailed):
        await client.get_match("EUW1_1")

    assert route.call_count == 1


@respx.mock
async def test_every_attempt_goes_through_the_limiter(client, limiter):
    route = respx.get(MATCH_URL).mock(
        side_effect=[
            httpx.Response(500),
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(200, json={}),
        ]
    )

    await client.get_match("EUW1_1")

    assert route.call_count == 3
    assert limiter.acquired == 3


@respx.mock
async def test_limits_are_learned_from_responses(client, limiter):
    respx.get(MATCH_URL).respond(
        json={}, headers={"X-Method-Rate-Limit": "2000:10"}
    )

    await client.get_match("EUW1_1")

    assert limiter._method["europe", "match"][10].limit == 2000


def test_only_request_method_can_reach_riot():
    """Nothing can call Riot except through the rate-limited `_request`."""
    root = Path(__file__).parent.parent
    sources = {
        path: path.read_text(encoding="utf-8")
        for path in [root / "main.py", *(root / "ingestion").glob("*.py")]
        if path.exists()
    }

    importers = [
        path.name
        for path, text in sources.items()
        if re.search(r"^\s*(import|from)\s+httpx\b", text, re.MULTILINE)
    ]
    assert importers == ["riot_client.py"]

    client_source = sources[root / "ingestion" / "riot_client.py"]
    assert client_source.count("self._http.get(") == 1
    assert client_source.count("self._http.") == 2  # the get, plus aclose
