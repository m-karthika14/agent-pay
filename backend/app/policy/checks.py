"""
Purpose: Individual deterministic hard checks for the AgentPay policy engine
(plan.md Section 11.1).

Design note on how the eleven named checks map to functions here:

Section 11.1 lists eleven check names: check_signature, check_mandate_active,
check_merchant, check_category, check_amount_cap, check_currency,
check_inventory, check_cart_integrity, check_single_use, check_replay,
check_idempotency. Seven of these (signature, mandate_active, merchant,
amount_cap, currency, single_use, replay) are all facets of "is this mandate
valid for this request" -- app.security.mandate_verifier.verify_mandate()
already implements exactly this fail-fast sequence and is unit tested
(tests/unit/test_mandate_verifier.py). Re-deriving each of those seven as a
separate function here would duplicate that logic rather than reuse it
(explicitly against plan.md's instructions), so check_mandate() below calls
verify_mandate() once and covers all seven.

The remaining four checks are genuinely new at Phase 3 and operate over the
CART (not a single mandate), so each gets its own real function:
check_category (a cart can hold items across multiple categories, which a
single verify_mandate() call cannot express), check_inventory,
check_cart_integrity, and check_idempotency.

check_mandate_not_reused_by_another_cart (Phase 10) is a fifth cart-level
check, added after the adversarial suite found that single-use enforcement
previously only applied at payment capture -- see its own docstring.
"""
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.carts.freeze import verify_cart_integrity as _verify_cart_integrity
from app.core.constants import CART_STATUS_FROZEN
from app.db.models.cart import Cart
from app.db.models.cart_item import CartItem
from app.db.models.inventory import Inventory
from app.db.models.mandate import Mandate
from app.db.models.product import Product
from app.policy import reason_codes
from app.schemas.mandate import SignedMandate
from app.security.mandate_verifier import verify_mandate


class PolicyCheckResult(BaseModel):
    """Outcome of one deterministic policy check."""

    passed: bool
    reason_code: str | None = None
    reason: str | None = None


def check_mandate(
    signed_mandate: SignedMandate,
    mandate_row: Mandate,
    public_key_b64: str,
    cart: Cart,
) -> PolicyCheckResult:
    """
    Verify the mandate itself is valid for this specific cart/checkout.

    Covers plan.md Section 11.1's check_signature, check_mandate_active,
    check_merchant, check_amount_cap, check_currency, check_single_use, and
    check_replay by delegating to app.security.mandate_verifier.verify_mandate
    (see module docstring for why this isn't duplicated as separate
    functions).

    Args:
        signed_mandate: The mandate payload + signature to verify.
        mandate_row: The persisted Mandate row (for its current status).
        public_key_b64: The merchant's Ed25519 public key.
        cart: The cart being checked out -- its merchant_id, subtotal_minor,
            and currency become the mandate's "requested" values.

    Returns:
        PolicyCheckResult; passed=False carries the specific reason_code
        (MANDATE_INVALID_SIGNATURE, MANDATE_EXPIRED, MANDATE_MERCHANT_MISMATCH,
        MANDATE_AMOUNT_EXCEEDED, MANDATE_CURRENCY_MISMATCH,
        MANDATE_ALREADY_CONSUMED, or REPLAY_DETECTED).
    """
    result = verify_mandate(
        signed_mandate,
        public_key_b64,
        current_status=mandate_row.status,
        expected_merchant_id=str(cart.merchant_id),
        requested_amount=cart.subtotal_minor,
        requested_currency=cart.currency,
    )
    return PolicyCheckResult(passed=result.valid, reason_code=result.reason_code, reason=result.reason)


async def check_category(
    session: AsyncSession, cart: Cart, allowed_categories: list[str]
) -> PolicyCheckResult:
    """
    Verify every product in the cart belongs to a category the mandate allows.

    Args:
        session: Active AsyncSession.
        cart: The cart to check.
        allowed_categories: MandatePayload.allowed_categories.

    Returns:
        PolicyCheckResult; passed=False (MANDATE_CATEGORY_FORBIDDEN) if any
        line item's product category is not in allowed_categories.
    """
    result = await session.execute(
        select(Product.category)
        .join(CartItem, CartItem.product_id == Product.id)
        .where(CartItem.cart_id == cart.id)
    )
    categories = {row[0] for row in result.all()}
    disallowed = categories - set(allowed_categories)
    if disallowed:
        return PolicyCheckResult(
            passed=False,
            reason_code=reason_codes.MANDATE_CATEGORY_FORBIDDEN,
            reason=f"Cart contains disallowed categor{'y' if len(disallowed) == 1 else 'ies'}: {', '.join(sorted(disallowed))}.",
        )
    return PolicyCheckResult(passed=True)


async def check_inventory(session: AsyncSession, cart: Cart) -> PolicyCheckResult:
    """
    Re-verify every cart line item still has sufficient available stock.

    This re-checks inventory at checkout time, distinct from the check
    already performed when items were added to the cart (plan.md Section
    10.2) -- stock can change between add-to-cart and checkout.

    Args:
        session: Active AsyncSession.
        cart: The cart to check.

    Returns:
        PolicyCheckResult; passed=False (INVENTORY_INVALID) if any item now
        requests more than is currently available.
    """
    result = await session.execute(
        select(CartItem.quantity, Product.name, Inventory.quantity, Inventory.reserved_quantity)
        .join(Product, Product.id == CartItem.product_id)
        .outerjoin(Inventory, Inventory.product_id == Product.id)
        .where(CartItem.cart_id == cart.id)
    )
    for requested_qty, product_name, stock_qty, reserved_qty in result.all():
        available = (stock_qty - reserved_qty) if stock_qty is not None else 0
        if requested_qty > available:
            return PolicyCheckResult(
                passed=False,
                reason_code=reason_codes.INVENTORY_INVALID,
                reason=f"Only {available} unit(s) of '{product_name}' are available; cart requests {requested_qty}.",
            )
    return PolicyCheckResult(passed=True)


async def check_cart_integrity(session: AsyncSession, cart: Cart) -> PolicyCheckResult:
    """
    Verify a previously-FROZEN cart's contents have not been altered since
    freezing (plan.md Rule: "frozen hash != final hash -> BLOCK").

    Args:
        session: Active AsyncSession.
        cart: A cart with status FROZEN.

    Returns:
        PolicyCheckResult; passed=False (CART_HASH_MISMATCH) if the
        recomputed hash no longer matches the stored frozen_hash.
    """
    if await _verify_cart_integrity(session, cart):
        return PolicyCheckResult(passed=True)
    return PolicyCheckResult(
        passed=False,
        reason_code=reason_codes.CART_HASH_MISMATCH,
        reason="Cart contents no longer match the frozen hash computed at checkout time.",
    )


def check_idempotency(cart: Cart, current_hash: str) -> PolicyCheckResult:
    """
    Detect a repeat checkout request for a cart that was already frozen.

    Args:
        cart: A cart with status FROZEN (already checked out once).
        current_hash: The hash recomputed from the cart's current contents
            (from check_cart_integrity / verify_cart_integrity), confirmed
            to match cart.frozen_hash before this is called.

    Returns:
        PolicyCheckResult with passed=False and reason_code
        IDEMPOTENCY_DUPLICATE -- per plan.md's Phase 3 acceptance criteria,
        a duplicate checkout request on an already-frozen, untampered cart
        is explicitly rejected rather than silently re-processed.
    """
    return PolicyCheckResult(
        passed=False,
        reason_code=reason_codes.IDEMPOTENCY_DUPLICATE,
        reason=f"Cart '{cart.id}' was already checked out (frozen_hash={current_hash}).",
    )


async def check_mandate_not_reused_by_another_cart(
    session: AsyncSession, cart: Cart, mandate_row: Mandate
) -> PolicyCheckResult:
    """
    Verify this mandate has not already been used to freeze a DIFFERENT
    cart (Phase 10 -- found by the adversarial suite's cap_splitting cases).

    Single-use enforcement (plan.md Rule 7 / mandate.single_use) previously
    only applied at payment capture (app.mandates.service.consume_mandate),
    which only marks a mandate CONSUMED once its transaction is actually
    paid. That left a window: an ACTIVE-but-unpaid mandate could be reused
    via request_checkout() to freeze a second, different cart, and both
    carts could independently go on to request a Razorpay order (since
    idempotency there is keyed per-cart, not per-mandate). This check closes
    that window at the earlier, checkout-freeze point instead of relying
    solely on payment-time consumption.

    Args:
        session: Active AsyncSession.
        cart: The cart about to be frozen (still OPEN).
        mandate_row: The persisted Mandate row authorizing this cart.

    Returns:
        PolicyCheckResult; passed=False
        (MANDATE_ALREADY_ASSOCIATED_WITH_ANOTHER_CART) if any OTHER cart is
        already FROZEN under this same mandate.
    """
    result = await session.execute(
        select(Cart.id).where(
            Cart.mandate_id == mandate_row.id, Cart.id != cart.id, Cart.status == CART_STATUS_FROZEN
        )
    )
    existing_cart_id = result.scalars().first()
    if existing_cart_id is not None:
        return PolicyCheckResult(
            passed=False,
            reason_code=reason_codes.MANDATE_ALREADY_ASSOCIATED_WITH_ANOTHER_CART,
            reason=f"Mandate '{mandate_row.mandate_id}' already froze a different cart ('{existing_cart_id}').",
        )
    return PolicyCheckResult(passed=True)
