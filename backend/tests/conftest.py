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

from app.ai.gemini_client import get_gemini_client
from app.db import session as db_session


@pytest_asyncio.fixture(autouse=True)
async def _reset_db_engine_per_test():
    """Dispose the cached async engine after each test (see module docstring)."""
    yield
    if db_session._engine is not None:
        await db_session._engine.dispose()
    db_session._engine = None
    db_session._session_factory = None


@pytest_asyncio.fixture(autouse=True)
async def _reset_gemini_client_per_test():
    """
    Close and clear the cached Gemini client after each test.

    Same root cause as _reset_db_engine_per_test above: app.ai.gemini_client
    .get_gemini_client() is process-cached (functools.lru_cache) and holds a
    live httpx.AsyncClient bound to whichever event loop first created it.
    Since Phase 8, any request_checkout() call may transitively invoke
    Gemini (via the Merchant Revenue Agent / Intent Gate), so a client
    cached during one test's event loop breaks ("Event loop is closed")
    when reused during a later, unrelated test. Closing and clearing it here
    -- while this test's own loop is still alive -- keeps every test's
    Gemini client scoped to that test's own loop, mirroring how the DB
    engine is reset above.
    """
    yield
    if get_gemini_client.cache_info().currsize > 0:
        client = get_gemini_client()
        await client.aio.aclose()
    get_gemini_client.cache_clear()
