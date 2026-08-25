"""
Purpose: Final deterministic re-validation after an Intent-Gate-approved
merchant proposal has been applied to a frozen cart (plan.md Section 8.3 /
Section 11 "Post-LLM behavior" / Section 15 step 13).

Distinct from app.policy.engine.run_hard_checks(): that function is Phase
3's pre-LLM gate, and its FROZEN-cart branch treats any second call on an
already-FROZEN cart as either tamper (CART_HASH_MISMATCH) or a duplicate
request (IDEMPOTENCY_DUPLICATE) -- neither applies here. This module runs
immediately after app.services.checkout_service itself re-freezes a cart it
just modified, within the same request_checkout() call; there is no
"duplicate request" to detect, and the hash being checked is the one
AgentPay just (re)computed, not one a prior request already consumed.

Re-runs the full amount/category/inventory/mandate check set against the
cart's final state -- an accepted upsell could in principle push the total
over the mandate's cap even though the same check already passed inside
app.services.merchant_service.evaluate_proposal() moments earlier -- so
nothing the merchant agent or intent gate approved can silently expand the
money boundary (plan.md Rule 1). This also runs, unmodified, on the
no-proposal path: plan.md Section 5 states the original cart proceeds
"directly from hard checks to final re-validation" even with no proposal,
so there is exactly one authoritative gate immediately before Razorpay,
regardless of which path reached it.
"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.cart import Cart
from app.db.models.mandate import Mandate
from app.policy import checks
from app.policy.engine import HardCheckResult
from app.schemas.mandate import SignedMandate


async def run_final_revalidation(
    session: AsyncSession,
    signed_mandate: SignedMandate,
    mandate_row: Mandate,
    public_key_b64: str,
    cart: Cart,
    allowed_categories: list[str],
) -> HardCheckResult:
    """
    Re-run every deterministic check against a cart's final (possibly
    merchant-modified) state, immediately after AgentPay re-freezes it.

    Args:
        session: Active AsyncSession.
        signed_mandate: The mandate payload + signature authorizing this cart.
        mandate_row: The persisted Mandate row (for its current status).
        public_key_b64: The merchant's Ed25519 public key.
        cart: The cart in its final state (already re-frozen if a proposal
            was applied).
        allowed_categories: MandatePayload.allowed_categories.

    Returns:
        HardCheckResult. passed=True only if the cart's stored frozen_hash
        matches its current contents, and it still satisfies the mandate's
        amount cap, category, and inventory constraints.
    """
    integrity_result = await checks.check_cart_integrity(session, cart)
    if not integrity_result.passed:
        return HardCheckResult(
            passed=False, reason_code=integrity_result.reason_code, reason=integrity_result.reason
        )

    mandate_result = checks.check_mandate(signed_mandate, mandate_row, public_key_b64, cart)
    if not mandate_result.passed:
        return HardCheckResult(passed=False, reason_code=mandate_result.reason_code, reason=mandate_result.reason)

    category_result = await checks.check_category(session, cart, allowed_categories)
    if not category_result.passed:
        return HardCheckResult(
            passed=False, reason_code=category_result.reason_code, reason=category_result.reason
        )

    inventory_result = await checks.check_inventory(session, cart)
    if not inventory_result.passed:
        return HardCheckResult(
            passed=False, reason_code=inventory_result.reason_code, reason=inventory_result.reason
        )

    return HardCheckResult(passed=True)
