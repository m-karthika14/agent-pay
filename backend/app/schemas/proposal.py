"""
Purpose: Pydantic schemas for merchant proposals (plan.md Section 13, 27).

A proposal is the Merchant Revenue Agent's suggested cart modification
(e.g. "add 1x Protective Case"). It is never applied directly to a cart --
app.services.merchant_service evaluates it against AgentPay's deterministic
checks and returns a ProposalEvaluation the agent must respect.
"""
from enum import StrEnum

from pydantic import BaseModel, Field


class ProposalStatus(StrEnum):
    """
    The full proposal state machine (plan.md Section 27). Not every value is
    reachable yet in Phase 6 alone -- PROPOSAL_ESCALATED requires the Intent
    Gate (Phase 7), which does not exist until then.
    """

    NO_PROPOSAL = "NO_PROPOSAL"
    PROPOSAL_PENDING = "PROPOSAL_PENDING"
    PROPOSAL_ALLOWED = "PROPOSAL_ALLOWED"
    PROPOSAL_REJECTED = "PROPOSAL_REJECTED"
    PROPOSAL_ESCALATED = "PROPOSAL_ESCALATED"
    PROPOSAL_LIMIT_REACHED = "PROPOSAL_LIMIT_REACHED"
    ORIGINAL_CART_RETAINED = "ORIGINAL_CART_RETAINED"


class MerchantProposal(BaseModel):
    """One cart-modification proposal from the Merchant Revenue Agent."""

    product_id: str
    quantity: int = Field(gt=0)
    reason: str = Field(description="Why the agent believes this increases basket value.")


class ProposalEvaluation(BaseModel):
    """
    The deterministic outcome of evaluating one MerchantProposal against
    AgentPay's hard checks (plan.md Section 13.3: submit_proposal() calls
    AgentPay's proposal pathway, not the cart, directly).

    Phase 6 scope note: this only re-runs the deterministic policy checks
    that already exist (amount cap, category, inventory) against a
    hypothetical modified cart. Semantic intent evaluation (does this
    accessory violate the user's actual request even though its category is
    technically allowed) is the Intent Gate's job, added in Phase 7.
    """

    allowed: bool
    reason_code: str | None = None
    reason: str | None = None
