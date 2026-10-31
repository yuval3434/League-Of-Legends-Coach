"""Riot API client: Riot ID -> PUUID -> match IDs -> match details and timelines.

`_request` is the only code that talks to Riot, and it always goes through the
rate limiter. tests/test_riot_client.py checks this.
"""

import logging
import random
from typing import Any
from urllib.parse import quote

import httpx

from ingestion.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
MAX_BACKOFF_S = 60
MAX_IDS_PER_PAGE = 100


class RiotError(Exception):
    """Base class for Riot API failures."""


class RiotAuthError(RiotError):
    """401 or 403. The key is invalid, expired or blocked; retrying can't help."""


class RiotNotFound(RiotError):
    """404."""


class RiotRequestFailed(RiotError):
    """A rejected request, or retries ran out."""


def _backoff(attempt: int) -> float:
    return min(MAX_BACKOFF_S, 2**attempt) + random.random()


class RiotClient:
    def __init__(
        self,
        api_key: str,
        limiter: RateLimiter,
        account_region: str,
        match_region: str,
    ) -> None:
        self._limiter = limiter
        self._account_region = account_region
        self._match_region = match_region
        self._http = httpx.AsyncClient(
            headers={"X-Riot-Token": api_key}, timeout=10.0
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(
        self,
        region: str,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """GET a path, retrying 429s, 5xx and network errors.

        `method` names the endpoint for rate limiting, so it must not contain
        IDs. Waiting between attempts happens inside the limiter.
        """
        url = f"https://{region}.api.riotgames.com{path}"
        for attempt in range(MAX_ATTEMPTS):
            await self._limiter.acquire(region, method)
            try:
                response = await self._http.get(url, params=params)
            except httpx.TransportError as error:
                logger.warning("%s: network error: %s", method, error)
                self._limiter.pause(region, _backoff(attempt))
                continue

            self._limiter.observe(region, method, response.headers)
            status = response.status_code

            if status == 200:
                return response.json()
            if status == 404:
                raise RiotNotFound(path)
            if status in (401, 403):
                raise RiotAuthError(
                    f"Riot returned {status}. The API key is missing, invalid or "
                    "expired; development keys last 24 hours."
                )
            if status == 429:
                delay = self._retry_after(response) or _backoff(attempt)
                logger.warning(
                    "%s: 429 (%s), pausing %s for %.1fs",
                    method,
                    response.headers.get("X-Rate-Limit-Type", "no type"),
                    region,
                    delay,
                )
                self._limiter.pause(region, delay)
            elif status >= 500:
                logger.warning("%s: server error %d", method, status)
                self._limiter.pause(region, _backoff(attempt))
            else:
                raise RiotRequestFailed(f"{method}: Riot returned {status}")

        raise RiotRequestFailed(f"{method}: gave up after {MAX_ATTEMPTS} attempts")

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        try:
            return float(response.headers["Retry-After"])
        except (KeyError, ValueError):
            return None

    async def get_account(self, game_name: str, tag_line: str) -> dict[str, Any]:
        name, tag = quote(game_name, safe=""), quote(tag_line, safe="")
        return await self._request(
            self._account_region,
            "account-by-riot-id",
            f"/riot/account/v1/accounts/by-riot-id/{name}/{tag}",
        )

    async def get_match_ids(self, puuid: str, queue: int, count: int) -> list[str]:
        """Return up to `count` of a player's newest match IDs in one queue."""
        match_ids: list[str] = []
        while len(match_ids) < count:
            page_size = min(MAX_IDS_PER_PAGE, count - len(match_ids))
            page = await self._request(
                self._match_region,
                "match-ids-by-puuid",
                f"/lol/match/v5/matches/by-puuid/{quote(puuid, safe='')}/ids",
                {"queue": queue, "start": len(match_ids), "count": page_size},
            )
            match_ids.extend(page)
            if len(page) < page_size:
                break
        return match_ids

    async def get_match(self, match_id: str) -> dict[str, Any]:
        return await self._request(
            self._match_region,
            "match",
            f"/lol/match/v5/matches/{quote(match_id, safe='')}",
        )

    async def get_timeline(self, match_id: str) -> dict[str, Any]:
        return await self._request(
            self._match_region,
            "timeline",
            f"/lol/match/v5/matches/{quote(match_id, safe='')}/timeline",
        )
