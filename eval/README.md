# AgentPay Evaluation Harness

Phase 9 built the harness itself; Phase 10 (plan.md Section 20-22 / final.md
Phase 10) builds the metrics computed on top of it. See "Metrics (Phase 10)"
below for the primary result and the adversarial suite.

## Harness (Phase 9)

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

## Metrics (Phase 10)

### Primary metric -- Mandate Ceiling Drift

```
Ceiling Drift = Final Completed Spend / Authorized Spending Cap
```

`ceiling_drift.py` computes this per persona and as a mean, per arm, from
`harness.py`'s run results. Denominator rule (plan.md Section 20, strictly
enforced): only `completed=True` runs are included. An abandoned run is
**never** counted as ₹0 -- `abandonment.py` reports abandonment as its own
separate rate instead.

### Supporting metrics

- `abandonment.py` -- abandonment rate + which personas abandoned and why,
  per arm.
- `escalation.py` -- correct escalation rate, computed from the adversarial
  suite's `expected_outcome == "ESCALATION_REQUIRED"` cases.
- `violations_caught` / `violations_attempted` -- from the adversarial suite
  as a whole.

### Adversarial suite (`scenarios.json` + `adversarial.py`)

~30 frozen attack/edge-case scenarios across the 15 categories in plan.md
Section 22 (overspend, cap splitting, expired mandate, replay, wrong
merchant, wrong category, price change, cart modification, duplicate
submit, prompt injection, currency mismatch, unit confusion, out of stock,
merchant upsell, duplicate payment). Supporting evidence, not the primary
causal claim (plan.md Section 21) -- the attacks were authored by us.

Run: `uv run python eval/run_adversarial_suite.py` -> `eval/reports/adversarial_suite.json`.

**Known finding (not fixed as part of Phase 10, flagged for a decision):**
two cases (`cap_splitting_reuse_after_success`,
`cap_splitting_reuse_before_completion`) currently fail. AgentPay's
single-use enforcement only marks a mandate CONSUMED at payment capture
(`app.mandates.service.consume_mandate`, called from webhook reconciliation)
-- an ACTIVE-but-unpaid mandate can currently be reused to freeze a
*second*, different cart via `request_checkout()`. This is a real gap, not
a test bug; see the main conversation/phase report for the fix-or-document
decision.

### Sensitivity sweep (`sensitivity.py`)

Reruns the normal-category personas at the spending cap scaled by
-30%/baseline/+30% (plan.md Section 19.3) -- the cap is swept because it is
literally Ceiling Drift's denominator. Do not change the evaluation
architecture after observing these results.

Run: `uv run python eval/sensitivity.py` -> `eval/reports/sensitivity.json`.

### Everything at once

```bash
uv run python eval/metrics.py
```

Runs both arms, the full adversarial suite, and the sensitivity sweep, and
writes the one consolidated report the pitch deck's numbers should be read
from: `eval/reports/metrics_summary.json`. Every number in it traces back
to an actual run recorded in that file -- per plan.md Section 31, no
evaluation number is ever invented.
