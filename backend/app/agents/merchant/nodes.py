"""
Purpose: LangGraph node implementations for the Merchant Revenue Agent
(plan.md Section 13.4).

Each `make_*_node(session)` function is a factory that closes over the
active AsyncSession and returns the actual node coroutine -- LangGraph node
functions only receive `state`, so per-request dependencies like a DB
session are bound in via closure rather than smuggled through state (state
must stay plain, checkpointable data, plan.md Section 13.1).

Exactly one node (generate_candidates) calls the LLM (Groq). Every other
node is ordinary deterministic Python -- consistent with plan.md Rule 6:
the agent proposes using AI creativity for *what* to propose, but
AgentPay's deterministic checks (via submit_proposal ->
app.services.merchant_service) are what actually decide whether a
proposal is allowed.
"""
import logging

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.merchant import tools
from app.agents.merchant.prompts import build_merchant_agent_system_prompt
from app.agents.merchant.state import MerchantAgentState
from app.ai.errors import LLMError
from app.ai.llm_client import classify_with_schema
from app.core.constants import MAX_MERCHANT_PROPOSALS
from app.schemas.proposal import MerchantProposal, ProposalStatus

logger = logging.getLogger("agentpay.merchant_agent")


class _CandidateProposal(BaseModel):
    """
    One LLM-generated upsell/cross-sell idea (internal to this module).

    quantity uses ge=1 rather than gt=0 for historical reasons: under the
    project's previous Gemini-backed client, Pydantic's gt=0 compiled to
    JSON Schema's "exclusiveMinimum" keyword, which Gemini's provider-side
    structured-output validator rejected outright (verified live). ge=1
    was the fix (compiles to "minimum", which Gemini did support). The
    current Groq-backed client (app.ai.llm_client) validates the response
    with Pydantic client-side rather than relying on provider-side schema
    enforcement, so this constraint is no longer strictly load-bearing, but
    ge=1 remains the semantically correct constraint regardless.
    """

    product_id: str
    quantity: int = Field(ge=1)
    reason: str
    estimated_value_add_minor: int = Field(
        description="The LLM's estimate of the added basket value, in minor currency units."
    )


class _CandidateProposalList(BaseModel):
    """The structured shape requested from the LLM in generate_candidates()."""

    candidates: list[_CandidateProposal]


def make_analyze_cart_node(session: AsyncSession):
    """Build the analyze_cart node: load the cart being checked out."""

    async def analyze_cart(state: MerchantAgentState) -> dict:
        cart = await tools.get_cart(session, state["cart_id"])
        merchant_name = await tools.get_merchant_name(session, cart.merchant_id)
        return {
            "original_cart": cart.model_dump(mode="json"),
            "merchant_id": cart.merchant_id,
            "merchant_name": merchant_name,
        }

    return analyze_cart


def make_search_relevant_products_node(session: AsyncSession):
    """
    Build the search_relevant_products node: find this merchant's products
    that could actually become an accepted proposal for this cart -- not
    already in the cart, in a category the mandate allows, and priced (at
    quantity 1) within the mandate's remaining headroom.

    This filtering is deterministic, not left to the LLM's judgment: without
    it, generate_candidates previously ranked every in-stock product purely
    by "value add," with no visibility into the mandate's real category/
    budget constraints -- it could rank its full 3 attempts on candidates
    that were always going to be rejected downstream (wrong category, or
    priced above what's left of the cap), even when a smaller, in-category,
    in-budget candidate sat in the very same catalog the whole time.
    """

    async def search_relevant_products(state: MerchantAgentState) -> dict:
        all_products = await tools.search_products(session, state["merchant_id"])
        cart_product_ids = {item["product_id"] for item in state["original_cart"]["items"]}
        allowed_categories = set(state["mandate_allowed_categories"])
        headroom_minor = state["mandate_max_amount_minor"] - state["original_cart"]["subtotal_minor"]
        candidates = [
            p.model_dump(mode="json")
            for p in all_products
            if p.product_id not in cart_product_ids
            and p.category in allowed_categories
            and p.price_minor <= headroom_minor
        ]
        return {"candidate_products": candidates}

    return search_relevant_products


def make_check_inventory_node(session: AsyncSession):
    """Build the check_inventory node: fetch live stock for every candidate."""

    async def check_inventory(state: MerchantAgentState) -> dict:
        results: dict[str, int] = {}
        for product in state["candidate_products"]:
            inventory = await tools.check_inventory(session, product["product_id"])
            results[product["product_id"]] = inventory.available_quantity
        return {"inventory_results": results}

    return check_inventory


def make_generate_candidates_node():
    """
    Build the generate_candidates node: the one LLM call in this graph.

    Asks the LLM (structured output) for a ranked list of upsell/cross-sell
    ideas given the cart and in-stock candidates. On any LLM failure, fails
    soft (empty candidate list) rather than raising -- a merchant agent
    outage must never block a checkout that doesn't even involve it
    (plan.md Rule 6: advisory only).
    """

    async def generate_candidates(state: MerchantAgentState) -> dict:
        in_stock = [
            p for p in state["candidate_products"] if state["inventory_results"].get(p["product_id"], 0) > 0
        ]
        if not in_stock:
            return {"ranked_candidates": []}

        headroom_minor = state["mandate_max_amount_minor"] - state["original_cart"]["subtotal_minor"]
        prompt = (
            f"Current cart (already authorized, do not modify it directly):\n"
            f"{state['original_cart']}\n\n"
            f"The buyer's mandate leaves {headroom_minor} minor currency units of headroom above this "
            "cart's current subtotal -- every candidate below already fits that headroom at quantity 1, "
            "but pick a quantity whose total price (unit price x quantity) does not exceed it.\n\n"
            f"In-stock candidate products you may propose adding (already filtered to this mandate's "
            f"allowed categories and this remaining headroom):\n"
            f"{in_stock}\n\n"
            "Propose up to 3 ranked upsell/cross-sell candidates from this list "
            "that would genuinely increase basket value for this cart."
        )
        system_instruction = build_merchant_agent_system_prompt(state["merchant_name"])
        try:
            result = await classify_with_schema(prompt, _CandidateProposalList, system_instruction=system_instruction)
        except LLMError:
            logger.warning("Merchant agent: LLM unavailable, proceeding with no proposal.", exc_info=True)
            return {"ranked_candidates": []}

        return {"ranked_candidates": [c.model_dump(mode="json") for c in result.candidates]}

    return generate_candidates


def _pick_best_untried_candidate(state: MerchantAgentState) -> dict | None:
    """
    Pick the highest-value candidate from state["ranked_candidates"] that
    hasn't already been tried in state["proposal_history"].

    Shared by rank_revenue_opportunity (the first pick) and revise_proposal
    (each subsequent pick from the same pool) -- both are "pick the best of
    what's left," just at different points in the revision loop.

    Returns:
        A MerchantProposal-shaped dict, or None if no untried candidate remains.
    """
    tried_product_ids = {entry["proposal"]["product_id"] for entry in state["proposal_history"]}
    remaining = [c for c in state["ranked_candidates"] if c["product_id"] not in tried_product_ids]
    if not remaining:
        return None

    best = max(remaining, key=lambda c: c["estimated_value_add_minor"])
    proposal = MerchantProposal(product_id=best["product_id"], quantity=best["quantity"], reason=best["reason"])
    return proposal.model_dump(mode="json")


def make_rank_revenue_opportunity_node():
    """
    Build the rank_revenue_opportunity node: deterministically pick the best
    not-yet-tried candidate (highest estimated value add).
    """

    async def rank_revenue_opportunity(state: MerchantAgentState) -> dict:
        return {"proposal": _pick_best_untried_candidate(state)}

    return rank_revenue_opportunity


def make_submit_proposal_node(session: AsyncSession):
    """
    Build the submit_proposal node: submit the current proposal to
    AgentPay's proposal pathway and record the outcome.
    """

    async def submit_proposal(state: MerchantAgentState) -> dict:
        proposal = MerchantProposal.model_validate(state["proposal"])
        evaluation = await tools.submit_proposal(session, state["cart_id"], state["mandate_id"], proposal)

        history_entry = {
            "proposal": proposal.model_dump(mode="json"),
            "allowed": evaluation.allowed,
            "reason_code": evaluation.reason_code,
        }
        update: dict = {
            "proposal_history": [*state["proposal_history"], history_entry],
            "attempt_count": state["attempt_count"] + 1,
            "last_reason_code": evaluation.reason_code,
        }
        if evaluation.allowed:
            update["final_status"] = ProposalStatus.PROPOSAL_ALLOWED
            update["final_proposal"] = proposal.model_dump(mode="json")
        return update

    return submit_proposal


def make_read_block_reason_node():
    """
    Build the read_block_reason node.

    A deliberately trivial pass-through: state["last_reason_code"] is
    already set by submit_proposal. This node exists as its own step
    (plan.md Section 13.4) so the graph/trace explicitly shows "the agent
    read the block reason" as a distinct moment, useful for the demo trace
    (plan.md Section 49).
    """

    async def read_block_reason(state: MerchantAgentState) -> dict:
        logger.info("Merchant agent: proposal blocked (%s), reading reason before revising.", state["last_reason_code"])
        return {}

    return read_block_reason


def make_revise_proposal_node():
    """
    Build the revise_proposal node: pick the next-best not-yet-tried
    candidate, reusing the same ranked_candidates the LLM already generated
    (no second LLM call needed to "revise" -- the ranking already
    accounts for multiple options).
    """

    async def revise_proposal(state: MerchantAgentState) -> dict:
        return {"proposal": _pick_best_untried_candidate(state)}

    return revise_proposal


def make_accept_original_cart_node():
    """
    Build the accept_original_cart node: the graph's other terminal state.

    Reached when three proposals were all rejected (attempt_count reaches
    MAX_MERCHANT_PROPOSALS), or when no viable candidate ever existed.
    Per plan.md Rule 7/Section 27, this is a legitimate, non-error outcome.
    """

    async def accept_original_cart(state: MerchantAgentState) -> dict:
        status = ProposalStatus.ORIGINAL_CART_RETAINED if state["attempt_count"] > 0 else ProposalStatus.NO_PROPOSAL
        return {"final_status": status, "final_proposal": None}

    return accept_original_cart
