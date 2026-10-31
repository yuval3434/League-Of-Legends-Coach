"""FastAPI app. Run with one worker: the rate limiter lives in this process."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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
        )
        app.state.sync_status = {"state": "idle"}
        app.state.sync_task = None
        yield
        if app.state.sync_task:
            app.state.sync_task.cancel()
        await app.state.riot.aclose()
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
        if request.app.state.sync_status["state"] == "running":
            raise HTTPException(409, "A sync is already running")
        request.app.state.sync_status = {"state": "running"}
        request.app.state.sync_task = asyncio.create_task(run_sync(body))
        return request.app.state.sync_status

    @app.get("/sync/status")
    async def sync_status(request: Request) -> dict[str, Any]:
        return request.app.state.sync_status

    return app


app = create_app()
