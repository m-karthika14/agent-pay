"""
Purpose: The Intent Gate (plan.md Section 14) -- a single LLM structured
classification call that judges whether a merchant proposal is consistent
with the buyer's signed intent. This is NOT an agent: no tools, no loop, no
state beyond one request/response (plan.md Section 0.5).

Authority model (plan.md Section 11.4 / Rule 1): callers must only invoke
evaluate_intent() for a proposal that has ALREADY passed AgentPay's
deterministic hard checks (app.services.merchant_service.evaluate_proposal
returning allowed=True). The gate can then only ALLOW that already-permitted
proposal, or BLOCK/ESCALATE it -- it can never grant authority a hard check
didn't already give.

Fail-closed (plan.md Rule 2): if the LLM is unavailable, or its confidence
falls below Settings.intent_confidence_threshold, or its own classification
is ESCALATE, this returns ESCALATE -- never ALLOW. evaluate_intent() itself
never raises; every LLM failure is caught and converted to an ESCALATE
decision so a gateway outage degrades to "ask a human," not to a crash or a
silent allow.
"""
from app.ai.errors import LLMError
from app.ai.llm_client import classify_with_schema
from app.core.config import get_settings
from app.intent.models import IntentDecision, IntentDecisionType, IntentGateInput, _IntentClassification
from app.intent.prompt import INTENT_GATE_SYSTEM_PROMPT
from app.policy import reason_codes


async def evaluate_intent(gate_input: IntentGateInput) -> IntentDecision:
    """
    Classify whether a merchant proposal is consistent with the buyer's
    signed intent.

    Args:
        gate_input: The buyer's original request, signed intent, the frozen
            original cart, the proposed modification, and the merchant's
            stated reason (plan.md Section 14.1).

    Returns:
        IntentDecision. decision is ALLOW only if the LLM classified the
        proposal as consistent AND its confidence met the configured
        threshold; otherwise BLOCK or ESCALATE, always carrying a
        reason_code from app.policy.reason_codes.
    """
    prompt = _build_prompt(gate_input)
    try:
        classification = await classify_with_schema(
            prompt, _IntentClassification, system_instruction=INTENT_GATE_SYSTEM_PROMPT
        )
    except LLMError as exc:
        return IntentDecision(
            decision=IntentDecisionType.ESCALATE,
            confidence=0.0,
            reason=f"Intent gate unavailable: {exc}",
            reason_code=reason_codes.PROPOSAL_GATEWAY_ERROR,
        )

    # Low confidence overrides whatever the LLM decided -- Rule 2 treats
    # "not confident" the same as "unavailable": fail closed, escalate.
    threshold = get_settings().intent_confidence_threshold
    if classification.confidence < threshold:
        return IntentDecision(
            decision=IntentDecisionType.ESCALATE,
            confidence=classification.confidence,
            reason=classification.reason,
            reason_code=reason_codes.PROPOSAL_LOW_CONFIDENCE,
        )

    if classification.decision == IntentDecisionType.ALLOW:
        return IntentDecision(
            decision=IntentDecisionType.ALLOW,
            confidence=classification.confidence,
            reason=classification.reason,
            reason_code=None,
        )
    if classification.decision == IntentDecisionType.ESCALATE:
        return IntentDecision(
            decision=IntentDecisionType.ESCALATE,
            confidence=classification.confidence,
            reason=classification.reason,
            reason_code=reason_codes.PROPOSAL_AMBIGUOUS_INTENT,
        )
    return IntentDecision(
        decision=IntentDecisionType.BLOCK,
        confidence=classification.confidence,
        reason=classification.reason,
        reason_code=reason_codes.PROPOSAL_INTENT_VIOLATION,
    )


def _build_prompt(gate_input: IntentGateInput) -> str:
    """Render one IntentGateInput into the plain-text prompt sent to the LLM."""
    return (
        f"Original buyer request: {gate_input.original_buyer_request}\n"
        f"Signed intent -- product type: {gate_input.signed_intent_product_type}\n"
        f"Signed intent -- notes: {gate_input.signed_intent_notes or '(none)'}\n"
        f"Original authorized cart: {gate_input.original_cart_summary}\n"
        f"Merchant's proposed modification: {gate_input.proposed_modification}\n"
        f"Merchant's stated reason for the proposal: {gate_input.merchant_proposal_reason}\n\n"
        "Does the proposed modification remain consistent with the buyer's "
        "signed intent? Classify it."
    )
