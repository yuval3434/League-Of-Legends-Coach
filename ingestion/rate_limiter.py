"""In-memory sliding-window rate limiter for the Riot API.

State lives in this process, so the app must run as a single process.

Limits apply per region at two levels: the whole key ("app") and each
endpoint ("method"). A call must fit every window at both levels.
"""

import asyncio
import time
from collections import deque
from collections.abc import Awaitable, Callable, Mapping

# Riot counts a call when it arrives, but we timestamp it when it's sent. The
# margin stops a slow call landing in a window we believe has already ended.
SAFETY_MARGIN_S = 0.5

# Riot's published limits for personal keys, used until a response reports the
# real ones. (limit, period in seconds)
DEFAULT_APP_LIMITS = ((20, 1), (100, 120))


class Window:
    """Allows `limit` calls in any span of `period` seconds."""

    def __init__(self, limit: int, period: float) -> None:
        self.limit = limit
        self.period = period
        self.calls: deque[float] = deque()

    def wait_time(self, now: float) -> float:
        """Seconds until a call would fit (0 if it fits now)."""
        expiry = self.period + SAFETY_MARGIN_S
        while self.calls and now - self.calls[0] >= expiry:
            self.calls.popleft()
        if len(self.calls) < self.limit:
            return 0.0
        # The call that must expire to bring us back under the limit.
        return self.calls[-self.limit] + expiry - now


def parse_limits(header: str) -> list[tuple[int, int]]:
    """Parse Riot's "20:1,100:120" format into (count, period) pairs."""
    return [
        (int(count), int(period))
        for count, period in (pair.split(":") for pair in header.split(","))
    ]


class RateLimiter:
    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._app: dict[str, dict[int, Window]] = {}
        self._method: dict[tuple[str, str], dict[int, Window]] = {}
        self._paused_until: dict[str, float] = {}

    def _app_windows(self, region: str) -> dict[int, Window]:
        if region not in self._app:
            self._app[region] = {
                period: Window(limit, period) for limit, period in DEFAULT_APP_LIMITS
            }
        return self._app[region]

    def _method_windows(self, region: str, method: str) -> dict[int, Window]:
        # Empty until a response tells us the endpoint's limits.
        return self._method.setdefault((region, method), {})

    async def acquire(self, region: str, method: str) -> None:
        """Wait until a call is allowed, then reserve its slot."""
        while True:
            now = self._clock()
            windows = [
                *self._app_windows(region).values(),
                *self._method_windows(region, method).values(),
            ]
            wait = max(
                self._paused_until.get(region, now) - now,
                *(window.wait_time(now) for window in windows),
            )
            if wait <= 0:
                # No await since the check, so concurrent callers can't both
                # take the last slot.
                for window in windows:
                    window.calls.append(now)
                return
            await self._sleep(wait)

    def pause(self, region: str, seconds: float) -> None:
        """Stop all calls to a region, such as after a 429."""
        until = self._clock() + seconds
        self._paused_until[region] = max(self._paused_until.get(region, 0), until)

    def observe(self, region: str, method: str, headers: Mapping[str, str]) -> None:
        """Update limits and counts from a Riot response's headers."""
        for prefix, windows in (
            ("X-App-Rate-Limit", self._app_windows(region)),
            ("X-Method-Rate-Limit", self._method_windows(region, method)),
        ):
            if limits := headers.get(prefix):
                self._apply_limits(windows, parse_limits(limits))
            if counts := headers.get(f"{prefix}-Count"):
                self._apply_counts(windows, parse_limits(counts))

    @staticmethod
    def _apply_limits(
        windows: dict[int, Window], limits: list[tuple[int, int]]
    ) -> None:
        for period in windows.keys() - {period for _, period in limits}:
            del windows[period]
        for limit, period in limits:
            if period in windows:
                windows[period].limit = limit
            else:
                windows[period] = Window(limit, period)

    def _apply_counts(
        self, windows: dict[int, Window], counts: list[tuple[int, int]]
    ) -> None:
        """Adopt Riot's count if it's higher than ours.

        After a restart our memory is empty but Riot's count isn't. We don't
        know when those calls happened, so we assume now, the cautious choice.
        """
        now = self._clock()
        for count, period in counts:
            if window := windows.get(period):
                missing = count - len(window.calls)
                window.calls.extend([now] * missing)
