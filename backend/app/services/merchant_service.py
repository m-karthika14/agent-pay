"""
Purpose: AgentPay's proposal-evaluation pathway (plan.md Section 13.3,
Section 27) -- what the Merchant Revenue Agent's submit_proposal() tool
actually calls.

This is deliberately NOT a REST/MCP-facing service: the merchant agent
(app.agents.merchant) is the only caller. It never mutates the cart --
per plan.md Rule 6, the merchant agent is advisory only, so this function
only evaluates a hypothetical modification and reports whether it would be
allowed, using the existing deterministic checks.

Phase 6 scope note (see app.schemas.proposal.ProposalEvaluation docstring):
this only re-runs deterministic policy (mandate amount cap, category,
inventory) against the FROZEN cart plus the proposed addition. It
deliberately does not evaluate semantic intent (e.g. "no accessories" even
when the category is technically allowed) -- that is the Intent Gate's job,
added in Phase 7. A proposal that passes here is not yet a fully-approved
purchase; app.services.checkout_service is extended in Phase 8 to also run
the Intent Gate before any modified cart is actually applied.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models.cart import Cart
from app.db.models.inventory import Inventory
from app.db.models.product import Product
from app.mandates.service import get_mandate_by_business_id, to_signed_mandate
from app.policy import reason_codes
from app.policy.checks import check_mandate
from app.schemas.common import NotFoundError
from app.schemas.proposal import MerchantProposal, ProposalEvaluation


async def evaluate_proposal(
    session: AsyncSession, cart_id: uuid.UUID, mandate_id: str, proposal: MerchantProposal
) -> ProposalEvaluation:
    """
    Evaluate a merchant-proposed cart addition against AgentPay's
    deterministic checks, without applying it to the cart.

    Args:
        session: Active AsyncSession.
        cart_id: The (already-frozen) cart the proposal would modify.
        mandate_id: Business-facing mandate_id authorizing the original cart.
        proposal: The proposed addition (product + quantity + reason).

    Returns:
        ProposalEvaluation. allowed=True only if the hypothetical modified
        cart would still satisfy the mandate's amount cap and category
        restrictions, and the proposed quantity is in stock.

    Raises:
        NotFoundError: If the cart, mandate, or proposed product don't exist.
    """
    cart = await session.get(Cart, cart_id)
    if cart is None:
        raise NotFoundError("CART_NOT_FOUND", f"No cart with id '{cart_id}'.")

    mandate_row = await get_mandate_by_business_id(session, mandate_id)
    if mandate_row is None:
        raise NotFoundError("MANDATE_NOT_FOUND", f"No mandate with id '{mandate_id}'.")
    signed_mandate = to_signed_mandate(mandate_row)

    product = await session.get(Product, uuid.UUID(proposal.product_id))
    if product is None or not product.is_active:
        raise NotFoundError("PRODUCT_NOT_FOUND", f"No active product with id '{proposal.product_id}'.")

    # --- Amount cap: reuse check_mandate() against a hypothetical subtotal. ---
    # A shallow, unpersisted copy so we never risk writing this hypothetical
    # total back to the real (frozen, immutable) cart row.
    hypothetical_cart = Cart(
        id=cart.id,
        merchant_id=cart.merchant_id,
        currency=cart.currency,
        subtotal_minor=cart.subtotal_minor + product.price_minor * proposal.quantity,
        status=cart.status,
    )
    public_key_b64 = _get_public_key_b64()
    mandate_check = check_mandate(signed_mandate, mandate_row, public_key_b64, hypothetical_cart)
    if not mandate_check.passed:
        return ProposalEvaluation(
            allowed=False, reason_code=mandate_check.reason_code, reason=mandate_check.reason
        )

    # --- Category: is the proposed product's category mandate-allowed? ---
    if product.category not in signed_mandate.payload.allowed_categories:
        return ProposalEvaluation(
            allowed=False,
            reason_code=reason_codes.MANDATE_CATEGORY_FORBIDDEN,
            reason=f"Proposed product category '{product.category}' is not in the mandate's allowed categories.",
        )

    # --- Inventory: is the proposed quantity actually in stock? ---
    inventory_result = await session.execute(select(Inventory).where(Inventory.product_id == product.id))
    inventory = inventory_result.scalar_one_or_none()
    available = (inventory.quantity - inventory.reserved_quantity) if inventory else 0
    if proposal.quantity > available:
        return ProposalEvaluation(
            allowed=False,
            reason_code=reason_codes.INVENTORY_INVALID,
            reason=f"Only {available} unit(s) of '{product.name}' are available; proposal requests {proposal.quantity}.",
        )

    return ProposalEvaluation(allowed=True)


def _get_public_key_b64() -> str:
    """Return the merchant's Ed25519 public key, for verifying the mandate signature."""
    return get_settings().ed25519_public_key_b64
