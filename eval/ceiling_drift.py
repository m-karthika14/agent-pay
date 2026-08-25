"""
Purpose: Compute the primary evaluation metric -- Mandate Ceiling Drift
(plan.md Section 20 / final.md Phase 10).

    Ceiling Drift = Final Completed Spend / Authorized Spending Cap

Denominator rule (plan.md Section 20, strictly enforced here): only
completed transactions are included. An abandoned transaction is NEVER
counted as ₹0 -- it is simply excluded from this metric and reported
separately by eval/abandonment.py. This prevents the metric from being
artificially improved by an arm that blocks/discourages more purchases.

Operates on eval/harness.py's PersonaRunResult records (as plain dicts, the
shape eval/run_*.py writes to eval/reports/*.json) -- never invents numbers
that didn't come from an actual harness run (plan.md Section 31).
"""
from statistics import mean


def compute_ceiling_drift(results: list[dict]) -> dict:
    """
    Compute per-persona and aggregate ceiling drift for one arm's results.

    Args:
        results: PersonaRunResult dicts (as produced by
            eval.harness.results_to_dicts) for ONE arm.

    Returns:
        {
          "per_persona": {persona_id: drift_ratio, ...},   # completed only
          "mean_drift": float | None,                      # None if nothing completed
          "completed_count": int,
          "eligible_count": int,   # normal-category runs with a mandate cap
        }
    """
    per_persona: dict[str, float] = {}
    eligible = [r for r in results if r["category"] == "normal" and r["mandate_max_amount_minor"]]

    for r in eligible:
        if r["completed"] and r["completed_spend_minor"] is not None:
            per_persona[r["persona_id"]] = r["completed_spend_minor"] / r["mandate_max_amount_minor"]

    drift_values = list(per_persona.values())
    return {
        "per_persona": per_persona,
        "mean_drift": mean(drift_values) if drift_values else None,
        "completed_count": len(drift_values),
        "eligible_count": len(eligible),
    }


def compare_arms(cap_only_results: list[dict], intent_aware_results: list[dict]) -> dict:
    """
    Compute ceiling drift for both arms side by side -- the core experiment
    (plan.md Section 19/20): does Intent-aware reduce how much of the
    authorized cap merchant pressure actually captures, compared to
    Cap-only, for the same personas/products/starting carts?

    Returns:
        {"cap_only": <compute_ceiling_drift output>, "intent_aware": <...>}
    """
    return {
        "cap_only": compute_ceiling_drift(cap_only_results),
        "intent_aware": compute_ceiling_drift(intent_aware_results),
    }
