"""
Purpose: Tool wrappers the Merchant Revenue Agent's graph nodes call
(plan.md Section 13.3).

Every wrapper here calls an existing AgentPay service function -- never its
own reimplementation (plan.md Section 17's "one source of truth" rule
applies just as much here as to the MCP tools). In particular,
submit_proposal() calls app.services.merchant_service.evaluate_proposal(),
AgentPay's proposal pathway -- it never mutates the cart directly
(plan.md Rule 6: the merchant agent is advisory only).

These are plain async functions (not LLM/LangChain "function calling"
tools) because the graph's flow is a fixed sequence of nodes, not a
dynamic tool-selection loop -- see plan.md Section 13.5's graph structure.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.carts import service as carts_service
from app.catalog import service as catalog_service
from app.schemas.cart import CartResponse
from app.schemas.product import InventoryResponse, ProductResponse
from app.schemas.proposal import MerchantProposal, ProposalEvaluation
from app.services import merchant_service


async def get_cart(session: AsyncSession, cart_id: str) -> CartResponse:
    """Fetch the cart the agent is analyzing."""
    return await carts_service.get_cart(session, uuid.UUID(cart_id))


async def search_products(session: AsyncSession) -> list[ProductResponse]:
    """List the merchant's full active catalog."""
    return await catalog_service.list_products(session)


async def get_product(session: AsyncSession, product_id: str) -> ProductResponse:
    """Fetch a single product's details."""
    return await catalog_service.get_product(session, uuid.UUID(product_id))


async def check_inventory(session: AsyncSession, product_id: str) -> InventoryResponse:
    """Fetch a product's current stock level."""
    return await catalog_service.get_inventory(session, uuid.UUID(product_id))


def calculate_bundle(cart_subtotal_minor: int, candidate_price_minor: int, quantity: int) -> int:
    """
    Compute the hypothetical cart total if a candidate product were added.

    Args:
        cart_subtotal_minor: The cart's current subtotal, in minor units.
        candidate_price_minor: The candidate product's unit price.
        quantity: How many units are being proposed.

    Returns:
        The hypothetical new total, in minor units. Pure arithmetic --
        this does not check whether that total would actually be
        authorized; submit_proposal() (via AgentPay's proposal pathway)
        does that.
    """
    return cart_subtotal_minor + candidate_price_minor * quantity


async def submit_proposal(
    session: AsyncSession, cart_id: str, mandate_id: str, proposal: MerchantProposal
) -> ProposalEvaluation:
    """
    Submit a proposal to AgentPay's proposal pathway for evaluation.

    This is the ONLY way a proposal can affect anything -- it never
    mutates the cart itself. AgentPay decides allowed/rejected using its
    existing deterministic checks (plan.md Rule 6, Section 13.3).
    """
    return await merchant_service.evaluate_proposal(session, uuid.UUID(cart_id), mandate_id, proposal)
