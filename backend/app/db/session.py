"""
Purpose: Async SQLAlchemy engine and session factory for AgentPay.

Responsibilities:
- Create a single, lazily-initialized async engine from Settings.database_url.
- Provide get_db_session(), a FastAPI-style async generator dependency that
  yields a scoped AsyncSession per request/test and always closes it.

This module reads configuration only through app.core.config.get_settings() —
never os.environ directly (plan.md Section 45).
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async SQLAlchemy engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, echo=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide async session factory, creating it on first use."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield a scoped AsyncSession for the duration of a request or test.

    Usage (FastAPI): `session: AsyncSession = Depends(get_db_session)`.
    The session is always closed on exit, including when the caller raises.
    """
    factory = get_session_factory()
    async with factory() as session:
        yield session
