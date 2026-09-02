# AgentPay

**A payments boundary for agent-to-agent commerce.** AgentPay makes a Razorpay
merchant transactable by any external AI buyer, end to end — while guaranteeing
every purchase stays inside the spending mandate the human actually signed.

## Why this exists

AI agents are starting to shop and pay on people's behalf. Emerging protocols —
UAP, ACP, AP2, x402 — standardise how autonomous agents discover catalogs and
move money, and the first in-app pilots are live. Merchants will soon have to be
transactable by buyer agents they neither build nor control.

That creates a conflict of interest:

- a **buyer agent** optimises for the cheapest cart that satisfies the request;
- a **merchant's revenue agent** optimises for a larger one.

Nothing in that exchange guarantees the result matches what the shopper
authorised. AgentPay is the deterministic layer that does: the human signs a
mandate — amount cap, allowed categories, expiry, intent — and every constraint
is checked by code, not by a model, before a rupee moves.

## Actors

| Actor | Role |
|---|---|
| **Buyer** | A human. Signs a spending mandate; approves, edits, or rejects each purchase. |
| **Buyer agent** | Any external AI (e.g. Claude over MCP). Searches, compares, builds a cart. Not built here. |
| **Merchant revenue agent** | The one agent in this repo. Proposes upsells and bundles on a frozen cart — advisory only. |
| **AgentPay** | The gateway. Verifies the mandate, runs deterministic policy checks, consults the Intent Gate, executes payment. |
| **Razorpay** | Payment execution (test mode). |

## How a purchase flows

1. **Mandate** — the buyer sets category, amount cap, and expiry. Signed with
   Ed25519. This is the only thing that grants authority.
2. **Shop** — the buyer agent searches merchants over MCP, builds a cart, and
   requests authorization. The buyer approves, edits, or rejects it in the app.
3. **Verify** — AgentPay checks the signature, replay protection, and the cart
   binding.
4. **Hard checks** — amount cap, allowed category, cart-hash integrity.
   Deterministic, and run before any LLM.
5. **Intent Gate** — if the merchant agent proposes an add-on, an LLM judges it
   against the signed intent and returns *allow*, *block*, or *escalate*. It can
   only subtract permission.
6. **Freeze** — the authorised cart is locked and re-validated.
7. **Pay** — a Razorpay order is created and charged: automatically against the
   buyer's authorised method where the payment rail supports it, otherwise via a
   one-time authenticated checkout. A failed auto-charge falls back gracefully —
   it never breaks the order.
8. **Record** — every step is a signed entry in a hash-chained audit log.

**The invariant:** an LLM may propose, revise, block, or escalate — never grant
spending authority. Fail closed: unavailable, ambiguous, or low-confidence intent
results in a block plus escalation.

## Repository layout

```
frontend/   React + Vite + TypeScript + Tailwind — storefront, buyer dashboard,
            live AI-activity view, read-only merchant console
backend/    FastAPI + PostgreSQL + SQLAlchemy — gateway, deterministic policy
            engine, mandate signing, merchant revenue agent (LangGraph),
            Intent Gate, MCP server, Razorpay integration, hash-chained audit log
eval/       Two-arm evaluation harness (cap-only vs. intent-aware) and metrics
scripts/    Database seeding and audit-chain verification
plan.md     Frozen architecture, security rules, and build order — the source of truth
```

## Running it locally

### Prerequisites

- Python 3.12+ and [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+
- PostgreSQL 16+ (via Docker, or a local install)
- Optional, for the full flow: Razorpay **test-mode** API keys, and a Groq API
  key for the merchant agent and Intent Gate (LLM calls are provider-agnostic
  via `backend/app/ai/llm_client.py`)

### 1. Database

```bash
docker compose up -d          # PostgreSQL on :5432
```

### 2. Backend → http://localhost:8000

```bash
cp .env.example backend/.env  # then fill in Razorpay / Groq keys

cd backend
uv sync
uv run alembic upgrade head
uv run python ../scripts/seed_database.py     # demo merchants + catalog
uv run uvicorn app.main:app --reload
```

Generate a signing keypair for `backend/.env`:

```bash
uv run python -c "from app.security.signing import generate_ed25519_keypair, encode_key; a, b = generate_ed25519_keypair(); print('ED25519_PRIVATE_KEY_B64=' + encode_key(a)); print('ED25519_PUBLIC_KEY_B64=' + encode_key(b))"
```

- API docs — http://localhost:8000/docs
- MCP endpoint — http://localhost:8000/mcp

### 3. Frontend → http://localhost:5173

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

### Or use the Makefile (needs GNU make — Git Bash / WSL on Windows)

```bash
make db-up
make install          # frontend + backend dependencies
make migrate
make seed
make dev-backend      # terminal 1
make dev-frontend     # terminal 2
```

## Connecting an AI buyer

The backend serves an MCP server at `/mcp` (Streamable HTTP). Point any
MCP-capable agent at it:

```bash
claude mcp add agentpay --transport http http://localhost:8000/mcp
```

Tools: `search_products`, `get_product`, `create_cart`, `add_to_cart`,
`request_authorization`, `check_authorization_status`, `request_checkout`,
`complete_purchase`.

A purchase only proceeds after the human approves the authorization request in
the app; the agent polls `check_authorization_status` until then. Watch it run
live under **AI Activity**.

## Tests

```bash
make test                     # frontend + backend
cd backend && uv run pytest   # backend only (LLM calls mocked)
```

## Evaluation

Two arms over a frozen buyer-persona panel: **cap-only** (hard checks only) vs.
**intent-aware** (hard checks plus the Intent Gate — the real system). It reports
spending-ceiling drift on completed transactions, escalation behaviour, and an
adversarial suite. See `eval/README.md`.

```bash
make seed
cd backend && uv run python ../eval/run_both_arms.py
```

## Deployment

- **Backend** — `render.yaml` provisions the FastAPI service and PostgreSQL on
  Render. Set the `sync: false` secrets in the dashboard.
- **Frontend** — static Vite build (`npm run build`) on Vercel; set
  `VITE_API_BASE_URL` and `VITE_RAZORPAY_KEY_ID`.

## Notes

- Razorpay runs in **test mode** throughout.
- Off-session recurring charges require Razorpay's server-to-server recurring API,
  which is enabled per account after KYC / activation. Where it isn't available
  the flow falls back to an authenticated checkout — the order still completes,
  and the reason is shown in the activity feed.
- `plan.md` is the frozen specification. Read it before any structural change.
