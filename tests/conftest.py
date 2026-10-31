"""Database fixtures. Tests use their own `lolcoach_test` database, never the
real one. They need `docker compose up -d db`, and skip if it isn't running."""

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ingestion.config import Settings
from ingestion.models import Base

TEST_DB = "lolcoach_test"


def _ensure_test_database(settings: Settings) -> None:
    async def run() -> None:
        engine = create_async_engine(
            settings.database_url, isolation_level="AUTOCOMMIT"
        )
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DB},
            )
            if not exists:
                await connection.execute(text(f"CREATE DATABASE {TEST_DB}"))
        await engine.dispose()

    asyncio.run(run())


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    settings = Settings(postgres_host=os.getenv("POSTGRES_HOST", "localhost"))
    try:
        _ensure_test_database(settings)
    except OSError:
        pytest.skip("Postgres isn't running: docker compose up -d db")
    return settings.model_copy(update={"postgres_db": TEST_DB})


@pytest.fixture
async def sessions(test_settings):
    engine = create_async_engine(test_settings.database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
