"""
Purpose: Build the Merchant Revenue Agent's LangGraph workflow
(plan.md Section 13.5) -- the only LangGraph component in AgentPay
(plan.md Section 13, Section 10.1 rationale: this agent has a real
multi-step, stateful, tool-using workflow with a bounded revision loop,
which is exactly what LangGraph models well).

Graph shape:
    START -> analyze_cart -> search_relevant_products -> check_inventory
          -> generate_candidates -> rank_revenue_opportunity
          -> [no candidate?] -> accept_original_cart -> END
          -> [candidate?] -> submit_proposal
          -> [allowed?] -> END (final_status already PROPOSAL_ALLOWED)
          -> [rejected, attempts < MAX] -> read_block_reason -> revise_proposal -> submit_proposal (loop)
          -> [rejected, attempts == MAX] -> accept_original_cart -> END

build_merchant_agent_graph() is a factory (not a module-level singleton)
because each node closes over a specific request's AsyncSession -- a fresh
graph is built per request_checkout() call, mirroring how
app.mcp.tests build a fresh MCPServer per test for the same closure reason.
"""
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.merchant.nodes import (
    make_accept_original_cart_node,
    make_analyze_cart_node,
    make_check_inventory_node,
    make_generate_candidates_node,
    make_rank_revenue_opportunity_node,
    make_read_block_reason_node,
    make_revise_proposal_node,
    make_search_relevant_products_node,
    make_submit_proposal_node,
)
from app.agents.merchant.state import MerchantAgentState
from app.core.constants import MAX_MERCHANT_PROPOSALS
from app.schemas.proposal import ProposalStatus


def _route_after_ranking(state: MerchantAgentState) -> str:
    """After ranking (or re-ranking on a retry), submit if there's a candidate, else give up."""
    return "submit_proposal" if state["proposal"] is not None else "accept_original_cart"


def _route_after_submit(state: MerchantAgentState) -> str:
    """
    After a submission: stop if allowed, retry if attempts remain, else
    give up. This is the bounded revision loop (plan.md Rule 7): at most
    MAX_MERCHANT_PROPOSALS submit_proposal calls per cart.
    """
    if state["final_status"] == ProposalStatus.PROPOSAL_ALLOWED:
        return "END"
    if state["attempt_count"] >= MAX_MERCHANT_PROPOSALS:
        return "accept_original_cart"
    return "read_block_reason"


def build_merchant_agent_graph(session: AsyncSession) -> CompiledStateGraph:
    """
    Build and compile the Merchant Revenue Agent's graph for one run.

    Args:
        session: Active AsyncSession, bound into every node that needs
            database access via closure (see module docstring).

    Returns:
        A compiled LangGraph graph, ready for `.ainvoke(initial_state)`.
    """
    graph = StateGraph(MerchantAgentState)

    graph.add_node("analyze_cart", make_analyze_cart_node(session))
    graph.add_node("search_relevant_products", make_search_relevant_products_node(session))
    graph.add_node("check_inventory", make_check_inventory_node(session))
    graph.add_node("generate_candidates", make_generate_candidates_node())
    graph.add_node("rank_revenue_opportunity", make_rank_revenue_opportunity_node())
    graph.add_node("submit_proposal", make_submit_proposal_node(session))
    graph.add_node("read_block_reason", make_read_block_reason_node())
    graph.add_node("revise_proposal", make_revise_proposal_node())
    graph.add_node("accept_original_cart", make_accept_original_cart_node())

    graph.add_edge(START, "analyze_cart")
    graph.add_edge("analyze_cart", "search_relevant_products")
    graph.add_edge("search_relevant_products", "check_inventory")
    graph.add_edge("check_inventory", "generate_candidates")
    graph.add_edge("generate_candidates", "rank_revenue_opportunity")

    graph.add_conditional_edges(
        "rank_revenue_opportunity",
        _route_after_ranking,
        {"submit_proposal": "submit_proposal", "accept_original_cart": "accept_original_cart"},
    )
    graph.add_conditional_edges(
        "submit_proposal",
        _route_after_submit,
        {"END": END, "read_block_reason": "read_block_reason", "accept_original_cart": "accept_original_cart"},
    )
    graph.add_edge("read_block_reason", "revise_proposal")
    graph.add_conditional_edges(
        "revise_proposal",
        _route_after_ranking,
        {"submit_proposal": "submit_proposal", "accept_original_cart": "accept_original_cart"},
    )
    graph.add_edge("accept_original_cart", END)

    return graph.compile()
