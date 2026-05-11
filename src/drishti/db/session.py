from collections.abc import AsyncIterator
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.sql import text

from drishti.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={
            "statement_cache_size": 0,
            "prepared_statement_name_func": lambda: f"__drishti_{uuid4()}__",
        },
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def set_merchant_context(session: AsyncSession, merchant_id: UUID) -> None:
    await session.execute(
        text("SET LOCAL app.current_merchant_id = :merchant_id"),
        {"merchant_id": str(merchant_id)},
    )


async def set_merchant_context_for_worker(session: AsyncSession, merchant_id: UUID) -> None:
    await set_merchant_context(session, merchant_id)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    raise RuntimeError("Database session dependency was not initialized")
