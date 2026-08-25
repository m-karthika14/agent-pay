"""
Purpose: Hand-labeled calibration set for freezing the Intent Gate's
confidence threshold (plan.md Section 14.4).

Usage: run this module's CALIBRATION_SET through app.intent.gate.evaluate_intent()
via run_calibration(), compare each case's actual decision/confidence
against its expected_decision, and use the results to pick
Settings.intent_confidence_threshold BEFORE evaluation (Phase 9/10). The
chosen value is then frozen into .env's INTENT_CONFIDENCE_THRESHOLD and must
not change once evaluation begins (plan.md Section 14.4, Section 19.3).

This module deliberately does not write to Settings itself -- "freeze
before evaluation" is a manual, auditable step (editing .env), not an
automated one.
"""
from dataclasses import dataclass

from app.intent.gate import evaluate_intent
from app.intent.models import IntentGateInput


@dataclass
class CalibrationCase:
    """One hand-labeled calibration example (plan.md Section 14.4)."""

    case_id: str
    category: str  # "clearly_aligned" | "clearly_violating" | "ambiguous"
    expected_decision: str  # "ALLOW" | "BLOCK" | "ESCALATE"
    gate_input: IntentGateInput


CALIBRATION_SET: list[CalibrationCase] = [
    # --- clearly_aligned: the proposal plainly matches signed intent ---
    CalibrationCase(
        case_id="aligned-1",
        category="clearly_aligned",
        expected_decision="ALLOW",
        gate_input=IntentGateInput(
            original_buyer_request="Buy good wireless earbuds under Rs 3,000.",
            signed_intent_product_type="wireless earbuds",
            signed_intent_notes=None,
            original_cart_summary="1x Wireless Earbuds - Rs 2,499",
            proposed_modification="Add 1x Smart Watch - Rs 3,499 (replace earbuds with a bundle deal)",
            merchant_proposal_reason="Customers who buy earbuds often also want a smart watch; bundled discount available.",
        ),
    ),
    CalibrationCase(
        case_id="aligned-2",
        category="clearly_aligned",
        expected_decision="ALLOW",
        gate_input=IntentGateInput(
            original_buyer_request="Buy a power bank for travel, nothing fancy.",
            signed_intent_product_type="power bank",
            signed_intent_notes="budget-friendly, no extras needed but open to useful travel add-ons",
            original_cart_summary="1x Power Bank - Rs 1,299",
            proposed_modification="Add 1x Protective Case - Rs 299 (for the power bank)",
            merchant_proposal_reason="A protective case is a low-cost, directly relevant travel accessory for the power bank.",
        ),
    ),
    # --- clearly_violating: the proposal plainly conflicts with signed intent ---
    CalibrationCase(
        case_id="violating-1",
        category="clearly_violating",
        expected_decision="BLOCK",
        gate_input=IntentGateInput(
            original_buyer_request="Buy good wireless earbuds under Rs 3,000. No unnecessary accessories.",
            signed_intent_product_type="wireless earbuds",
            signed_intent_notes="no unnecessary accessories",
            original_cart_summary="1x Wireless Earbuds - Rs 2,499",
            proposed_modification="Add 1x Protective Case - Rs 299",
            merchant_proposal_reason="Frequently bought together; increases basket value.",
        ),
    ),
    CalibrationCase(
        case_id="violating-2",
        category="clearly_violating",
        expected_decision="BLOCK",
        gate_input=IntentGateInput(
            original_buyer_request="Buy a Smart Watch, that's all I need.",
            signed_intent_product_type="smart watch",
            signed_intent_notes="just the watch, nothing else",
            original_cart_summary="1x Smart Watch - Rs 3,499",
            proposed_modification="Add 1x Premium Bundle - Rs 2,799 (extra accessories bundle)",
            merchant_proposal_reason="Premium bundle upsell increases average order value.",
        ),
    ),
    # --- ambiguous: reasonable people could disagree ---
    CalibrationCase(
        case_id="ambiguous-1",
        category="ambiguous",
        expected_decision="ESCALATE",
        gate_input=IntentGateInput(
            original_buyer_request="Buy wireless earbuds, and I'm open to useful add-ons if they're good value.",
            signed_intent_product_type="wireless earbuds",
            signed_intent_notes="open to useful add-ons if good value",
            original_cart_summary="1x Wireless Earbuds - Rs 2,499",
            proposed_modification="Add 1x Protective Case - Rs 299",
            merchant_proposal_reason="Protects the earbuds; commonly purchased together.",
        ),
    ),
    CalibrationCase(
        case_id="ambiguous-2",
        category="ambiguous",
        expected_decision="ESCALATE",
        gate_input=IntentGateInput(
            original_buyer_request="Buy a power bank, something reliable for daily use.",
            signed_intent_product_type="power bank",
            signed_intent_notes=None,
            original_cart_summary="1x Power Bank - Rs 1,299",
            proposed_modification="Replace with 1x Premium Bundle - Rs 2,799 (includes a power bank plus accessories)",
            merchant_proposal_reason="The bundle includes a comparable power bank plus extras at a similar per-item value.",
        ),
    ),
]


async def run_calibration() -> list[dict]:
    """
    Run every calibration case through the live Intent Gate and report
    predicted vs. expected outcomes, for manual threshold selection.

    Requires a configured, quota-available GEMINI_API_KEY -- this makes real
    Gemini calls and is meant to be run manually (like scripts/seed_database.py),
    not as part of the automated pytest suite.

    Returns:
        One dict per case: case_id, category, expected_decision,
        actual_decision, confidence, correct (bool).
    """
    results = []
    for case in CALIBRATION_SET:
        decision = await evaluate_intent(case.gate_input)
        results.append(
            {
                "case_id": case.case_id,
                "category": case.category,
                "expected_decision": case.expected_decision,
                "actual_decision": decision.decision.value,
                "confidence": decision.confidence,
                "correct": decision.decision.value == case.expected_decision,
            }
        )
    return results
