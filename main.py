"""FastAPI app. Run with one worker: the rate limiter lives in this process."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

import anthropic
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent.coach import ask_coach
from agent.llm import LocalModelError, ModelClient, create_model, local_model_ready
from agent.models import BY_ID, CHOICES, estimated_cost
from agent.options import DEFAULT_MODEL as OPTIONS_MODEL
from agent.options import OPTIONS_MAX_TOKENS, cost_ceiling, messages, prepare
from agent.pricing import answer_cost
from agent.samples import summarize
from agent.tools import TOOLS, ToolContext, run_tool
from analytics.champion_card import champion_card, riot_notes
from analytics.matches import match_detail, recent_matches
from benchmarks.cohorts import (
    MIN_BENCHMARK_GAMES,
    MIN_BENCHMARK_PLAYERS,
    PULLABLE_TIERS,
    ROLES,
    TARGET_OVERALL,
    cohort_fits,
    cohorts_for,
    get_cohort,
    offered_roles,
    why_no_benchmark,
)
from benchmarks.compare import compare
from benchmarks.own import own_numbers
from benchmarks.estimate import PULL_MORE_MATCHES, SAFETY_MULTIPLE, pull_more, to_500
from benchmarks.models import create_benchmark_engine
from benchmarks.pull import BATCH, pull_cohort, target_champions, tracked_puuids
from benchmarks.stretches import farm_by_stretch
from ingestion.auto_sync import SyncSettings, sync_round
from ingestion.auto_sync import now as utc_now
from ingestion.config import Settings
from ingestion.ddragon import (
    GetJson,
    get_json,
    load_champions,
    load_details,
    refresh_champion_details,
    refresh_champions,
)
from ingestion.keys import KEYS, describe, key_value, save_key
from ingestion.rate_limiter import RateLimiter
from ingestion.players import SelectedPlayer, list_players, load_player
from ingestion.riot_client import RiotAuthError, RiotClient, RiotError, RiotNotFound
from ingestion.sync import sync_player

logging.basicConfig(level=logging.INFO)
# httpx logs every request at INFO, which would drown out sync progress.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Auto-sync's first round waits this long after startup.
AUTO_SYNC_FIRST_DELAY_S = 60

NOT_PULLABLE = (
    "Master and above can't be pulled yet: their ladder is behind a different "
    "Riot endpoint from the divided one the pull uses."
)


class SyncRequest(BaseModel):
    game_name: str
    tag_line: str


class PullRequest(BaseModel):
    """A pull for one cohort. By default it stops at 500 games.

    `more` checks PULL_MORE_MATCHES more, for champion benchmarks. `max_matches`
    sets the total checked directly, for scripts. `player` is whose champions in
    the cohort's role are the targets; the owner when not given.
    """

    cohort: str
    max_matches: int | None = None
    more: bool = False
    player: str | None = None


class DraftRequest(BaseModel):
    """What champion select shows: champions only, never a player."""

    player: str | None = None
    allies: list[str] = Field(default_factory=list, max_length=4)
    enemies: list[str] = Field(default_factory=list, max_length=5)
    bans: list[str] = Field(default_factory=list, max_length=10)
    # The player's role in this draft; their main role when not given.
    role: str | None = None


class OptionsRequest(DraftRequest):
    # One of GET /coach/models' ids; Sonnet unless the picker says otherwise.
    model: str = OPTIONS_MODEL


class KeyRequest(BaseModel):
    key: str = Field(min_length=8, max_length=200)


# Tests a candidate key with one cheap call; raises if the key is refused.
KeyTester = Callable[[str], Awaitable[None]]

# Requests to the settings endpoints must name one of these hosts. The port is
# bound to 127.0.0.1, so only this machine reaches the API; checking the Host
# also stops a website from posing as localhost through DNS rebinding.
LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}
# A header only a script on our own page sends. A browser asks the API before
# sending it from another site, and the API never says yes, so a page open in
# another tab can't change a key.
SETTINGS_HEADER = "X-LoLCoach-Settings"


def local_only(request: Request) -> None:
    # "localhost:8000" -> "localhost"; "[::1]:8000" -> "[::1]".
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].lower()
    if host not in LOCAL_HOSTS or request.headers.get(SETTINGS_HEADER) != "1":
        raise HTTPException(403, "Settings can only be changed from this computer's web app")


class CoachRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # The PUUID of the player to ask about, from GET /players. None is the owner.
    player: str | None = None
    # One of GET /coach/models' ids. None is COACH_MODEL from .env.
    model: str | None = None


def create_app(
    settings: Settings | None = None,
    coach_model: ModelClient | None = None,
    env_path: Path | None = None,
    key_testers: dict[str, KeyTester] | None = None,
    fetch_ddragon: GetJson | None = None,
    auto_sync: bool = False,
) -> FastAPI:
    """`coach_model` replaces the model named in settings, so tests can pass a fake.

    `env_path` is the .env that keys are read from and saved to; None (as in
    tests) leaves the keys in `settings` and turns the key settings off. `key_testers`
    replace the real key checks, so tests make no calls to Riot or Anthropic.
    `fetch_ddragon` stores Data Dragon's latest champions at startup; None (as in
    tests) fetches nothing. `auto_sync` syncs every player every
    `auto_sync_minutes`; off by default, so tests never call Riot.
    """
    settings = settings or Settings()
    # A key saved from the settings page is in .env, but a container keeps the
    # environment it was created with. So .env wins for the keys.
    for name, key in KEYS.items():
        if env_path and (stored := key_value(env_path, name)):
            setattr(settings, key.env.lower(), SecretStr(stored))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(settings.database_url)
        app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)
        # One limiter for every Riot client, so a replaced key keeps the count.
        app.state.limiter = RateLimiter()
        app.state.riot = riot_client(settings.riot_api_key.get_secret_value())
        benchmark_engine = create_benchmark_engine(settings)
        app.state.benchmark_sessions = async_sessionmaker(
            benchmark_engine, expire_on_commit=False
        )
        app.state.sync_status = {"state": "idle"}
        app.state.sync_task = None
        # Held by any sync, manual or automatic, so two never run at once.
        app.state.sync_lock = asyncio.Lock()
        every = settings.auto_sync_minutes if auto_sync else 0
        app.state.auto_sync = {"state": "waiting" if every else "off", "every_minutes": every}
        app.state.auto_sync_task = asyncio.create_task(auto_sync_loop()) if every else None
        # One round on demand, for tests; the loop above is the only caller otherwise.
        app.state.auto_sync_once = auto_sync_once
        app.state.pull_status = {"state": "idle"}
        app.state.pull_task = None
        # Models are built when first asked for, one per choice, and dropped when
        # the Anthropic key changes.
        app.state.models = {}
        app.state.ddragon_task = (
            asyncio.create_task(store_champions(app.state.sessions, fetch_ddragon))
            if fetch_ddragon
            else None
        )
        yield
        for task in (
            app.state.sync_task,
            app.state.pull_task,
            app.state.ddragon_task,
            app.state.auto_sync_task,
        ):
            if task:
                task.cancel()
        await app.state.riot.aclose()
        await benchmark_engine.dispose()
        await engine.dispose()

    app = FastAPI(title="LoL Coach", lifespan=lifespan)

    def riot_client(key: str) -> RiotClient:
        return RiotClient(
            key,
            app.state.limiter,
            settings.riot_account_region,
            settings.riot_match_region,
            settings.riot_platform_region,
        )

    async def test_riot(key: str) -> None:
        client = riot_client(key)
        try:
            await client.get_platform_status()
        finally:
            await client.aclose()

    async def test_anthropic(key: str) -> None:
        # Listing models costs nothing and uses no tokens.
        async with anthropic.AsyncAnthropic(api_key=key) as client:
            await client.models.list(limit=1)

    testers = key_testers or {"riot": test_riot, "anthropic": test_anthropic}

    def keys_file() -> Path:
        if env_path is None:
            raise HTTPException(503, "Key settings are off: the API wasn't given a .env file")
        return env_path

    async def auto_sync_once() -> None:
        """One round of auto-sync, unless a manual sync holds the lock."""
        every = app.state.auto_sync["every_minutes"]
        base = {"every_minutes": every, "last_run_at": utc_now()}
        if not settings.riot_api_key.get_secret_value():
            app.state.auto_sync = base | {"state": "no_key", "error": "RIOT_API_KEY is not set."}
            return
        if app.state.sync_lock.locked():
            app.state.auto_sync = base | {"state": "skipped", "error": "A manual sync was running."}
            return
        async with app.state.sync_lock:
            app.state.auto_sync = {**app.state.auto_sync, "state": "running"}
            try:
                outcome = await sync_round(
                    app.state.sessions,
                    app.state.riot,
                    SyncSettings(
                        settings.riot_match_region, settings.sync_queues, settings.sync_match_count
                    ),
                )
            except Exception:
                logger.exception("Auto-sync crashed")
                outcome = {"state": "failed", "error": "Unexpected error; see the server log."}
        app.state.auto_sync = base | outcome
        logger.info("Auto-sync: %s", {k: v for k, v in outcome.items() if k != "failed"})

    async def auto_sync_loop() -> None:
        # The first round soon after startup, so a restart picks up new games.
        await asyncio.sleep(AUTO_SYNC_FIRST_DELAY_S)
        while True:
            await auto_sync_once()
            await asyncio.sleep(app.state.auto_sync["every_minutes"] * 60)

    async def run_sync(request: SyncRequest) -> None:
        async with app.state.sync_lock:
            await sync_one(request)

    async def sync_one(request: SyncRequest) -> None:
        riot_id = f"{request.game_name}#{request.tag_line}"

        def progress(event: dict[str, Any]) -> None:
            app.state.sync_status = {"state": "running", "riot_id": riot_id, **event}

        try:
            result = await sync_player(
                app.state.sessions,
                app.state.riot,
                request.game_name,
                request.tag_line,
                settings.riot_match_region,
                settings.sync_queues,
                settings.sync_match_count,
                progress,
            )
            app.state.sync_status = {"state": "done", "riot_id": riot_id, **asdict(result)}
        except RiotNotFound:
            app.state.sync_status = {
                "state": "failed",
                "riot_id": riot_id,
                "error": f"No player called {riot_id} was found.",
            }
        except RiotAuthError:
            app.state.sync_status = {
                "state": "failed",
                "riot_id": riot_id,
                "error": (
                    "Riot refused the API key. Development keys expire every 24 hours: "
                    "put a new one in .env and restart the API."
                ),
            }
        except RiotError as error:
            logger.error("Sync failed: %s", error)
            app.state.sync_status = {"state": "failed", "error": str(error)}
        except Exception:
            logger.exception("Sync crashed")
            app.state.sync_status = {
                "state": "failed",
                "error": "Unexpected error; see the server log.",
            }

    async def run_pull(
        cohort: str, max_matches: int, until_overall: bool, targets: set[str]
    ) -> None:
        try:
            async with app.state.sessions() as session:
                skip = await tracked_puuids(session)
            outcomes = await pull_cohort(
                app.state.benchmark_sessions,
                app.state.riot,
                cohort,
                max_matches,
                targets,
                skip,
                until_overall,
            )
            app.state.pull_status = app.state.pull_status | {
                "state": "done",
                "outcomes": outcomes,
            }
        except RiotError as error:
            logger.error("Pull failed: %s", error)
            app.state.pull_status = {"state": "failed", "error": str(error)}
        except Exception:
            logger.exception("Pull crashed")
            app.state.pull_status = {
                "state": "failed",
                "error": "Unexpected error; see the server log.",
            }

    def refuse_if_busy(state: Any) -> None:
        """A sync and a pull share one call budget, so only one runs at a time."""
        if "running" in (state.sync_status["state"], state.pull_status["state"]):
            raise HTTPException(409, "A sync or benchmark pull is already running")

    async def selected(request: Request, player: str | None) -> SelectedPlayer:
        """The player a request is about: the PUUID given, or the owner."""
        async with request.app.state.sessions() as session:
            found = await load_player(session, player)
        if found is None and player:
            raise HTTPException(404, "No synced player has that PUUID")
        if found is None:
            raise HTTPException(409, "No player is synced yet: run POST /sync first")
        return found

    def context_for(request: Request, player: SelectedPlayer) -> ToolContext:
        state = request.app.state
        return ToolContext(state.sessions, state.benchmark_sessions, (player.puuid,), player)

    def fits(player: SelectedPlayer) -> dict[str, str | None]:
        return cohort_fits(
            player.rank_tier, player.role_games, player.main_role, player.rank_checked
        )

    async def cohort_sizes(request: Request) -> dict[str, dict[str, int]]:
        """Each cohort's all-champion games and players, and matches checked."""
        async with request.app.state.benchmark_sessions() as session:
            rows = await session.execute(
                text(
                    """
                    SELECT c.cohort,
                           (SELECT count(*) FROM scan_queue q
                            WHERE q.cohort = c.cohort AND q.outcome IS NOT NULL) AS checked,
                           (SELECT count(*) FROM sample s
                            WHERE s.cohort = c.cohort AND s.in_overall) AS games,
                           (SELECT count(DISTINCT s.puuid) FROM sample s
                            WHERE s.cohort = c.cohort AND s.in_overall) AS players
                    FROM (SELECT cohort FROM scan_queue UNION SELECT cohort FROM sample) c
                    """
                )
            )
            return {row.cohort: dict(row._mapping) for row in rows}

    @app.get("/settings/keys", dependencies=[Depends(local_only)])
    async def keys() -> dict[str, Any]:
        """Whether each key is set, its last 4 characters and when. Never the key."""
        return {name: describe(keys_file(), name) for name in KEYS}

    @app.put("/settings/keys/{name}", dependencies=[Depends(local_only)])
    async def set_key(name: str, body: KeyRequest, request: Request) -> dict[str, Any]:
        """Test a key with one cheap call, then save it to .env and start using it."""
        if name not in KEYS:
            raise HTTPException(404, f"No key called {name}")
        state = request.app.state
        if name == "riot":
            refuse_if_busy(state)
        key = body.key.strip()
        try:
            await testers[name](key)
        except (RiotError, anthropic.AuthenticationError, anthropic.PermissionDeniedError) as error:
            # RiotError's messages are our own, with Riot's status code and never the
            # key; for Anthropic, only the error's type, as below.
            detail = error if isinstance(error, RiotError) else type(error).__name__
            logger.warning("The %s key was refused on its test call: %s", name, detail)
            raise HTTPException(400, f"The {name.capitalize()} key was refused, so it wasn't saved.")
        except (anthropic.APIError, OSError) as error:
            # Don't log the error itself: some libraries put the request in it.
            logger.warning("Testing the %s key failed: %s", name, type(error).__name__)
            raise HTTPException(502, f"Couldn't reach {name.capitalize()} to test the key; it wasn't saved.")
        save_key(keys_file(), name, key)
        setattr(settings, KEYS[name].env.lower(), SecretStr(key))
        if name == "riot":
            old, state.riot = state.riot, riot_client(key)
            await old.aclose()
        else:
            state.models = {}
        logger.info("The %s key was replaced", name)
        return describe(keys_file(), name)

    @app.get("/health")
    async def health(request: Request) -> dict[str, str]:
        async with request.app.state.sessions() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.post("/sync", status_code=202)
    async def start_sync(body: SyncRequest, request: Request) -> dict[str, Any]:
        """Start syncing a player in the background. 100 matches take ~4 minutes."""
        if not settings.riot_api_key.get_secret_value():
            raise HTTPException(503, "RIOT_API_KEY is not set in .env")
        refuse_if_busy(request.app.state)
        request.app.state.sync_status = {
            "state": "running",
            "riot_id": f"{body.game_name}#{body.tag_line}",
            "stage": "starting",
        }
        if request.app.state.sync_lock.locked():
            raise HTTPException(409, "An automatic sync is running; try again in a minute")
        request.app.state.sync_task = asyncio.create_task(run_sync(body))
        return request.app.state.sync_status

    @app.get("/sync/auto")
    async def auto_sync_status(request: Request) -> dict[str, Any]:
        """Auto-sync's last round: when, how many new games, or why it stopped."""
        return request.app.state.auto_sync

    @app.get("/sync/status")
    async def sync_status(request: Request) -> dict[str, Any]:
        return request.app.state.sync_status

    @app.post("/benchmarks/pull", status_code=202)
    async def start_pull(body: PullRequest, request: Request) -> dict[str, Any]:
        """Pull a cohort: to 500 games, `more` for champion benchmarks, or to
        `max_matches` checked in total. Free, but it uses the Riot call budget."""
        if not settings.riot_api_key.get_secret_value():
            raise HTTPException(503, "RIOT_API_KEY is not set in .env")
        cohort = get_cohort(body.cohort)
        if cohort is None:
            raise HTTPException(422, f"Unknown cohort: {body.cohort}")
        if cohort.tier not in PULLABLE_TIERS:
            raise HTTPException(422, NOT_PULLABLE)
        refuse_if_busy(request.app.state)
        size = (await cohort_sizes(request)).get(body.cohort, {"checked": 0, "games": 0})
        until_overall = False
        if body.max_matches is not None:
            max_matches, mode = body.max_matches, "matches"
        elif body.more:
            max_matches, mode = size["checked"] + PULL_MORE_MATCHES, "more"
        else:
            estimate = to_500(size["games"])
            if not estimate["games_needed"]:
                raise HTTPException(
                    409, f"This cohort already has {TARGET_OVERALL} games: use Pull more."
                )
            max_matches = size["checked"] + max(estimate["matches"] * SAFETY_MULTIPLE, BATCH)
            until_overall, mode = True, "to_500"
        player = await selected(request, body.player)
        async with request.app.state.sessions() as session:
            targets = await target_champions(session, cohort.role, player.puuid)
        request.app.state.pull_status = {
            "state": "running",
            "cohort": body.cohort,
            "mode": mode,
            "max_matches": max_matches,
            "started_checked": size["checked"],
        }
        request.app.state.pull_task = asyncio.create_task(
            run_pull(body.cohort, max_matches, until_overall, targets)
        )
        return request.app.state.pull_status

    @app.get("/benchmarks/status")
    async def pull_status(request: Request) -> dict[str, Any]:
        """The last pull, with its cohort's games and matches checked so far."""
        status = request.app.state.pull_status
        if "cohort" not in status:
            return status
        size = (await cohort_sizes(request)).get(status["cohort"], {})
        return status | {"checked": size.get("checked", 0), "games": size.get("games", 0)}

    @app.get("/own")
    async def own(
        request: Request,
        role: str | None = Query(default=None),
        player: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """A player's own numbers in one role, all games and wins against losses.
        For when no benchmark fits them yet. Free: no model call."""
        chosen = await selected(request, player)
        role = role or chosen.main_role
        if role not in ROLES:
            raise HTTPException(422, "Give a role: TOP, JUNGLE, MIDDLE, BOTTOM or UTILITY")
        async with request.app.state.sessions() as session:
            return await own_numbers(session, [chosen.puuid], role) | {
                "games": chosen.role_games.get(role, 0)
            }

    @app.get("/benchmarks/offers")
    async def offers(request: Request, player: str | None = Query(default=None)) -> dict[str, Any]:
        """For each role the player gets benchmarks in, each cohort that could fit:
        its size, whether it fits, and what a pull would take."""
        chosen = await selected(request, player)
        roles = offered_roles(chosen.role_games, chosen.main_role)
        sizes = await cohort_sizes(request)
        has_key = bool(settings.riot_api_key.get_secret_value())
        result = []
        for role in roles:
            cohorts = []
            for name in cohorts_for(chosen.rank_tier, role):
                cohort = get_cohort(name)
                size = sizes.get(name, {"games": 0, "players": 0, "checked": 0})
                why_not = why_no_benchmark(name, chosen.rank_tier, roles, chosen.rank_checked)
                why_no_pull = (
                    why_not
                    or (None if cohort.tier in PULLABLE_TIERS else NOT_PULLABLE)
                    or (None if has_key else "Set a Riot API key in Settings to pull.")
                )
                cohorts.append(
                    {
                        "cohort": name,
                        "tier": cohort.tier,
                        "role": cohort.role,
                        "audience": cohort.audience,
                        "games": size["games"],
                        "players": size["players"],
                        "checked": size["checked"],
                        "has_benchmark": size["games"] >= MIN_BENCHMARK_GAMES
                        and size["players"] >= MIN_BENCHMARK_PLAYERS,
                        "why_not": why_not,
                        "why_no_pull": why_no_pull,
                        "to_500": to_500(size["games"]),
                        "pull_more": pull_more(),
                    }
                )
            result.append({"role": role, "games": chosen.role_games.get(role, 0), "cohorts": cohorts})
        return {"roles": result, "pull": await pull_status(request)}

    @app.get("/benchmarks/compare")
    async def compare_with_cohort(
        request: Request,
        cohort: str = Query(),
        champion: str | None = Query(default=None),
        player: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Compare a player with a cohort, if it fits them, optionally on one champion."""
        if get_cohort(cohort) is None:
            raise HTTPException(422, f"Unknown cohort: {cohort}")
        chosen = await selected(request, player)
        reason = why_no_benchmark(
            cohort,
            chosen.rank_tier,
            offered_roles(chosen.role_games, chosen.main_role),
            chosen.rank_checked,
        )
        async with request.app.state.sessions() as my_session:
            async with request.app.state.benchmark_sessions() as benchmark_session:
                return await compare(
                    my_session, benchmark_session, [chosen.puuid], cohort, champion, reason
                )

    @app.get("/benchmarks/stretches")
    async def stretches(request: Request, player: str | None = Query(default=None)) -> dict[str, Any]:
        """Gold and CS per stretch, against the enemy jungler and each cohort that fits."""
        chosen = await selected(request, player)
        async with request.app.state.sessions() as my_session:
            async with request.app.state.benchmark_sessions() as benchmark_session:
                return await farm_by_stretch(
                    my_session,
                    benchmark_session,
                    [chosen.puuid],
                    fits(chosen),
                )

    def has_anthropic_key() -> bool:
        return bool(settings.anthropic_api_key.get_secret_value())

    def model_for(request: Request, choice: str) -> ModelClient:
        if coach_model is not None:
            return coach_model  # a test's fake
        if BY_ID[choice].provider == "anthropic" and not has_anthropic_key():
            raise HTTPException(503, "ANTHROPIC_API_KEY is not set in .env")
        models = request.app.state.models
        if choice not in models:
            models[choice] = create_model(settings, choice)
        return models[choice]

    @app.get("/matches")
    async def matches(
        request: Request,
        player: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        """A player's games, newest first."""
        chosen = await selected(request, player)
        async with request.app.state.sessions() as session:
            return await recent_matches(session, chosen.puuid, limit, offset)

    @app.get("/matches/{match_id}")
    async def match(
        request: Request, match_id: str, player: str | None = Query(default=None)
    ) -> dict[str, Any]:
        """One of the player's games, with both teams' champions and stats."""
        chosen = await selected(request, player)
        async with request.app.state.sessions() as session:
            found = await match_detail(session, chosen.puuid, match_id)
        if found is None:
            raise HTTPException(404, "This player has no game with that ID")
        return found

    @app.get("/draft/champions")
    async def draft_champions(request: Request) -> dict[str, Any]:
        """Every champion with its tags, for the champion-select picker."""
        async with request.app.state.sessions() as session:
            version, champions = await load_champions(session)
        if not champions:
            raise HTTPException(503, "Champion data from Data Dragon isn't loaded yet")
        return {
            "version": version,
            "champions": sorted(
                (
                    {"champion": c.champion, "name": c.name, "tags": list(c.tags)}
                    for c in champions.values()
                ),
                key=lambda c: c["name"],
            ),
        }

    @app.get("/draft/riot")
    async def draft_riot(
        request: Request, champions: str = Query(min_length=1, max_length=400)
    ) -> dict[str, Any]:
        """Riot's abilities and tips for comma-separated champions. Free."""
        names = [name.strip() for name in champions.split(",") if name.strip()][:20]
        async with request.app.state.sessions() as session:
            try:
                return await riot_notes(session, names)
            except ValueError as error:
                raise HTTPException(422, str(error)) from error

    @app.get("/draft/champion/{champion}")
    async def draft_champion(
        request: Request,
        champion: str,
        player: str | None = Query(default=None),
        role: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """One champion's card: the player's stats on it next to their overall
        average, each fitting cohort's benchmark on it, and Riot's text about it."""
        chosen = await selected(request, player)
        role = role or chosen.main_role or "JUNGLE"
        if role not in ROLES:
            raise HTTPException(422, "Give a role: TOP, JUNGLE, MIDDLE, BOTTOM or UTILITY")
        async with request.app.state.sessions() as my_session:
            version, champions = await load_champions(my_session)
            ids = {key.lower(): key for key in champions}
            detail = None
            if version and champion.lower() in ids:
                found = await load_details(my_session, version, [ids[champion.lower()]])
                detail = next(iter(found.values()), None)
            async with request.app.state.benchmark_sessions() as benchmark_session:
                card = await champion_card(
                    my_session,
                    benchmark_session,
                    (chosen.puuid,),
                    champion,
                    fits(chosen),
                    detail,
                    role,
                )
        if card is None:
            raise HTTPException(404, f"No games on {champion}")
        return card

    @app.post("/draft")
    async def draft(request: Request, body: DraftRequest) -> dict[str, Any]:
        """The champion-select board for what's on screen. Free: no model call."""
        context = context_for(request, await selected(request, body.player))
        result = await run_tool(
            context,
            "draft_board",
            {"allies": body.allies, "enemies": body.enemies, "bans": body.bans, "role": body.role},
        )
        if result.is_error:
            raise HTTPException(422, result.content)
        return json.loads(result.content)

    async def prepared_options(request: Request, body: OptionsRequest) -> Any:
        if body.model not in BY_ID:
            raise HTTPException(422, f"Unknown model: {body.model}")
        context = context_for(request, await selected(request, body.player))
        board = {"allies": body.allies, "enemies": body.enemies, "bans": body.bans, "role": body.role}
        # A model that cites numbers needs refs in the two results it's given.
        cite = BY_ID[body.model].provider == "anthropic"
        try:
            return context, await prepare(context, board, cite)
        except ValueError as error:
            raise HTTPException(422, str(error)) from error

    @app.post("/draft/options/estimate")
    async def options_estimate(request: Request, body: OptionsRequest) -> dict[str, Any]:
        """The most "Options for this draft" can cost on this board. Free: Anthropic
        doesn't charge for counting tokens."""
        _, prepared = await prepared_options(request, body)
        model = model_for(request, body.model)
        try:
            ceiling = await cost_ceiling(model, body.model, prepared)
        except anthropic.APIError:
            logger.exception("Counting tokens failed")
            raise HTTPException(502, "Couldn't count the tokens; see the server log.")
        return {"model": body.model, "champions": prepared.champions} | ceiling

    @app.post("/draft/options")
    async def options(request: Request, body: OptionsRequest) -> dict[str, Any]:
        """The coach's general notes on each available pool champion against this
        enemy team, from Riot's text. Paid, unless the local model answers."""
        context, prepared = await prepared_options(request, body)
        model = model_for(request, body.model)
        try:
            answer = await ask_coach(
                model,
                context,
                messages(prepared)[0]["content"],
                preloaded=prepared.preloaded,
                offer_tools=False,
                max_tokens=OPTIONS_MAX_TOKENS,
            )
        except anthropic.APIError:
            logger.exception("The model API call failed")
            raise HTTPException(502, "The model API call failed; see the server log.")
        except LocalModelError as error:
            raise HTTPException(502, f"The local model didn't answer. {error}")
        logger.info("Draft options: %s, caught %s, %s", answer.status, answer.caught_numbers, answer.usage)
        cost_usd, upper_bound = answer_cost(answer.usage, answer.models)
        return {k: v for k, v in asdict(answer).items() if k != "tool_log"} | {
            "champions": prepared.champions,
            "tools": [summarize(log) for log in answer.tool_log],
            "cost_usd": cost_usd,
            "cost_is_upper_bound": upper_bound,
        }

    @app.get("/coach/status")
    async def coach_status(request: Request) -> dict[str, Any]:
        """Whether a Claude model can answer: it needs ANTHROPIC_API_KEY. Free."""
        return {"available": coach_model is not None or has_anthropic_key()}

    @app.get("/coach/models")
    async def coach_models() -> list[dict[str, Any]]:
        """The models to pick from, each with its estimated cost per question. Free."""
        local = await local_model_ready(settings.ollama_url, settings.local_model)
        rows = []
        for choice in CHOICES:
            if choice.provider == "ollama":
                reason = local
                label = f"{choice.label} · {settings.local_model}"
            else:
                reason = None if has_anthropic_key() or coach_model else "Needs an Anthropic API key."
                label = choice.label
            rows.append(
                {
                    "id": choice.id,
                    "label": label,
                    "estimated_cost_usd": estimated_cost(choice.id),
                    "available": reason is None,
                    "reason": reason,
                    "default": choice.id == settings.coach_model,
                }
            )
        return rows

    @app.post("/coach")
    async def ask(body: CoachRequest, request: Request) -> dict[str, Any]:
        """Ask the coach a question. Paid, unless the local model answers."""
        choice = body.model or settings.coach_model
        if choice not in BY_ID:
            raise HTTPException(422, f"Unknown model: {choice}")
        model = model_for(request, choice)
        context = context_for(request, await selected(request, body.player))
        try:
            answer = await ask_coach(model, context, body.question)
        except anthropic.APIError:
            logger.exception("The model API call failed")
            raise HTTPException(502, "The model API call failed; see the server log.")
        except LocalModelError as error:
            logger.warning("The local model failed: %s", error)
            raise HTTPException(502, f"The local model didn't answer. {error}")
        logger.info(
            "Coach: %s, tools %s, caught %s, %s",
            answer.status,
            answer.tools_called,
            answer.caught_numbers,
            answer.usage,
        )
        # The full tool log is for the eval; the caller gets each call's sample sizes.
        body = {k: v for k, v in asdict(answer).items() if k != "tool_log"}
        cost_usd, upper_bound = answer_cost(answer.usage, answer.models)
        return body | {
            "tools": [summarize(log) for log in answer.tool_log],
            "cost_usd": cost_usd,
            "cost_is_upper_bound": upper_bound,
        }

    @app.get("/player")
    async def player_info(
        request: Request, player: str | None = Query(default=None)
    ) -> dict[str, Any]:
        """One player's Riot ID, rank, main role and benchmarks, for the profile header."""
        chosen = await selected(request, player)
        return asdict(chosen) | {
            "roles": offered_roles(chosen.role_games, chosen.main_role),
            "benchmarks": fits(chosen),
        }

    @app.get("/players")
    async def players(request: Request) -> list[dict[str, Any]]:
        """Every synced player, the owner first, for the player switcher."""
        async with request.app.state.sessions() as session:
            rows = await list_players(session)
        return [
            row
            | {
                "benchmarks": cohort_fits(
                    row["rank_tier"],
                    row["role_games"],
                    row["main_role"],
                    row["rank_checked_at"] is not None,
                )
            }
            for row in rows
        ]

    @app.get("/stats/{name}")
    async def stat(
        name: str,
        request: Request,
        champion: str | None = Query(default=None),
        cohort: str | None = Query(default=None),
        theme: str | None = Query(default=None),
        role: str | None = Query(default=None),
        player: str | None = Query(default=None),
    ) -> Any:
        """Run one of the coach's tools directly, for one player. Free: no model call."""
        tool = next((t for t in TOOLS if t.name == name), None)
        if tool is None:
            raise HTTPException(404, f"No stat called {name}")
        given = {"champion": champion, "cohort": cohort, "theme": theme, "role": role}
        arguments = {key: given[key] for key in tool.properties}
        context = context_for(request, await selected(request, player))
        result = await run_tool(context, name, arguments)
        if result.is_error:
            raise HTTPException(422, result.content)
        return json.loads(result.content)

    return app


async def store_champions(sessions: async_sessionmaker, fetch: GetJson) -> None:
    """Store Data Dragon's latest champions. Offline, the stored ones are used."""
    try:
        async with sessions() as session:
            version = await refresh_champions(session, fetch)
            added = await refresh_champion_details(session, version, fetch)
        logger.info("Data Dragon champions: version %s, %d champion files added", version, added)
    except Exception:
        logger.exception("Couldn't refresh Data Dragon's champions")


app = create_app(env_path=Path(".env"), fetch_ddragon=get_json, auto_sync=True)
