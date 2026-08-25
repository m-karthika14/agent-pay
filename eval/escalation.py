"""
Purpose: Compute the correct escalation rate (plan.md Section 21) -- of the
adversarial-suite cases that are SUPPOSED to be escalated (ambiguous or
low-confidence intent, plan.md Rule 2/Rule 3), how many actually were.

Operates on eval/adversarial.py's ScenarioResult records (as plain dicts),
which already carry ground truth (expected_outcome) and whether the actual
result matched it (passed) -- this module just filters/aggregates rather
than re-deriving anything, per plan.md's "reuse, don't duplicate" rule.
"""


def compute_escalation_rate(scenario_results: list[dict]) -> dict:
    """
    Compute the correct escalation rate from adversarial suite results.

    Args:
        scenario_results: ScenarioResult dicts from
            eval.adversarial.results_to_dicts(), covering the full suite.

    Returns:
        {
          "correct_escalation_rate": float | None,  # None if no escalation cases exist
          "correct_count": int,
          "expected_escalation_count": int,
          "cases": [{"scenario_id": ..., "passed": ..., "actual_state": ...}, ...],
        }
    """
    escalation_cases = [r for r in scenario_results if r["expected_outcome"] == "ESCALATION_REQUIRED"]
    correct = [r for r in escalation_cases if r["passed"]]

    return {
        "correct_escalation_rate": (len(correct) / len(escalation_cases)) if escalation_cases else None,
        "correct_count": len(correct),
        "expected_escalation_count": len(escalation_cases),
        "cases": [
            {"scenario_id": r["scenario_id"], "passed": r["passed"], "actual_state": r["final_transaction_state"]}
            for r in escalation_cases
        ],
    }
