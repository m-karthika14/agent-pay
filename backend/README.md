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

## Run the dev server

Not yet available — `app/main.py` is created in a later phase.
