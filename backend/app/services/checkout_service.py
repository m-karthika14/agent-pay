"""
Purpose: Orchestrate `request_checkout()` -- the deterministic AgentPay
checkout boundary (plan.md Section 15).

Implements the full fourteen-step flow: load mandate, run hard checks
(steps 1-5), freeze the cart and compute its hash (steps 6-8), optionally
invoke the Merchant Revenue Agent and, if it produces a hard-check-passed
proposal, run it through the Intent Gate (steps 9-11), apply an
Intent-Gate-allowed proposal and re-freeze (step 12), re-run every
deterministic check against the final cart state (step 13), and return the
approved checkout state (step 14).

Every hard-check/intent-gate/final-revalidation outcome (pass or block) is
recorded to the audit log, matching plan.md Rule 1: "BLOCK -> reason code ->
audit event."

Money-boundary invariant (plan.md Rule 1): the Merchant Revenue Agent and
Intent Gate can only ever *remove* a proposal from consideration (reject,
escalate) or let one through that already passed AgentPay's own
deterministic checks (app.services.merchant_service.evaluate_proposal) --
neither can grant authority beyond what the signed mandate allows. That is
why an Intent-Gate-allowed proposal is re-validated in full (step 13,
app.policy.final_revalidation) before this function returns: no AI output
reaches Razorpay without passing through deterministic code one more time.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.merchant.runner import run_merchant_agent
from app.audit.service import append_event
from app.authorization.service import get_approved_mandate_id_for_cart
from app.carts import service as carts_service
from app.carts.freeze import freeze_cart
from app.carts.service import to_cart_response
from app.core.config import get_settings
from app.core.constants import CART_STATUS_FROZEN
from app.db.models.cart import Cart
from app.db.models.mandate import Mandate
from app.db.models.product import Product
from app.intent.gate import evaluate_intent
from app.intent.models import IntentDecisionType, IntentGateInput
from app.mandates.service import get_mandate_by_business_id, to_signed_mandate
from app.policy.engine import run_hard_checks
from app.policy.final_revalidation import run_final_revalidation
from app.schemas.audit import AuditEventInput
from app.schemas.cart import CartResponse
from app.schemas.checkout import CheckoutResponse, ProposalOutcome
from app.schemas.common import NotFoundError, ValidationError
from app.schemas.mandate import SignedMandate
from app.schemas.proposal import ProposalStatus


async def _load_cart_or_raise(session: AsyncSession, cart_id: uuid.UUID) -> Cart:
    """Fetch a cart by id, raising NotFoundError if it does not exist."""
    cart = await session.get(Cart, cart_id)
    if cart is None:
        raise NotFoundError("CART_NOT_FOUND", f"No cart with id '{cart_id}'.")
    return cart


async def _resolve_mandate_id(session: AsyncSession, cart_id: uuid.UUID) -> str:
    """
    Resolve which mandate_id to use for a request_checkout() call that
    omitted one (plan.md Phase 2.1 -- Claude's cart-only checkout call).

    An already-FROZEN cart always reuses whatever mandate it was frozen
    under -- never re-resolved from app.authorization.service, since a
    *newer* APPROVED authorization request created after freezing must never
    silently redirect a duplicate-detection call (policy.checks.
    check_idempotency always BLOCKs a second request_checkout() on a frozen
    cart, regardless of mandate_id) to a different mandate. A still-OPEN
    cart resolves to its most recently APPROVED authorization request, if
    any.

    Raises:
        NotFoundError: If the cart does not exist.
        ValidationError: NO_APPROVED_AUTHORIZATION if neither source has a
            mandate yet.
    """
    cart = await _load_cart_or_raise(session, cart_id)
    if cart.mandate_id is not None:
        mandate_row = await session.get(Mandate, cart.mandate_id)
        if mandate_row is not None:
            return mandate_row.mandate_id

    resolved = await get_approved_mandate_id_for_cart(session, cart_id)
    if resolved is None:
        raise ValidationError(
            "NO_APPROVED_AUTHORIZATION",
            f"No mandate_id given and no approved authorization request exists yet for cart '{cart_id}' -- "
            "call check_authorization_status() and wait for APPROVED, or pass a mandate_id directly.",
        )
    return resolved


async def request_checkout(
    session: AsyncSession, cart_id: uuid.UUID, mandate_id: str | None = None, *, intent_gate_enabled: bool = True
) -> CheckoutResponse:
    """
    Run AgentPay's deterministic checkout boundary for a cart.

    Order of operations (plan.md Section 15):
        0. If mandate_id is omitted (plan.md Phase 2.1 -- Claude's
           cart-only checkout call), resolve it: an already-FROZEN cart
           reuses whatever mandate it was frozen under (never re-resolved
           from a newer authorization request -- see _resolve_mandate_id's
           docstring); a still-OPEN cart resolves to its most recently
           APPROVED authorization request, if any. Raises
           NO_APPROVED_AUTHORIZATION if neither source has one. This is
           purely a lookup of *which* mandate_id to use -- every check below
           runs in full afterward regardless of how mandate_id was obtained.
        1. Load mandate (by business mandate_id).
        2-5. Run hard checks: mandate validity, category, inventory
             (app.policy.engine.run_hard_checks) -- or, if the cart was
             already frozen by a prior call, integrity + duplicate checks.
        6-7. Freeze the cart and compute its SHA-256 hash.
        8. Persist checkout state (cart row is updated in place).
        9-13. Only on the call that performs the initial freeze (never on an
             idempotent re-validation call -- see _run_merchant_advisory's
             docstring): optionally invoke the Merchant Revenue Agent: if it
             produces a proposal that already passed its own deterministic
             checks, run the Intent Gate over it; if the gate ALLOWs it,
             apply it to the cart and re-freeze; finally, re-run every
             deterministic check against the cart's final state (whether or
             not a proposal was applied -- plan.md Section 5: the original
             cart proceeds "directly from hard checks to final
             re-validation" when there is no proposal too).
        14. Return the approved checkout state.

    Args:
        session: Active AsyncSession.
        cart_id: The cart to check out.
        mandate_id: Business-facing mandate_id authorizing this cart, or
            None to resolve it from the cart's own state (plan.md Phase
            2.1) -- see step 0 above.
        intent_gate_enabled: Whether a hard-check-passed merchant proposal
            must also pass the Intent Gate before being applied. Defaults
            to True (the real, production behavior). This exists ONLY for
            eval/'s Cap-only vs Intent-aware arm comparison (plan.md Section
            19.1) -- app.mcp.tools and the REST routes never pass this
            argument, so Claude and other external callers can never reach
            it. Setting it False does not weaken any hard check (amount,
            category, inventory, mandate validity all still run
            unconditionally); it only means a proposal that already passed
            those hard checks is applied without also being checked against
            the buyer's signed *intent* -- exactly the "Cap-only" arm's
            definition (plan.md Section 19.1).

    Returns:
        CheckoutResponse with the now-FROZEN cart, its hash, and (on the
        initial freeze) what happened to any merchant proposal.

    Raises:
        NotFoundError: If the cart or mandate does not exist.
        ValidationError: If any hard check, or the final re-validation,
            fails. The exception's reason_code is the specific failing
            check's code (e.g. MANDATE_AMOUNT_EXCEEDED,
            MANDATE_CATEGORY_FORBIDDEN, INVENTORY_INVALID,
            CART_HASH_MISMATCH, IDEMPOTENCY_DUPLICATE,
            NO_APPROVED_AUTHORIZATION -- mandate_id omitted and this cart has
            no mandate of its own yet). The block is always audited before
            this is raised, except NO_APPROVED_AUTHORIZATION, which can't
            yet be tied to any mandate to audit against.
    """
    if mandate_id is None:
        mandate_id = await _resolve_mandate_id(session, cart_id)

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

    proposal_outcome: ProposalOutcome | None = None

    if not was_already_frozen:
        # Record which mandate froze this cart (Phase 10) so
        # check_mandate_not_reused_by_another_cart can detect this mandate
        # being reused for a second, different cart on a later call.
        cart.mandate_id = mandate_row.id
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

        cart, proposal_outcome = await _run_merchant_advisory(
            session, cart, signed_mandate, mandate_row, public_key_b64, mandate_id, intent_gate_enabled
        )

    cart_response = await to_cart_response(session, cart)
    return CheckoutResponse(
        cart=cart_response, frozen_hash=cart.frozen_hash, frozen_at=cart.frozen_at, proposal=proposal_outcome
    )


async def _run_merchant_advisory(
    session: AsyncSession,
    cart: Cart,
    signed_mandate: SignedMandate,
    mandate_row: Mandate,
    public_key_b64: str,
    mandate_id: str,
    intent_gate_enabled: bool,
) -> tuple[Cart, ProposalOutcome]:
    """
    Run plan.md Section 15 steps 9-13 for one freshly-frozen cart.

    Only ever called once per checkout, immediately after the initial
    freeze in request_checkout() -- never on an idempotent re-validation
    call, since app.policy.engine.run_hard_checks already blocks any second
    request_checkout() on an already-frozen cart with IDEMPOTENCY_DUPLICATE
    before this function would ever be reached again.

    Args:
        session: Active AsyncSession.
        cart: The just-frozen cart (status FROZEN, frozen_hash already set).
        signed_mandate: The mandate authorizing this cart.
        mandate_row: The persisted Mandate row.
        public_key_b64: The merchant's Ed25519 public key.
        mandate_id: Business-facing mandate_id, passed through to the
            Merchant Revenue Agent and used for audit event linkage.
        intent_gate_enabled: See request_checkout()'s docstring -- eval-only,
            never reachable from MCP/REST.

    Returns:
        (cart, proposal_outcome) -- cart is the same row, re-frozen with a
        higher subtotal if a proposal was applied; proposal_outcome always
        describes what happened (even NO_PROPOSAL is reported, never a bare
        None).

    Raises:
        ValidationError: If the final deterministic re-validation (step 13)
            fails -- reached whether or not a proposal was applied. The
            block is always audited (CART_REVALIDATION_BLOCKED) before this
            is raised.
    """
    await append_event(
        session,
        AuditEventInput(
            event_type="MERCHANT_AGENT_STARTED",
            actor_type="MERCHANT_AGENT",
            payload={
                "cart_id": str(cart.id),
                "cart_subtotal_minor": cart.subtotal_minor,
                "mandate_max_amount_minor": signed_mandate.payload.max_amount,
                "allowed_categories": signed_mandate.payload.allowed_categories,
            },
            mandate_id=str(mandate_row.id),
        ),
    )
    agent_result = await run_merchant_agent(session, cart.id, mandate_id)

    if agent_result["final_status"] != ProposalStatus.PROPOSAL_ALLOWED:
        # The agent never got as far as a hard-check-passed proposal to
        # evaluate against the Intent Gate (no viable candidate, every
        # candidate it tried failed the agent's own retries, or the
        # underlying LLM call itself was unavailable -- plan.md Rule 2 fails
        # closed to no proposal rather than guessing). This is Rule 7's
        # "rejected proposal is not a failure" outcome, but until now it
        # left no audit record and no way for the storefront's live
        # conversation to ever close out the Merchant Agent's turn -- it
        # just looked like it never finished.
        await append_event(
            session,
            AuditEventInput(
                event_type="MERCHANT_AGENT_NO_PROPOSAL",
                actor_type="MERCHANT_AGENT",
                payload={"cart_id": str(cart.id), "final_status": agent_result["final_status"].value},
                mandate_id=str(mandate_row.id),
            ),
        )
        proposal_outcome = ProposalOutcome(status=agent_result["final_status"])
    elif intent_gate_enabled:
        proposal_outcome = await _evaluate_proposal_via_intent_gate(
            session, cart, signed_mandate, mandate_row, agent_result["final_proposal"]
        )
    else:
        # Cap-only arm (plan.md Section 19.1): a proposal that already
        # passed AgentPay's own deterministic hard checks
        # (app.services.merchant_service.evaluate_proposal) is applied
        # without also being judged against the buyer's signed *intent* --
        # the spending cap and hard policy still fully apply either way.
        proposal_outcome = await _apply_proposal_without_intent_gate(
            session, cart, mandate_row, agent_result["final_proposal"]
        )

    final_check = await run_final_revalidation(
        session, signed_mandate, mandate_row, public_key_b64, cart, signed_mandate.payload.allowed_categories
    )
    if not final_check.passed:
        await append_event(
            session,
            AuditEventInput(
                event_type="CART_REVALIDATION_BLOCKED",
                actor_type="SYSTEM",
                payload={"cart_id": str(cart.id), "reason_code": final_check.reason_code},
                decision="BLOCK",
                reason_code=final_check.reason_code,
                mandate_id=str(mandate_row.id),
            ),
        )
        raise ValidationError(final_check.reason_code, final_check.reason or "Final re-validation failed.")

    await append_event(
        session,
        AuditEventInput(
            event_type="CART_REVALIDATION_PASSED",
            actor_type="SYSTEM",
            payload={"cart_id": str(cart.id)},
            decision="PASS",
            mandate_id=str(mandate_row.id),
        ),
    )

    return cart, proposal_outcome


async def _evaluate_proposal_via_intent_gate(
    session: AsyncSession,
    cart: Cart,
    signed_mandate: SignedMandate,
    mandate_row: Mandate,
    final_proposal: dict,
) -> ProposalOutcome:
    """
    Run the Intent Gate over one hard-check-passed merchant proposal, and
    apply + re-freeze the cart if it's allowed (plan.md Section 15 steps
    10-12).

    Args:
        session: Active AsyncSession.
        cart: The frozen cart the proposal would modify. Mutated and
            re-frozen in place if the Intent Gate allows the proposal.
        signed_mandate: The mandate authorizing the original cart.
        mandate_row: The persisted Mandate row.
        final_proposal: A MerchantProposal-shaped dict (product_id,
            quantity, reason) from app.agents.merchant.runner.run_merchant_agent.

    Returns:
        ProposalOutcome describing the Intent Gate's verdict. Never raises
        for a BLOCK/ESCALATE outcome -- those are non-terminal (plan.md
        Section 6.2/6.3): the proposal is simply not applied, and the
        original (already hard-check-passed) cart is left untouched for the
        caller's final re-validation pass.
    """
    product = await session.get(Product, uuid.UUID(final_proposal["product_id"]))
    proposal_snapshot = _proposal_snapshot(final_proposal, product)
    mandate_snapshot = _mandate_snapshot(signed_mandate)

    await append_event(
        session,
        AuditEventInput(
            event_type="MERCHANT_PROPOSAL_CREATED",
            actor_type="MERCHANT_AGENT",
            payload={"cart_id": str(cart.id), "proposal": final_proposal, **proposal_snapshot},
            mandate_id=str(mandate_row.id),
        ),
    )

    original_cart = await to_cart_response(session, cart)
    gate_input = _build_intent_gate_input(signed_mandate, original_cart, product, final_proposal)

    await append_event(
        session,
        AuditEventInput(
            event_type="INTENT_CHECK_STARTED",
            actor_type="INTENT_GATE",
            payload={"cart_id": str(cart.id), **proposal_snapshot, **mandate_snapshot},
            mandate_id=str(mandate_row.id),
        ),
    )
    intent_decision = await evaluate_intent(gate_input)

    if intent_decision.decision == IntentDecisionType.ALLOW:
        await append_event(
            session,
            AuditEventInput(
                event_type="INTENT_GATE_ALLOWED",
                actor_type="INTENT_GATE",
                payload={"cart_id": str(cart.id), "confidence": intent_decision.confidence, **proposal_snapshot},
                decision="ALLOW",
                mandate_id=str(mandate_row.id),
            ),
        )

        await _apply_proposal_to_cart(session, cart, mandate_row, final_proposal)

        return ProposalOutcome(
            status=ProposalStatus.PROPOSAL_ALLOWED,
            product_id=final_proposal["product_id"],
            quantity=final_proposal["quantity"],
            reason=intent_decision.reason,
            intent_confidence=intent_decision.confidence,
        )

    if intent_decision.decision == IntentDecisionType.BLOCK:
        await append_event(
            session,
            AuditEventInput(
                event_type="INTENT_GATE_BLOCKED",
                actor_type="INTENT_GATE",
                payload={
                    "cart_id": str(cart.id),
                    "confidence": intent_decision.confidence,
                    "reason": intent_decision.reason,
                    **proposal_snapshot,
                    **mandate_snapshot,
                },
                decision="BLOCK",
                reason_code=intent_decision.reason_code,
                mandate_id=str(mandate_row.id),
            ),
        )
        await append_event(
            session,
            AuditEventInput(
                event_type="PROPOSAL_REJECTED",
                actor_type="SYSTEM",
                payload={"cart_id": str(cart.id), "product_id": final_proposal["product_id"], **proposal_snapshot},
                decision="BLOCK",
                reason_code=intent_decision.reason_code,
                mandate_id=str(mandate_row.id),
            ),
        )
        return ProposalOutcome(
            status=ProposalStatus.PROPOSAL_REJECTED,
            product_id=final_proposal["product_id"],
            quantity=final_proposal["quantity"],
            reason=intent_decision.reason,
            reason_code=intent_decision.reason_code,
            intent_confidence=intent_decision.confidence,
        )

    # ESCALATE: plan.md Section 6.3 -- ambiguous/low-confidence/unavailable
    # intent reasoning fails closed. The proposal is not applied (same
    # outcome as BLOCK for the cart), but recorded distinctly so it surfaces
    # for human review rather than looking like an ordinary rejection.
    await append_event(
        session,
        AuditEventInput(
            event_type="INTENT_ESCALATED",
            actor_type="INTENT_GATE",
            payload={
                "cart_id": str(cart.id),
                "confidence": intent_decision.confidence,
                "reason": intent_decision.reason,
                **proposal_snapshot,
                **mandate_snapshot,
            },
            decision="ESCALATE",
            reason_code=intent_decision.reason_code,
            mandate_id=str(mandate_row.id),
        ),
    )
    return ProposalOutcome(
        status=ProposalStatus.PROPOSAL_ESCALATED,
        product_id=final_proposal["product_id"],
        quantity=final_proposal["quantity"],
        reason=intent_decision.reason,
        reason_code=intent_decision.reason_code,
        intent_confidence=intent_decision.confidence,
    )


async def _apply_proposal_without_intent_gate(
    session: AsyncSession, cart: Cart, mandate_row: Mandate, final_proposal: dict
) -> ProposalOutcome:
    """
    Cap-only arm (plan.md Section 19.1): apply a hard-check-passed merchant
    proposal directly, without consulting the Intent Gate.

    Args:
        session: Active AsyncSession.
        cart: The frozen cart to modify. Mutated and re-frozen in place.
        mandate_row: The persisted Mandate row.
        final_proposal: A MerchantProposal-shaped dict (product_id,
            quantity, reason) from run_merchant_agent.

    Returns:
        ProposalOutcome with status=PROPOSAL_ALLOWED and no
        intent_confidence (the Intent Gate was never consulted). Only
        MERCHANT_PROPOSAL_CREATED and CART_FROZEN are audited -- no
        INTENT_GATE_* event exists for this proposal, so the audit trail
        itself makes clear it was never judged against signed intent.
    """
    product = await session.get(Product, uuid.UUID(final_proposal["product_id"]))
    await append_event(
        session,
        AuditEventInput(
            event_type="MERCHANT_PROPOSAL_CREATED",
            actor_type="MERCHANT_AGENT",
            payload={
                "cart_id": str(cart.id),
                "proposal": final_proposal,
                "intent_gate_enabled": False,
                **_proposal_snapshot(final_proposal, product),
            },
            mandate_id=str(mandate_row.id),
        ),
    )
    await _apply_proposal_to_cart(session, cart, mandate_row, final_proposal)
    return ProposalOutcome(
        status=ProposalStatus.PROPOSAL_ALLOWED,
        product_id=final_proposal["product_id"],
        quantity=final_proposal["quantity"],
        reason=final_proposal["reason"],
    )


async def _apply_proposal_to_cart(
    session: AsyncSession, cart: Cart, mandate_row: Mandate, final_proposal: dict
) -> None:
    """
    Apply an approved merchant proposal to the cart and re-freeze it
    (plan.md Section 15 step 12).

    Shared by the Intent-Gate-ALLOW path and the Cap-only arm's auto-apply
    path -- the mechanics of "merge the item in, re-freeze, audit
    CART_FROZEN" are identical either way; only how a proposal got approved
    differs (handled by each caller before this is invoked).
    """
    product = await session.get(Product, uuid.UUID(final_proposal["product_id"]))
    await carts_service.merge_item_into_cart(session, cart, product, final_proposal["quantity"])
    await freeze_cart(session, cart)
    await append_event(
        session,
        AuditEventInput(
            event_type="CART_FROZEN",
            actor_type="SYSTEM",
            payload={"cart_id": str(cart.id), "frozen_hash": cart.frozen_hash, "modified_by_proposal": True},
            mandate_id=str(mandate_row.id),
        ),
    )


def _proposal_snapshot(proposal: dict, product: Product) -> dict:
    """
    A self-contained snapshot of one merchant proposal (product name/
    category/price, quantity, reason) for the audit payload -- so a later
    "why was this blocked" view (the storefront's expandable AI Activity
    evidence) never needs a second query to explain a rejected proposal,
    since the product itself is never added to the cart when rejected.
    """
    return {
        "proposed_product_name": product.name,
        "proposed_category": product.category,
        "proposed_price_minor": product.price_minor,
        "proposed_quantity": proposal["quantity"],
        "proposed_reason": proposal["reason"],
    }


def _mandate_snapshot(signed_mandate: SignedMandate) -> dict:
    """A self-contained snapshot of the authorizing mandate's limits, for the same evidence view as _proposal_snapshot."""
    return {
        "mandate_max_amount_minor": signed_mandate.payload.max_amount,
        "mandate_allowed_categories": signed_mandate.payload.allowed_categories,
        "mandate_allow_addons": signed_mandate.payload.allow_addons,
    }


def _build_intent_gate_input(
    signed_mandate: SignedMandate, original_cart: CartResponse, product: Product, proposal: dict
) -> IntentGateInput:
    """
    Render the mandate's signed intent, the original (pre-proposal) cart,
    and a merchant proposal into the Intent Gate's input shape (plan.md
    Section 14.1).

    original_buyer_request is synthesized from the mandate's signed
    MandateIntent, since AgentPay stores no separate raw buyer utterance --
    the signed intent IS the trustworthy record of what the buyer asked for
    (plan.md Rule 3).
    """
    intent = signed_mandate.payload.intent
    if original_cart.items:
        cart_summary = ", ".join(
            f"{item.quantity}x {item.product_name} ({item.line_total_minor} {original_cart.currency} minor units)"
            for item in original_cart.items
        )
    else:
        cart_summary = "(empty cart)"

    original_buyer_request = intent.product_type + (f". {intent.notes}" if intent.notes else "")
    proposed_modification = (
        f"Add {proposal['quantity']}x {product.name} "
        f"({product.price_minor} {original_cart.currency} minor units)"
    )
    return IntentGateInput(
        original_buyer_request=original_buyer_request,
        signed_intent_product_type=intent.product_type,
        signed_intent_notes=intent.notes,
        original_cart_summary=cart_summary,
        proposed_modification=proposed_modification,
        merchant_proposal_reason=proposal["reason"],
    )
