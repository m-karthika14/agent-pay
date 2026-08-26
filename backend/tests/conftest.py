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
import os
from unittest.mock import AsyncMock, patch

import pytest_asyncio

from app.ai.errors import LLMUnavailableError
from app.ai.llm_client import get_llm_client
from app.db import session as db_session

REAL_LLM_ENV_VAR = "REAL_LLM_TESTS"


@pytest_asyncio.fixture(autouse=True)
async def _reset_db_engine_per_test():
    """Dispose the cached async engine after each test (see module docstring)."""
    yield
    if db_session._engine is not None:
        await db_session._engine.dispose()
    db_session._engine = None
    db_session._session_factory = None


@pytest_asyncio.fixture(autouse=True)
async def _reset_llm_client_per_test():
    """
    Close and clear the cached LLM (Groq) client after each test.

    Same root cause as _reset_db_engine_per_test above: app.ai.llm_client
    .get_llm_client() is process-cached (functools.lru_cache) and holds a
    live httpx-based client bound to whichever event loop first created it.
    Since Phase 8, any request_checkout() call may transitively invoke the
    LLM (via the Merchant Revenue Agent / Intent Gate), so a client cached
    during one test's event loop breaks ("Event loop is closed") when
    reused during a later, unrelated test. Closing and clearing it here --
    while this test's own loop is still alive -- keeps every test's LLM
    client scoped to that test's own loop, mirroring how the DB engine is
    reset above.
    """
    yield
    if get_llm_client.cache_info().currsize > 0:
        client = get_llm_client()
        await client.close()
    get_llm_client.cache_clear()


@pytest_asyncio.fixture(autouse=True)
async def _mock_llm_by_default():
    """
    Three-tier testing plan: normal development runs against a mocked LLM
    (this fixture, on by default); the pre-demo integration check and the
    live demo itself run against real Groq.

    Every request_checkout() call that passes hard checks transitively
    reaches the Merchant Revenue Agent (app.agents.merchant.nodes) and,
    if it proposes something, the Intent Gate (app.intent.gate) -- both are
    single classify_with_schema() calls to real Groq. Tests that don't
    specifically exercise that AI layer (most of the suite: cart/checkout/
    mandate/order/webhook routes) have no reason to make a real network
    call, wait on Groq's rate limit, or produce non-deterministic output --
    so by default, both call sites are patched to raise LLMUnavailableError,
    the same "model could not be consulted" path both already handle by
    design (the merchant agent fails soft to no proposal; the intent gate
    fails closed to ESCALATE -- see their own docstrings).

    A test that specifically needs a real or a specific LLM response (e.g.
    tests/unit/test_merchant_agent.py, tests/integration/
    test_checkout_advisory.py) already patches these same two targets
    itself; that test-local patch nests inside this one and correctly wins
    for the duration of its own `with` block, so this fixture never
    interferes with it.

    Set REAL_LLM_TESTS=1 to disable this default and run the whole suite
    against real Groq instead -- the "before demo" integration tier,
    confirming the actual Groq integration still works end-to-end.
    """
    if os.environ.get(REAL_LLM_ENV_VAR, "").lower() in {"1", "true", "yes"}:
        yield
        return

    unavailable = AsyncMock(
        side_effect=LLMUnavailableError(
            "Real LLM calls are disabled in the default test tier. Set "
            f"{REAL_LLM_ENV_VAR}=1 to run against real Groq, or mock "
            "classify_with_schema explicitly in this test if it needs a "
            "specific LLM response."
        )
    )
    with (
        patch("app.agents.merchant.nodes.classify_with_schema", new=unavailable),
        patch("app.intent.gate.classify_with_schema", new=unavailable),
    ):
        yield
