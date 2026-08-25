"""
Purpose: Pydantic schemas for the Intent Gate (plan.md Section 14).

The Intent Gate is a single Gemini structured-classification call, not an
agent (plan.md Section 0.5 / Section 14.1): it has no tools, no loop, and no
state beyond one request/response. These are its strict input/output shapes.
"""
from enum import StrEnum

from pydantic import BaseModel, Field


class IntentDecisionType(StrEnum):
    """The three possible outcomes of one intent-gate classification (plan.md Section 14.2)."""

    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    ESCALATE = "ESCALATE"


class IntentGateInput(BaseModel):
    """
    Everything the Intent Gate needs to judge one merchant proposal
    (plan.md Section 14.1).

    original_buyer_request/signed_intent_* both derive from the mandate's
    signed MandateIntent -- the mandate carries no separate raw buyer
    utterance, and per plan.md Rule 3 ("intent is signed into the mandate"),
    the signed intent IS the trustworthy record of what the user asked for.
    The merchant agent cannot rewrite it.
    """

    original_buyer_request: str
    signed_intent_product_type: str
    signed_intent_notes: str | None = None
    original_cart_summary: str = Field(description="Plain-text summary of the frozen, authorized cart.")
    proposed_modification: str = Field(description="Plain-text summary of the merchant's proposed change.")
    merchant_proposal_reason: str


class IntentDecision(BaseModel):
    """
    The Intent Gate's final, deterministic-wrapper-assigned verdict.

    decision=ALLOW only ever permits what hard checks already allowed
    (plan.md Rule 1: the gate can subtract permission, never add it).
    reason_code is always set on BLOCK/ESCALATE, and is assigned by
    app.intent.gate -- never returned directly by Gemini (see
    app.policy.reason_codes' Phase 7 section for why).
    """

    decision: IntentDecisionType
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    reason_code: str | None = None


class _IntentClassification(BaseModel):
    """
    The narrow shape actually requested from Gemini (internal to this
    module). Deliberately excludes reason_code -- see IntentDecision's
    docstring for why that's assigned by the deterministic wrapper instead.
    """

    decision: IntentDecisionType
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
