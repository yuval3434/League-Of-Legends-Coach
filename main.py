"""FastAPI app. Run with one worker: the rate limiter lives in this process."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from benchmarks.cohorts import COHORTS
from benchmarks.compare import compare
from benchmarks.models import create_benchmark_engine
from benchmarks.pull import pull_cohort, target_champions, tracked_puuids
from ingestion.config import Settings
from ingestion.rate_limiter import RateLimiter
from ingestion.riot_client import RiotClient, RiotError
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


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(settings.database_url)
        app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)
        app.state.riot = RiotClient(
            settings.riot_api_key.get_secret_value(),
            RateLimiter(),
            settings.riot_account_region,
            settings.riot_match_region,
            settings.riot_platform_region,
        )
        benchmark_engine = create_benchmark_engine(settings)
        app.state.benchmark_sessions = async_sessionmaker(
            benchmark_engine, expire_on_commit=False
        )
        app.state.sync_status = {"state": "idle"}
        app.state.sync_task = None
        app.state.pull_status = {"state": "idle"}
        app.state.pull_task = None
        yield
        for task in (app.state.sync_task, app.state.pull_task):
            if task:
                task.cancel()
        await app.state.riot.aclose()
        await benchmark_engine.dispose()
        await engine.dispose()

    app = FastAPI(title="LoL Coach", lifespan=lifespan)

    async def run_sync(request: SyncRequest) -> None:
        try:
            result = await sync_player(
                app.state.sessions,
                app.state.riot,
                request.game_name,
                request.tag_line,
                settings.riot_match_region,
                settings.sync_queues,
                settings.sync_match_count,
            )
            app.state.sync_status = {"state": "done", **asdict(result)}
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
        request.app.state.sync_status = {"state": "running"}
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
    ) -> dict[str, Any]:
        """Compare the tracked player with a cohort, optionally on one champion."""
        if cohort not in COHORTS:
            raise HTTPException(422, f"Unknown cohort: {cohort}")
        async with request.app.state.sessions() as my_session:
            puuids = sorted(await tracked_puuids(my_session))
            async with request.app.state.benchmark_sessions() as benchmark_session:
                return await compare(
                    my_session, benchmark_session, puuids, cohort, champion
                )

    return app


app = create_app()
