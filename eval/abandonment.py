"""
Purpose: Compute abandonment rate and reasons (plan.md Section 20/21) --
reported SEPARATELY from Ceiling Drift, never folded into it as a ₹0 spend
(plan.md Section 20's explicit denominator rule).

Operates on eval/harness.py's PersonaRunResult records for one arm.
"""


def compute_abandonment(results: list[dict]) -> dict:
    """
    Compute the abandonment rate for one arm's results, plus a breakdown of
    which personas abandoned and why (their proposal_status at the point of
    abandonment).

    Args:
        results: PersonaRunResult dicts for ONE arm.

    Returns:
        {
          "abandonment_rate": float | None,   # None if no eligible personas
          "abandoned_count": int,
          "eligible_count": int,               # normal-category, non-hard-blocked runs
          "abandoned_personas": [{"persona_id": ..., "proposal_status": ...}, ...],
        }
    """
    eligible = [r for r in results if r["category"] == "normal" and not r["hard_check_blocked"]]
    abandoned = [r for r in eligible if r["completed"] is False]

    return {
        "abandonment_rate": (len(abandoned) / len(eligible)) if eligible else None,
        "abandoned_count": len(abandoned),
        "eligible_count": len(eligible),
        "abandoned_personas": [
            {"persona_id": r["persona_id"], "proposal_status": r["proposal_status"]} for r in abandoned
        ],
    }


def compare_arms(cap_only_results: list[dict], intent_aware_results: list[dict]) -> dict:
    """Compute abandonment for both arms side by side."""
    return {
        "cap_only": compute_abandonment(cap_only_results),
        "intent_aware": compute_abandonment(intent_aware_results),
    }
