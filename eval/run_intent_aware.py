#!/usr/bin/env python
"""
Purpose: Run the frozen persona panel through Arm B -- Intent-aware
(plan.md Section 19.1): hard constraints, plus the buyer's signed intent
enforced via the Intent Gate for any merchant proposal
(intent_gate_enabled=True, AgentPay's real production behavior).

Run from the repo root or from backend/:
    uv run python eval/run_intent_aware.py
    (or, from backend/:  uv run python ../eval/run_intent_aware.py)

Requires a configured, quota-available GEMINI_API_KEY -- both the Merchant
Revenue Agent and the Intent Gate make real Gemini calls in this arm.

Writes eval/reports/intent_aware.json.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import results_to_dicts, run_arm  # noqa: E402

REPORT_PATH = Path(__file__).resolve().parent / "reports" / "intent_aware.json"


async def main() -> None:
    results = await run_arm("intent_aware", intent_gate_enabled=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(results_to_dicts(results), indent=2), encoding="utf-8")
    for r in results:
        print(f"{r.persona_id:20s} arm={r.arm:12s} blocked={r.hard_check_blocked!s:5s} "
              f"proposal={r.proposal_status} completed={r.completed}")
    print(f"\nWrote {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
