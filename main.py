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
from agent.pricing import answer_cost
from agent.samples import summarize
from agent.tools import TOOLS, ToolContext, run_tool
from analytics.matches import match_detail, recent_matches
from benchmarks.cohorts import COHORTS, why_no_benchmark
from benchmarks.compare import compare
from benchmarks.models import create_benchmark_engine
from benchmarks.pull import pull_cohort, target_champions, tracked_puuids
from benchmarks.stretches import farm_by_stretch
from ingestion.config import Settings
from ingestion.ddragon import GetJson, get_json, load_champions, refresh_champions
from ingestion.keys import KEYS, describe, key_value, save_key
from ingestion.rate_limiter import RateLimiter
from ingestion.players import SelectedPlayer, list_players, load_player
from ingestion.riot_client import RiotAuthError, RiotClient, RiotError, RiotNotFound
from ingestion.sync import sync_player

logging.basicConfig(level=logging.INFO)
# httpx logs every request at INFO, which would drown out sync progress.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


class SyncRequest(BaseModel):
    game_name: str
    tag_line: str


class PullRequest(BaseModel):
    cohort: str
    max_matches: int


class DraftRequest(BaseModel):
    """What champion select shows: champions only, never a player."""

    player: str | None = None
    allies: list[str] = Field(default_factory=list, max_length=4)
    enemies: list[str] = Field(default_factory=list, max_length=5)
    bans: list[str] = Field(default_factory=list, max_length=10)


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
) -> FastAPI:
    """`coach_model` replaces the model named in settings, so tests can pass a fake.

    `env_path` is the .env that keys are read from and saved to; None (as in
    tests) leaves the keys in `settings` and turns the key settings off. `key_testers`
    replace the real key checks, so tests make no calls to Riot or Anthropic.
    `fetch_ddragon` stores Data Dragon's latest champions at startup; None (as in
    tests) fetches nothing.
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
        for task in (app.state.sync_task, app.state.pull_task, app.state.ddragon_task):
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

    async def run_sync(request: SyncRequest) -> None:
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

    async def run_pull(request: PullRequest) -> None:
        try:
            async with app.state.sessions() as session:
                targets = await target_champions(session)
                skip = await tracked_puuids(session)
            outcomes = await pull_cohort(
                app.state.benchmark_sessions,
                app.state.riot,
                request.cohort,
                request.max_matches,
                targets,
                skip,
            )
            app.state.pull_status = {
                "state": "done",
                "cohort": request.cohort,
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

    def benchmarks_for(
        rank_tier: str | None, main_role: str | None, rank_checked: bool
    ) -> dict[str, str | None]:
        """Each cohort, with why it doesn't fit the player, or None if it does."""
        return {
            cohort: why_no_benchmark(cohort, rank_tier, main_role, rank_checked)
            for cohort in COHORTS
        }

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
        except (RiotError, anthropic.AuthenticationError, anthropic.PermissionDeniedError):
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
        request.app.state.sync_task = asyncio.create_task(run_sync(body))
        return request.app.state.sync_status

    @app.get("/sync/status")
    async def sync_status(request: Request) -> dict[str, Any]:
        return request.app.state.sync_status

    @app.post("/benchmarks/pull", status_code=202)
    async def start_pull(body: PullRequest, request: Request) -> dict[str, Any]:
        """Check a cohort's matches until `max_matches` are checked in total."""
        if not settings.riot_api_key.get_secret_value():
            raise HTTPException(503, "RIOT_API_KEY is not set in .env")
        if body.cohort not in COHORTS:
            raise HTTPException(422, f"Unknown cohort: {body.cohort}")
        refuse_if_busy(request.app.state)
        request.app.state.pull_status = {"state": "running", "cohort": body.cohort}
        request.app.state.pull_task = asyncio.create_task(run_pull(body))
        return request.app.state.pull_status

    @app.get("/benchmarks/status")
    async def pull_status(request: Request) -> dict[str, Any]:
        return request.app.state.pull_status

    @app.get("/benchmarks/compare")
    async def compare_with_cohort(
        request: Request,
        cohort: str = Query(),
        champion: str | None = Query(default=None),
        player: str | None = Query(default=None),
    ) -> dict[str, Any]:
        """Compare a player with a cohort, if it fits them, optionally on one champion."""
        if cohort not in COHORTS:
            raise HTTPException(422, f"Unknown cohort: {cohort}")
        chosen = await selected(request, player)
        reason = why_no_benchmark(
            cohort, chosen.rank_tier, chosen.main_role, chosen.rank_checked
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
                    benchmarks_for(chosen.rank_tier, chosen.main_role, chosen.rank_checked),
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

    @app.post("/draft")
    async def draft(request: Request, body: DraftRequest) -> dict[str, Any]:
        """The champion-select board for what's on screen. Free: no model call."""
        context = context_for(request, await selected(request, body.player))
        result = await run_tool(
            context,
            "draft_board",
            {"allies": body.allies, "enemies": body.enemies, "bans": body.bans},
        )
        if result.is_error:
            raise HTTPException(422, result.content)
        return json.loads(result.content)

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
            "benchmarks": benchmarks_for(
                chosen.rank_tier, chosen.main_role, chosen.rank_checked
            )
        }

    @app.get("/players")
    async def players(request: Request) -> list[dict[str, Any]]:
        """Every synced player, the owner first, for the player switcher."""
        async with request.app.state.sessions() as session:
            rows = await list_players(session)
        return [
            row
            | {
                "benchmarks": benchmarks_for(
                    row["rank_tier"], row["main_role"], row["rank_checked_at"] is not None
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
        logger.info("Data Dragon champions: version %s", version)
    except Exception:
        logger.exception("Couldn't refresh Data Dragon's champions")


app = create_app(env_path=Path(".env"), fetch_ddragon=get_json)
