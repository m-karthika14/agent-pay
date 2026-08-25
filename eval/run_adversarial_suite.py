#!/usr/bin/env python
"""
Purpose: Run the full ~30-case adversarial suite (plan.md Section 22) and
write a structured report -- supporting evidence for the pitch deck, not
the primary causal claim (plan.md Section 21: that's Cap-only vs
Intent-aware ceiling drift, via eval/run_both_arms.py).

Run from the repo root or backend/:
    uv run python eval/run_adversarial_suite.py

Writes eval/reports/adversarial_suite.json. Some cases invoke the real
Merchant Revenue Agent and Intent Gate (mocked at the LLM call site, so
no live GROQ_API_KEY is required for THOSE specific cases), but most
cases that pass hard checks will still transitively invoke the real
Merchant Revenue Agent against the live LLM (same as eval/harness.py) -- see
eval/README.md.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adversarial import results_to_dicts, run_adversarial_suite  # noqa: E402

REPORT_PATH = Path(__file__).resolve().parent / "reports" / "adversarial_suite.json"


async def main() -> None:
    results = await run_adversarial_suite()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(results_to_dicts(results), indent=2), encoding="utf-8")

    passed_count = sum(1 for r in results if r.passed)
    print(f"{'status':6s} {'scenario_id':45s} {'category':18s} {'expected':30s} {'actual':30s}")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(
            f"{status:6s} {r.scenario_id:45s} {r.category:18s} "
            f"{str(r.expected_reason_code or r.expected_outcome):30s} "
            f"{str(r.actual_reason_code or r.final_transaction_state):30s}"
        )
    print(f"\n{passed_count}/{len(results)} scenarios caught as expected.")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
