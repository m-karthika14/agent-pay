"""
Purpose: Orchestrate `request_checkout()` -- the deterministic AgentPay
checkout boundary (plan.md Section 15).

Phase 3 scope: this implements steps 1-8 and 14 of Section 15's full
fourteen-step flow (load mandate, run hard checks, load cart, freeze,
compute hash, persist, return approved state). Steps 9-13 (invoke merchant
advisor, run intent gate, handle proposal accept/reject) do not exist yet --
the Merchant Revenue Agent (Phase 6) and Intent Gate (Phase 7) are built
later, at which point this function gains an optional advisory step between
the hard checks and freezing. It is not stubbed out early.

Every hard-check outcome (pass or block) is recorded to the audit log,
matching plan.md Rule 1: "BLOCK -> reason code -> audit event."
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import append_event
from app.carts.freeze import freeze_cart
from app.carts.service import to_cart_response
from app.core.config import get_settings
from app.core.constants import CART_STATUS_FROZEN
from app.db.models.cart import Cart
from app.mandates.service import get_mandate_by_business_id, to_signed_mandate
from app.policy.engine import run_hard_checks
from app.schemas.audit import AuditEventInput
from app.schemas.checkout import CheckoutResponse
from app.schemas.common import NotFoundError, ValidationError


async def _load_cart_or_raise(session: AsyncSession, cart_id: uuid.UUID) -> Cart:
    """Fetch a cart by id, raising NotFoundError if it does not exist."""
    cart = await session.get(Cart, cart_id)
    if cart is None:
        raise NotFoundError("CART_NOT_FOUND", f"No cart with id '{cart_id}'.")
    return cart


async def request_checkout(session: AsyncSession, cart_id: uuid.UUID, mandate_id: str) -> CheckoutResponse:
    """
    Run AgentPay's deterministic checkout boundary for a cart.

    Order of operations (plan.md Section 15, Phase 3 subset):
        1. Load mandate (by business mandate_id).
        2-5. Run hard checks: mandate validity, category, inventory
             (app.policy.engine.run_hard_checks) -- or, if the cart was
             already frozen by a prior call, integrity + duplicate checks.
        6-7. Freeze the cart and compute its SHA-256 hash.
        8. Persist checkout state (cart row is updated in place).
        14. Return the approved checkout state.

    Args:
        session: Active AsyncSession.
        cart_id: The cart to check out.
        mandate_id: Business-facing mandate_id authorizing this cart.

    Returns:
        CheckoutResponse with the now-FROZEN cart and its hash.

    Raises:
        NotFoundError: If the cart or mandate does not exist.
        ValidationError: If any hard check fails. The exception's
            reason_code is the specific failing check's code (e.g.
            MANDATE_AMOUNT_EXCEEDED, MANDATE_CATEGORY_FORBIDDEN,
            INVENTORY_INVALID, CART_HASH_MISMATCH, IDEMPOTENCY_DUPLICATE).
            The block is always audited before this is raised.
    """
    mandate_row = await get_mandate_by_business_id(session, mandate_id)
    if mandate_row is None:
        raise NotFoundError("MANDATE_NOT_FOUND", f"No mandate with id '{mandate_id}'.")
    signed_mandate = to_signed_mandate(mandate_row)

    cart = await _load_cart_or_raise(session, cart_id)

    was_already_frozen = cart.status == CART_STATUS_FROZEN
    public_key_b64 = get_settings().ed25519_public_key_b64

    hard_check = await run_hard_checks(
        session, signed_mandate, mandate_row, public_key_b64, cart, signed_mandate.payload.allowed_categories
    )

    if not hard_check.passed:
        event_type = "CART_REVALIDATION_BLOCKED" if was_already_frozen else "HARD_POLICY_BLOCKED"
        await append_event(
            session,
            AuditEventInput(
                event_type=event_type,
                actor_type="SYSTEM",
                payload={"cart_id": str(cart.id), "reason_code": hard_check.reason_code},
                decision="BLOCK",
                reason_code=hard_check.reason_code,
                mandate_id=str(mandate_row.id),
            ),
        )
        raise ValidationError(hard_check.reason_code, hard_check.reason or "Checkout blocked.")

    event_type = "CART_REVALIDATION_PASSED" if was_already_frozen else "HARD_POLICY_PASSED"
    await append_event(
        session,
        AuditEventInput(
            event_type=event_type,
            actor_type="SYSTEM",
            payload={"cart_id": str(cart.id)},
            decision="PASS",
            mandate_id=str(mandate_row.id),
        ),
    )

    if not was_already_frozen:
        cart = await freeze_cart(session, cart)
        await append_event(
            session,
            AuditEventInput(
                event_type="CART_FROZEN",
                actor_type="SYSTEM",
                payload={"cart_id": str(cart.id), "frozen_hash": cart.frozen_hash},
                mandate_id=str(mandate_row.id),
            ),
        )

    cart_response = await to_cart_response(session, cart)
    return CheckoutResponse(cart=cart_response, frozen_hash=cart.frozen_hash, frozen_at=cart.frozen_at)
