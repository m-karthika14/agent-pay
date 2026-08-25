#!/usr/bin/env python
"""
Purpose: Sensitivity sweep (plan.md Section 19.3 / Section 22) -- rerun the
persona panel with the mandate spending cap scaled by -30%/baseline/+30%,
to check whether the primary Ceiling Drift result is stable or an artifact
of one specific cap value. Do not change the evaluation architecture after
observing these results (plan.md Section 19.3/31).

The spending cap is the swept assumption because it is literally the
denominator of the primary metric (Mandate Ceiling Drift, plan.md Section
20) -- the most direct test of whether that metric's conclusion holds under
a different authorized spending limit. Only "normal" category personas are
swept (the adversarial persona's cap is the attack's own subject, not a
tunable assumption).

Run from the repo root or backend/:
    uv run python eval/sensitivity.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ceiling_drift import compute_ceiling_drift  # noqa: E402
from harness import load_personas, results_to_dicts, run_persona  # noqa: E402

SWEEP_FACTORS = {"-30%": 0.7, "baseline": 1.0, "+30%": 1.3}
REPORT_PATH = Path(__file__).resolve().parent / "reports" / "sensitivity.json"


async def run_sweep() -> dict:
    """
    Rerun every normal-category persona through both arms at each sweep
    factor, and compute ceiling drift for each (factor, arm) combination.

    Returns:
        {
          factor_label: {
            "cap_only": {..raw PersonaRunResult dicts + ceiling_drift..},
            "intent_aware": {...},
          },
          ...
        }
    """
    personas = [p for p in load_personas() if p["category"] == "normal"]
    output: dict = {}

    for label, factor in SWEEP_FACTORS.items():
        output[label] = {}
        for arm, intent_gate_enabled in (("cap_only", False), ("intent_aware", True)):
            results = []
            for persona in personas:
                scaled_cap = round(persona["mandate"]["max_amount_minor"] * factor)
                result = await run_persona(
                    persona, arm=arm, intent_gate_enabled=intent_gate_enabled, max_amount_override=scaled_cap
                )
                results.append(result)
            result_dicts = results_to_dicts(results)
            output[label][arm] = {
                "results": result_dicts,
                "ceiling_drift": compute_ceiling_drift(result_dicts),
            }

    return output


async def main() -> None:
    output = await run_sweep()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(output, indent=2), encoding="utf-8")

    print(f"{'factor':10s} {'arm':12s} {'mean_drift':12s} {'completed/eligible':20s}")
    for label, arms in output.items():
        for arm, data in arms.items():
            cd = data["ceiling_drift"]
            mean_drift = f"{cd['mean_drift']:.3f}" if cd["mean_drift"] is not None else "n/a"
            print(f"{label:10s} {arm:12s} {mean_drift:12s} {cd['completed_count']}/{cd['eligible_count']}")
    print(f"\nWrote {REPORT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
