"""
Purpose: Unit tests for the Intent Gate (plan.md Section 14).

The LLM is mocked at app.intent.gate.classify_with_schema (where gate.py
imported it), mirroring tests/unit/test_merchant_agent.py's pattern -- no
live GROQ_API_KEY is required to run this suite. Each test exercises one
branch of evaluate_intent()'s fail-closed decision logic (plan.md Rule 2).
"""
from unittest.mock import AsyncMock, patch

from app.ai.errors import LLMUnavailableError
from app.core.config import get_settings
from app.intent.calibration import CALIBRATION_SET
from app.intent.gate import evaluate_intent
from app.intent.models import IntentDecisionType, IntentGateInput, _IntentClassification
from app.policy import reason_codes

PATCH_TARGET = "app.intent.gate.classify_with_schema"

_SAMPLE_INPUT = IntentGateInput(
    original_buyer_request="Buy wireless earbuds under Rs 3,000. No unnecessary accessories.",
    signed_intent_product_type="wireless earbuds",
    signed_intent_notes="no unnecessary accessories",
    original_cart_summary="1x Wireless Earbuds - Rs 2,499",
    proposed_modification="Add 1x Protective Case - Rs 299",
    merchant_proposal_reason="Frequently bought together.",
)


def _classification(decision: IntentDecisionType, confidence: float, reason: str = "test reason") -> _IntentClassification:
    return _IntentClassification(decision=decision, confidence=confidence, reason=reason)


async def test_llm_unavailable_fails_closed_to_escalate() -> None:
    """If the LLM can't be reached, the gate must escalate, never crash or silently allow."""
    with patch(PATCH_TARGET, new=AsyncMock(side_effect=LLMUnavailableError("no key"))):
        result = await evaluate_intent(_SAMPLE_INPUT)

    assert result.decision == IntentDecisionType.ESCALATE
    assert result.reason_code == reason_codes.PROPOSAL_GATEWAY_ERROR


async def test_high_confidence_allow_is_passed_through() -> None:
    """A high-confidence ALLOW from the LLM is returned as ALLOW with no reason_code."""
    threshold = get_settings().intent_confidence_threshold
    classification = _classification(IntentDecisionType.ALLOW, min(threshold + 0.1, 1.0))
    with patch(PATCH_TARGET, new=AsyncMock(return_value=classification)):
        result = await evaluate_intent(_SAMPLE_INPUT)

    assert result.decision == IntentDecisionType.ALLOW
    assert result.reason_code is None


async def test_high_confidence_block_gets_intent_violation_code() -> None:
    """A high-confidence BLOCK from the LLM is returned as BLOCK with PROPOSAL_INTENT_VIOLATION."""
    threshold = get_settings().intent_confidence_threshold
    classification = _classification(IntentDecisionType.BLOCK, min(threshold + 0.1, 1.0))
    with patch(PATCH_TARGET, new=AsyncMock(return_value=classification)):
        result = await evaluate_intent(_SAMPLE_INPUT)

    assert result.decision == IntentDecisionType.BLOCK
    assert result.reason_code == reason_codes.PROPOSAL_INTENT_VIOLATION


async def test_high_confidence_llm_escalate_gets_ambiguous_code() -> None:
    """A high-confidence ESCALATE from the LLM itself maps to PROPOSAL_AMBIGUOUS_INTENT."""
    threshold = get_settings().intent_confidence_threshold
    classification = _classification(IntentDecisionType.ESCALATE, min(threshold + 0.1, 1.0))
    with patch(PATCH_TARGET, new=AsyncMock(return_value=classification)):
        result = await evaluate_intent(_SAMPLE_INPUT)

    assert result.decision == IntentDecisionType.ESCALATE
    assert result.reason_code == reason_codes.PROPOSAL_AMBIGUOUS_INTENT


async def test_low_confidence_allow_is_overridden_to_escalate() -> None:
    """Rule 2: low confidence forces ESCALATE even if the LLM's raw decision was ALLOW."""
    threshold = get_settings().intent_confidence_threshold
    classification = _classification(IntentDecisionType.ALLOW, max(threshold - 0.2, 0.0))
    with patch(PATCH_TARGET, new=AsyncMock(return_value=classification)):
        result = await evaluate_intent(_SAMPLE_INPUT)

    assert result.decision == IntentDecisionType.ESCALATE
    assert result.reason_code == reason_codes.PROPOSAL_LOW_CONFIDENCE


async def test_low_confidence_block_is_still_overridden_to_escalate() -> None:
    """Low confidence forces ESCALATE even if the LLM's raw decision was BLOCK (never trust an unsure verdict either way)."""
    threshold = get_settings().intent_confidence_threshold
    classification = _classification(IntentDecisionType.BLOCK, max(threshold - 0.2, 0.0))
    with patch(PATCH_TARGET, new=AsyncMock(return_value=classification)):
        result = await evaluate_intent(_SAMPLE_INPUT)

    assert result.decision == IntentDecisionType.ESCALATE
    assert result.reason_code == reason_codes.PROPOSAL_LOW_CONFIDENCE


def test_calibration_set_covers_all_three_categories() -> None:
    """The hand-labeled calibration set (plan.md Section 14.4) must cover all three required categories."""
    categories = {case.category for case in CALIBRATION_SET}
    assert categories == {"clearly_aligned", "clearly_violating", "ambiguous"}
    assert len(CALIBRATION_SET) >= 6
    assert len({case.case_id for case in CALIBRATION_SET}) == len(CALIBRATION_SET)
