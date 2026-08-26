# AgentPay Backend

FastAPI backend for AgentPay: mandate signing/verification, the deterministic policy
engine, cart integrity, the Merchant Revenue Agent (LangGraph), the intent gate,
Razorpay integration, the MCP server, and the hash-chained audit log.

See `../plan.md` for the full architecture and build order. The `app/` package
structure is built incrementally, phase by phase (Section 4 has the final layout);
it does not exist yet as of this scaffold.

## Setup

```bash
uv sync
```

This creates `.venv/` and installs all dependencies declared in `pyproject.toml`.

## Run tests

```bash
uv run pytest
```

By default, the Merchant Revenue Agent's and Intent Gate's LLM calls
(`classify_with_schema`) are mocked to fail closed -- fast, deterministic,
no `GROQ_API_KEY` or network access needed, and no risk of hitting Groq's
rate limit or polluting the dev database with test fixtures while waiting
on real completions. Tests that specifically exercise LLM-driven behavior
mock these calls themselves regardless.

Before a demo, run the same suite against real Groq to confirm the live
integration still works end-to-end:

```bash
REAL_LLM_TESTS=1 uv run pytest
```

## Run the dev server

Not yet available — `app/main.py` is created in a later phase.
