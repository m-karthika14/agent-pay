#!/usr/bin/env python
"""
Purpose: Run the frozen persona panel through Arm A -- Cap-only (plan.md
Section 19.1): hard spending cap and hard policy constraints are enforced,
but a hard-check-passed merchant proposal is applied without also being
judged against the buyer's signed intent (intent_gate_enabled=False).

Run from the repo root or from backend/:
    uv run python eval/run_cap_only.py
    (or, from backend/:  uv run python ../eval/run_cap_only.py)

Writes eval/reports/cap_only.json.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness import results_to_dicts, run_arm  # noqa: E402

REPORT_PATH = Path(__file__).resolve().parent / "reports" / "cap_only.json"


async def main() -> None:
    results = await run_arm("cap_only", intent_gate_enabled=False)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(results_to_dicts(results), indent=2), encoding="utf-8")
    for r in results:
        print(f"{r.persona_id:20s} arm={r.arm:12s} blocked={r.hard_check_blocked!s:5s} "
              f"proposal={r.proposal_status} completed={r.completed}")
    print(f"\nWrote {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
