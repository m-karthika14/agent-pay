#!/usr/bin/env python
"""
Purpose: Run the complete Phase 10 evaluation and compute every metric
plan.md Section 20/21 asks for, into one consolidated report:

    - Mandate Ceiling Drift (primary metric), Cap-only vs Intent-aware
    - Legitimate completion rate / abandonment rate (reported separately
      from ceiling drift, never folded into it as ₹0 -- Section 20)
    - Correct escalation rate (from the adversarial suite's escalation cases)
    - Violations caught / attempted (from the full adversarial suite)
    - The sensitivity sweep (-30%/baseline/+30% on the spending cap)

This is the single entry point for "run everything and get the final
numbers" -- it calls eval/harness.py, eval/adversarial.py, and
eval/sensitivity.py's functions directly (not their CLI scripts as
subprocesses) and writes eval/reports/metrics_summary.json, the one file
the pitch deck's real numbers should be read from (plan.md Section 31:
never invent evaluation numbers -- every number in this report traces back
to an actual run recorded here).

Run from the repo root or backend/:
    uv run python eval/metrics.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from abandonment import compare_arms as compare_abandonment  # noqa: E402
from adversarial import results_to_dicts as adversarial_results_to_dicts  # noqa: E402
from adversarial import run_adversarial_suite  # noqa: E402
from ceiling_drift import compare_arms as compare_ceiling_drift  # noqa: E402
from escalation import compute_escalation_rate  # noqa: E402
from harness import results_to_dicts as persona_results_to_dicts  # noqa: E402
from harness import run_arm  # noqa: E402
from sensitivity import run_sweep  # noqa: E402

REPORTS_DIR = Path(__file__).resolve().parent / "reports"


async def run_full_evaluation() -> dict:
    """Run both arms, the adversarial suite, and the sensitivity sweep, then compute every metric."""
    cap_only = persona_results_to_dicts(await run_arm("cap_only", intent_gate_enabled=False))
    intent_aware = persona_results_to_dicts(await run_arm("intent_aware", intent_gate_enabled=True))
    adversarial_results = adversarial_results_to_dicts(await run_adversarial_suite())
    sensitivity_results = await run_sweep()

    ceiling_drift = compare_ceiling_drift(cap_only, intent_aware)
    abandonment = compare_abandonment(cap_only, intent_aware)
    escalation = compute_escalation_rate(adversarial_results)

    violations_caught = sum(1 for r in adversarial_results if r["passed"])
    violations_attempted = len(adversarial_results)

    return {
        "ceiling_drift": ceiling_drift,
        "abandonment": abandonment,
        "escalation": escalation,
        "violations_caught": violations_caught,
        "violations_attempted": violations_attempted,
        "violations_caught_rate": violations_caught / violations_attempted if violations_attempted else None,
        "raw": {
            "cap_only_results": cap_only,
            "intent_aware_results": intent_aware,
            "adversarial_results": adversarial_results,
            "sensitivity_results": sensitivity_results,
        },
    }


async def main() -> None:
    summary = await run_full_evaluation()
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / "metrics_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    cd = summary["ceiling_drift"]
    ab = summary["abandonment"]
    esc = summary["escalation"]

    def _fmt(x):
        return f"{x:.3f}" if isinstance(x, float) else str(x)

    print("=== Mandate Ceiling Drift (primary metric) ===")
    print(f"  Cap-only:     mean_drift={_fmt(cd['cap_only']['mean_drift'])}  "
          f"completed={cd['cap_only']['completed_count']}/{cd['cap_only']['eligible_count']}")
    print(f"  Intent-aware: mean_drift={_fmt(cd['intent_aware']['mean_drift'])}  "
          f"completed={cd['intent_aware']['completed_count']}/{cd['intent_aware']['eligible_count']}")
    print("\n=== Abandonment (reported separately, never as Rs 0 spend) ===")
    print(f"  Cap-only:     rate={_fmt(ab['cap_only']['abandonment_rate'])}")
    print(f"  Intent-aware: rate={_fmt(ab['intent_aware']['abandonment_rate'])}")
    print("\n=== Correct Escalation Rate ===")
    print(f"  rate={_fmt(esc['correct_escalation_rate'])}  "
          f"({esc['correct_count']}/{esc['expected_escalation_count']})")
    print("\n=== Adversarial Suite ===")
    print(f"  violations_caught={summary['violations_caught']}/{summary['violations_attempted']} "
          f"({_fmt(summary['violations_caught_rate'])})")
    print(f"\nWrote {REPORTS_DIR / 'metrics_summary.json'}")


if __name__ == "__main__":
    asyncio.run(main())
