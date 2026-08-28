"""
Purpose: LangGraph state definition for the Merchant Revenue Agent
(plan.md Section 13.1).

A TypedDict (LangGraph's standard state shape) rather than a live ORM/session
object -- state must stay plain, serializable data so LangGraph can track
and pass it between nodes. Nodes that need database access receive the
AsyncSession separately, via closures built in graph.py (see that module's
docstring for why).
"""
from typing import Any, TypedDict


class MerchantAgentState(TypedDict):
    """
    The Merchant Revenue Agent's working state, threaded through every node
    in the graph (plan.md Section 13.1's exact field list, plus a couple of
    plain-data fields nodes need to pass results forward).
    """

    cart_id: str
    merchant_id: str
    #: This cart's merchant's display name (e.g. "TechHub") -- used to build
    #: a per-merchant system prompt (app.agents.merchant.prompts) and to
    #: scope candidate product search to this merchant only.
    merchant_name: str
    mandate_id: str
    #: The mandate's real spending ceiling and category allow-list (from
    #: SignedMandate.payload, read once by checkout_service before this
    #: graph runs) -- used to deterministically filter candidates in
    #: search_relevant_products() to ones that could actually be accepted,
    #: instead of letting the LLM rank purely by "value add" and only
    #: discovering a category/budget mismatch after submitting.
    mandate_max_amount_minor: int
    mandate_allowed_categories: list[str]

    #: Snapshot of the cart at the start of the run (CartResponse.model_dump()).
    original_cart: dict[str, Any]

    #: The cart's own items, WITH their real product descriptions (CartResponse
    #: itself carries only name/category/price per item, no description) --
    #: given to the LLM so it can ground any compatibility/necessity claim in
    #: what the purchased product's own listing actually says, instead of
    #: inventing a plausible-sounding technical claim about it (a live
    #: reported case: the agent asserted a charging cable was "essential for
    #: powering" a pair of earbuds -- a claim neither product's real
    #: description supports).
    cart_item_details: list[dict[str, Any]]

    #: Products not already in the cart, candidates for an upsell/cross-sell.
    candidate_products: list[dict[str, Any]]

    #: product_id -> available_quantity, for every candidate product.
    inventory_results: dict[str, int]

    #: Ranked candidates the LLM generated this round (product_id, quantity,
    #: reason, estimated_value_add), highest value first.
    ranked_candidates: list[dict[str, Any]]

    #: The specific proposal currently being (or about to be) submitted.
    proposal: dict[str, Any] | None

    #: Every {proposal, allowed, reason_code} pair attempted so far.
    proposal_history: list[dict[str, Any]]

    last_reason_code: str | None
    attempt_count: int

    #: Final outcome (a ProposalStatus value) once the graph reaches END.
    final_status: str
    #: The allowed proposal, if final_status == PROPOSAL_ALLOWED; else None.
    final_proposal: dict[str, Any] | None
