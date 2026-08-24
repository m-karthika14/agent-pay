"""
Purpose: Shared pytest fixtures for the AgentPay backend test suite.

app.db.session caches a single async engine/session-factory at module scope
for the running process. pytest-asyncio gives each async test its own event
loop by default, and asyncpg connections are bound to the loop they were
created on -- reusing a cached engine across tests then fails with
"another operation is in progress" / "Event loop is closed". This fixture
disposes and clears that cache after every test so each test lazily builds
a fresh engine bound to its own event loop.
"""
import pytest_asyncio

from app.db import session as db_session


@pytest_asyncio.fixture(autouse=True)
async def _reset_db_engine_per_test():
    """Dispose the cached async engine after each test (see module docstring)."""
    yield
    if db_session._engine is not None:
        await db_session._engine.dispose()
    db_session._engine = None
    db_session._session_factory = None
