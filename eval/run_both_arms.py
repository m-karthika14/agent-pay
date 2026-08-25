#!/usr/bin/env python
"""
Purpose: Run the frozen persona panel through both arms (plan.md Section
19.1) in one pass and write a combined report -- the actual input Phase 10's
metrics (ceiling drift, completion/abandonment/escalation rates) are
computed from.

Run from the repo root or from backend/:
    uv run python eval/run_both_arms.py
    (or, from backend/:  uv run python ../eval/run_both_arms.py)

Writes eval/reports/both_arms.json, plus the individual per-arm reports
(same as running run_cap_only.py and run_intent_aware.py separately).
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import results_to_dicts, run_arm  # noqa: E402

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


async def main() -> None:
    cap_only_results = await run_arm("cap_only", intent_gate_enabled=False)
    intent_aware_results = await run_arm("intent_aware", intent_gate_enabled=True)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "cap_only.json").write_text(
        json.dumps(results_to_dicts(cap_only_results), indent=2), encoding="utf-8"
    )
    (REPORTS_DIR / "intent_aware.json").write_text(
        json.dumps(results_to_dicts(intent_aware_results), indent=2), encoding="utf-8"
    )
    combined = {
        "cap_only": results_to_dicts(cap_only_results),
        "intent_aware": results_to_dicts(intent_aware_results),
    }
    (REPORTS_DIR / "both_arms.json").write_text(json.dumps(combined, indent=2), encoding="utf-8")

    print(f"{'persona':20s} {'arm':12s} {'blocked':8s} {'proposal':20s} {'completed':10s}")
    for r in [*cap_only_results, *intent_aware_results]:
        print(f"{r.persona_id:20s} {r.arm:12s} {r.hard_check_blocked!s:8s} "
              f"{str(r.proposal_status):20s} {str(r.completed):10s}")
    print(f"\nWrote reports to {REPORTS_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
