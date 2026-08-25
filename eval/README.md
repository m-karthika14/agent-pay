# AgentPay Evaluation Harness

Phase 9 (plan.md Section 19 / final.md Phase 9): a harness that drives the
real backend (`app.services.checkout_service.request_checkout()`) through a
frozen buyer persona panel, comparing two arms:

- **Cap-only** -- hard spending cap and hard policy constraints (amount,
  category, inventory, mandate validity) are enforced, but a merchant
  proposal that passes those hard checks is applied without also being
  judged against the buyer's signed *intent* (no Intent Gate consultation).
- **Intent-aware** -- the real, full system: hard constraints, plus the
  Intent Gate judging every hard-check-passed proposal against the buyer's
  signed intent (AgentPay's actual production behavior).

Both arms use the identical Merchant Revenue Agent, product catalog,
starting carts, and persona panel (plan.md Section 19.1) -- only whether the
Intent Gate is consulted differs.

## Prerequisites

1. A running PostgreSQL database matching `backend/.env`'s `DATABASE_URL`.
2. The UrbanNest catalog seeded:
   ```bash
   uv run python scripts/seed_database.py
   ```
   (run from the repo root, or from `backend/` as
   `uv run python ../scripts/seed_database.py`)
3. For the Intent-aware arm: a configured, quota-available `GEMINI_API_KEY`
   in `backend/.env` -- both the Merchant Revenue Agent and the Intent Gate
   make real Gemini calls in that arm. The Cap-only arm still invokes the
   Merchant Revenue Agent (which also calls Gemini to generate candidates),
   so it needs a working key too; only the Intent Gate call is skipped.

## Running

From the repo root (or `backend/`, adjusting the relative path):

```bash
uv run python eval/run_cap_only.py       # Arm A only
uv run python eval/run_intent_aware.py   # Arm B only
uv run python eval/run_both_arms.py      # both, plus a combined report
```

Each run writes JSON to `eval/reports/`.

## The persona panel (`personas.json`)

Frozen before either arm runs (plan.md Section 19.2) -- do not edit after
seeing results. Four personas:

- `price_sensitive` -- explicitly asked for no add-ons; abandons if the
  approved cart was modified from what they asked for.
- `convenience_first` -- explicitly welcomes a reasonable add-on; always
  completes.
- `literal_minded` -- a differently-phrased "nothing else" instruction
  (tests intent-gate semantic understanding under different prompt wording,
  not just a different reasoning style); abandons if modified.
- `prompt_injected` -- **adversarial**: its starting cart already exceeds
  its own mandate's cap (simulating a buyer agent manipulated into
  over-committing before `request_checkout()` is ever called). Expected to
  be blocked by AgentPay's hard checks before the Merchant Revenue Agent or
  Intent Gate are ever reached (`model_invoked=False`).

Since Claude (the external buyer) isn't built by this project, each
persona's reaction to a checkout result is a frozen, deterministic
`completion_rule` in `personas.json` rather than a live LLM decision --
see `harness.py`'s module docstring for the full rationale.

## Scope

This harness measures AgentPay's *authorization* decision -- would the
transaction be approved, and at what final amount -- via
`request_checkout()` only. It deliberately does not create a real Razorpay
Test Mode order per run (already covered by Phase 4/5's tests), so eval
runs stay fast and side-effect-free outside the database.

Metrics computation on top of these reports (Mandate Ceiling Drift,
completion/abandonment/escalation rates, the ~30-case adversarial suite,
the sensitivity sweep) is Phase 10's job, not this harness's.
