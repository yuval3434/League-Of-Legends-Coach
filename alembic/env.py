import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from ingestion.config import Settings
from ingestion.models import Base


def run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


async def main() -> None:
    engine = create_async_engine(Settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(run_migrations)
        await connection.commit()
    await engine.dispose()


asyncio.run(main())
