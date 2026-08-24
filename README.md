# AgentPay

> A merchant-side authorization gateway that makes a Razorpay merchant transactable by
> external AI buyers, while protecting the user's signed spending and intent from
> revenue-maximizing merchant agents.

Built for **Razorpay Track 1 — AI Growth & Agentic Commerce**.

`plan.md` is the single frozen source of truth for this project's architecture, security
rules, phases, and build order. Read it before making any structural change.

## The core idea

```text
USER            authorizes a purchase (signed mandate)
CLAUDE          external AI buyer, transacts via MCP
MERCHANT AGENT  our one AI agent, pushes upsells/bundles (advisory only)
AGENTPAY        deterministic gateway — enforces the user's actual authorization
RAZORPAY        executes the payment (Test Mode)
```

LLMs (the merchant agent and the intent gate) can only **subtract** permission —
propose, revise, block, or escalate. They can never **grant** authority. Every hard
financial constraint is checked by deterministic code before any LLM is invoked, and
again before payment is executed.

## Repository layout

```text
frontend/   React + Vite + TypeScript + Tailwind storefront and merchant console
backend/    FastAPI + PostgreSQL + SQLAlchemy backend, security, policy engine,
            merchant agent (LangGraph), intent gate, MCP server, Razorpay integration
eval/       Two-arm evaluation harness (cap-only vs. intent-aware) and metrics
scripts/    Operational scripts (seeding, mandate generation, audit verification)
docs/       Architecture, API, mandate, security, evaluation, and deployment docs
```

See `plan.md` Section 4 for the complete file-by-file structure.

## Local development

Prerequisites: Git, Node.js, Python 3.12+, `uv`, PostgreSQL.

```bash
# Frontend
cd frontend
npm install
npm run dev

# Backend
cd backend
uv sync
uv run uvicorn app.main:app --reload
```

Copy `.env.example` to `.env` (and `frontend/.env.example` to `frontend/.env`) and fill
in real values. Never commit a real `.env` file — see the "Secret rules" in `plan.md`
Section 6.

## Build status

This project is built phase by phase, in the exact order defined in `plan.md`
Section 71 (Final Phase Map). Do not skip ahead — see `plan.md` for the current phase.
