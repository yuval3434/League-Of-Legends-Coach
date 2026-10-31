import asyncio

import pytest

from ingestion.rate_limiter import SAFETY_MARGIN_S, RateLimiter, parse_limits


class FakeTime:
    """A clock that only moves when the limiter sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept = 0.0

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds
        self.slept += seconds
        await asyncio.sleep(0)


@pytest.fixture
def fake_time() -> FakeTime:
    return FakeTime()


@pytest.fixture
def limiter(fake_time: FakeTime) -> RateLimiter:
    return RateLimiter(clock=fake_time.clock, sleep=fake_time.sleep)


def test_parse_limits():
    assert parse_limits("20:1,100:120") == [(20, 1), (100, 120)]


async def test_calls_under_the_limit_do_not_wait(limiter, fake_time):
    for _ in range(20):
        await limiter.acquire("europe", "match")
    assert fake_time.slept == 0


async def test_short_window_blocks_call_21(limiter, fake_time):
    for _ in range(21):
        await limiter.acquire("europe", "match")
    assert fake_time.slept == pytest.approx(1 + SAFETY_MARGIN_S)


async def test_never_more_than_100_calls_in_any_two_minutes(limiter, fake_time):
    sent = []
    for _ in range(250):
        await limiter.acquire("europe", "match")
        sent.append(fake_time.now)

    for start in sent:
        in_span = [t for t in sent if start <= t < start + 120]
        assert len(in_span) <= 100


async def test_concurrent_callers_cannot_overshoot(limiter, fake_time):
    sent = []

    async def call():
        await limiter.acquire("europe", "match")
        sent.append(fake_time.now)

    await asyncio.gather(*(call() for _ in range(50)))

    for start in sent:
        assert len([t for t in sent if start <= t < start + 1]) <= 20


async def test_regions_are_counted_separately(limiter, fake_time):
    for _ in range(20):
        await limiter.acquire("europe", "match")
        await limiter.acquire("americas", "match")
    assert fake_time.slept == 0


async def test_method_limit_learned_from_headers(limiter, fake_time):
    limiter.observe("europe", "timeline", {"X-Method-Rate-Limit": "2:10"})

    for _ in range(3):
        await limiter.acquire("europe", "timeline")

    assert fake_time.slept == pytest.approx(10 + SAFETY_MARGIN_S)


async def test_method_limit_does_not_affect_other_methods(limiter, fake_time):
    limiter.observe("europe", "timeline", {"X-Method-Rate-Limit": "1:10"})

    await limiter.acquire("europe", "timeline")
    await limiter.acquire("europe", "match")

    assert fake_time.slept == 0


async def test_app_limit_is_replaced_by_headers(limiter, fake_time):
    limiter.observe("europe", "match", {"X-App-Rate-Limit": "2:5"})

    for _ in range(3):
        await limiter.acquire("europe", "match")

    assert fake_time.slept == pytest.approx(5 + SAFETY_MARGIN_S)


async def test_higher_server_count_is_adopted_after_restart(limiter, fake_time):
    limiter.observe(
        "europe",
        "match",
        {"X-App-Rate-Limit": "100:120", "X-App-Rate-Limit-Count": "100:120"},
    )

    await limiter.acquire("europe", "match")

    assert fake_time.slept == pytest.approx(120 + SAFETY_MARGIN_S)


async def test_lower_server_count_is_ignored(limiter, fake_time):
    for _ in range(5):
        await limiter.acquire("europe", "match")

    limiter.observe("europe", "match", {"X-App-Rate-Limit-Count": "1:1,1:120"})

    window = limiter._app["europe"][120]
    assert len(window.calls) == 5


async def test_pause_blocks_every_method_in_the_region(limiter, fake_time):
    limiter.pause("europe", 30)

    await limiter.acquire("europe", "match")

    assert fake_time.slept == pytest.approx(30)


async def test_pause_does_not_affect_other_regions(limiter, fake_time):
    limiter.pause("europe", 30)

    await limiter.acquire("americas", "match")

    assert fake_time.slept == 0
