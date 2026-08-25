"""
Purpose: Entry point for running the Merchant Revenue Agent
(plan.md Section 13.6).

run_merchant_agent() builds a fresh graph, constructs the initial state,
executes it, and returns the final proposal-or-no-proposal result. It never
executes a payment or mutates the checkout itself -- it is purely advisory
(plan.md Rule 6); wiring its result into the actual checkout flow (running
the Intent Gate over an allowed proposal, then re-freezing the cart) is
Phase 7/8's job, not this module's.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.merchant.graph import build_merchant_agent_graph
from app.agents.merchant.state import MerchantAgentState
from app.schemas.proposal import ProposalStatus


async def run_merchant_agent(session: AsyncSession, cart_id: uuid.UUID, mandate_id: str) -> MerchantAgentState:
    """
    Run the Merchant Revenue Agent against a (frozen) cart.

    Args:
        session: Active AsyncSession.
        cart_id: The cart to analyze and potentially propose an addition to.
        mandate_id: Business-facing mandate_id authorizing the cart, needed
            so submit_proposal() can evaluate proposals against it.

    Returns:
        The final MerchantAgentState. `final_status` is one of
        PROPOSAL_ALLOWED, ORIGINAL_CART_RETAINED, or NO_PROPOSAL;
        `final_proposal` holds the allowed proposal, if any.
    """
    graph = build_merchant_agent_graph(session)

    initial_state: MerchantAgentState = {
        "cart_id": str(cart_id),
        "merchant_id": "",
        "mandate_id": mandate_id,
        "original_cart": {},
        "candidate_products": [],
        "inventory_results": {},
        "ranked_candidates": [],
        "proposal": None,
        "proposal_history": [],
        "last_reason_code": None,
        "attempt_count": 0,
        "final_status": ProposalStatus.NO_PROPOSAL,
        "final_proposal": None,
    }

    result = await graph.ainvoke(initial_state)
    return result
