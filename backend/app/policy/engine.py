"""
Purpose: Aggregate AgentPay's deterministic hard checks into one pass/block
decision (plan.md Section 11.2).

`run_hard_checks()` is ordinary, deterministic Python code. It never calls
the LLM -- per plan.md Rule 1 ("hard constraints run first"),
this is exactly the gate that must pass before any AI classification could
ever be invoked in later phases.
"""
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import CART_STATUS_FROZEN
from app.db.models.cart import Cart
from app.db.models.mandate import Mandate
from app.policy import checks
from app.schemas.mandate import SignedMandate


class HardCheckResult(BaseModel):
    """Aggregate outcome of AgentPay's deterministic hard-check pipeline."""

    passed: bool
    reason_code: str | None = None
    reason: str | None = None


def _block(result: checks.PolicyCheckResult) -> HardCheckResult:
    """Convert a failed PolicyCheckResult into a blocking HardCheckResult."""
    return HardCheckResult(passed=False, reason_code=result.reason_code, reason=result.reason)


async def run_hard_checks(
    session: AsyncSession,
    signed_mandate: SignedMandate,
    mandate_row: Mandate,
    public_key_b64: str,
    cart: Cart,
    allowed_categories: list[str],
) -> HardCheckResult:
    """
    Run every applicable deterministic check for a checkout request, in
    order, stopping and returning BLOCK at the first failure.

    Args:
        session: Active AsyncSession.
        signed_mandate: The mandate payload + signature authorizing this cart.
        mandate_row: The persisted Mandate row (for its current status).
        public_key_b64: The merchant's Ed25519 public key.
        cart: The cart being checked out.
        allowed_categories: MandatePayload.allowed_categories.

    Returns:
        HardCheckResult. passed=True only if every applicable check passes.

    Behavior depends on the cart's current status:
    - FROZEN (already checked out once): only check_cart_integrity and
      check_idempotency apply -- a second checkout request on an
      already-frozen cart is either a tamper attempt (CART_HASH_MISMATCH)
      or a duplicate request (IDEMPOTENCY_DUPLICATE); both BLOCK.
    - OPEN (first checkout request): check_mandate,
      check_mandate_not_reused_by_another_cart, check_category, and
      check_inventory run in sequence.
    """
    if cart.status == CART_STATUS_FROZEN:
        integrity_result = await checks.check_cart_integrity(session, cart)
        if not integrity_result.passed:
            return _block(integrity_result)
        # Untampered but already frozen: this is a repeat of a request that
        # already succeeded, not a new checkout attempt.
        duplicate_result = checks.check_idempotency(cart, cart.frozen_hash)
        return _block(duplicate_result)

    mandate_result = checks.check_mandate(signed_mandate, mandate_row, public_key_b64, cart)
    if not mandate_result.passed:
        return _block(mandate_result)

    # Phase 10: block reusing an ACTIVE-but-unpaid mandate to freeze a
    # second, different cart -- see check_mandate_not_reused_by_another_cart's
    # docstring for why this can't rely on mandate.single_use consumption
    # alone (that only happens at payment capture, much later).
    reuse_result = await checks.check_mandate_not_reused_by_another_cart(session, cart, mandate_row)
    if not reuse_result.passed:
        return _block(reuse_result)

    category_result = await checks.check_category(session, cart, allowed_categories)
    if not category_result.passed:
        return _block(category_result)

    inventory_result = await checks.check_inventory(session, cart)
    if not inventory_result.passed:
        return _block(inventory_result)

    return HardCheckResult(passed=True)
