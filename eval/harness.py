"""
Purpose: The AgentPay evaluation harness (plan.md Section 19 / final.md
Phase 9) -- drives real backend code (mandate creation, cart creation,
app.services.checkout_service.request_checkout()) through a frozen buyer
persona panel, for both the Cap-only and Intent-aware arms.

This is NOT a parallel reimplementation of checkout logic: every run calls
the exact same request_checkout() used by the REST API and the MCP tools
Claude drives, only toggling its eval-only `intent_gate_enabled` keyword
(see app.services.checkout_service.request_checkout's docstring for why
that argument exists and why it can never be reached by a real buyer).

Claude (the external buyer agent) is not built by this project, so a real
interactive buyer can't drive automated, repeatable eval runs. Each persona
in personas.json is instead a frozen, deterministic script (plan.md Section
19.2: "freeze the prompts before either arm runs" -- freezing here means
freezing the *translation* from a persona's prompt into concrete mandate
fields, starting cart, and completion rule, not just the prose):
  - `mandate`: the signed intent/constraints this persona's real user would
    have authorized.
  - `starting_cart_items`: what the buyer agent has already added to the
    cart before calling request_checkout() -- identical starting carts
    across arms, per plan.md Section 19.1.
  - `completion_rule`: a simple, deterministic rule for whether this
    persona would go on to complete_purchase() or abandon, given the
    checkout result. No LLM is involved in this decision -- it exists
    purely so a persona's reaction to a merchant proposal is repeatable
    run-to-run, which a live LLM buyer would not be.

Requires the real UrbanNest catalog to already be seeded
(scripts/seed_database.py) -- this harness reuses that merchant, its
products (by SKU), and its demo user rather than inventing a parallel
catalog, so eval runs exercise the exact same data judges see in the demo.

Scope note: this harness measures AgentPay's *authorization* decision --
would the transaction be approved, and at what amount -- via
request_checkout() only. It does not create a real Razorpay Test Mode order
per run (that flow is already covered by Phase 4/5's dedicated tests); this
keeps eval runs fast and side-effect-free outside the database. Metrics
computation (ceiling drift, abandonment rate, escalation rate, the
adversarial suite) is Phase 10's job, built on top of this harness's output
records, not part of this module.
"""
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.carts.service import add_cart_item, create_cart  # noqa: E402
from app.db.models.merchant import Merchant  # noqa: E402
from app.db.models.product import Product  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.mandates.service import create_mandate  # noqa: E402
from app.schemas.checkout import CheckoutResponse  # noqa: E402
from app.schemas.common import ValidationError  # noqa: E402
from app.schemas.mandate import MandateIntent, MandatePayload  # noqa: E402
from app.schemas.proposal import ProposalStatus  # noqa: E402
from app.services.checkout_service import request_checkout  # noqa: E402

PERSONAS_PATH = Path(__file__).resolve().parent / "personas.json"
URBANNEST_SLUG = "urbannest"
DEMO_USER_EMAIL = "demo@agentpay.test"


class SeedDataMissingError(RuntimeError):
    """Raised when the UrbanNest merchant/user isn't seeded yet. Run scripts/seed_database.py first."""


@dataclass
class PersonaRunResult:
    """
    One persona's outcome under one arm -- the harness's output record
    (plan.md Section 22's per-case fields, adapted for the two-arm
    comparison rather than the adversarial suite specifically).
    """

    persona_id: str
    arm: str  # "cap_only" | "intent_aware"
    category: str  # "normal" | "adversarial"
    model_invoked: bool
    hard_check_blocked: bool
    hard_check_reason_code: str | None = None
    proposal_status: str | None = None
    proposal_reason_code: str | None = None
    starting_subtotal_minor: int | None = None
    approved_subtotal_minor: int | None = None
    completed: bool | None = None  # None when not applicable (e.g. hard-blocked adversarial case)
    completed_spend_minor: int | None = None  # approved_subtotal_minor if completed, else None
    matched_expectation: bool | None = None  # for adversarial cases: did the block match expected_hard_check_block


def load_personas() -> list[dict]:
    """Load the frozen persona panel from personas.json."""
    with open(PERSONAS_PATH, encoding="utf-8") as f:
        return json.load(f)["personas"]


async def _get_urbannest_context(session: AsyncSession) -> tuple[Merchant, User]:
    """Fetch the seeded UrbanNest merchant and demo user, or raise a clear, actionable error."""
    merchant_result = await session.execute(select(Merchant).where(Merchant.slug == URBANNEST_SLUG))
    merchant = merchant_result.scalar_one_or_none()
    user_result = await session.execute(select(User).where(User.email == DEMO_USER_EMAIL))
    user = user_result.scalar_one_or_none()
    if merchant is None or user is None:
        raise SeedDataMissingError(
            "UrbanNest merchant/demo user not found. Run `uv run python scripts/seed_database.py` "
            "(from the repo root or backend/) before running the evaluation harness."
        )
    return merchant, user


async def _get_product_by_sku(session: AsyncSession, sku: str) -> Product:
    result = await session.execute(select(Product).where(Product.sku == sku))
    product = result.scalar_one_or_none()
    if product is None:
        raise SeedDataMissingError(f"Product SKU '{sku}' not found -- run scripts/seed_database.py first.")
    return product


def _mandate_payload_for(persona: dict, merchant_id: uuid.UUID, run_suffix: str) -> MandatePayload:
    """Build this run's unique, signed mandate payload from a persona's frozen mandate fields."""
    m = persona["mandate"]
    return MandatePayload(
        mandate_id=f"EVAL-{persona['persona_id']}-{run_suffix}",
        merchant_id=str(merchant_id),
        currency="INR",
        max_amount=m["max_amount_minor"],
        allowed_categories=m["allowed_categories"],
        allow_addons=m["allow_addons"],
        delivery_requirement=m["delivery_requirement"],
        single_use=m["single_use"],
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        intent=MandateIntent(product_type=m["product_type"], notes=m.get("notes")),
    )


def _apply_completion_rule(persona: dict, checkout: CheckoutResponse, starting_subtotal: int) -> bool | None:
    """
    Decide whether this persona would complete_purchase() or abandon, given
    the checkout result -- a deterministic stand-in for the buyer decision a
    real Claude conversation would otherwise make (see module docstring).
    """
    rule = persona.get("completion_rule")
    if rule is None:
        return None
    rule_type = rule["type"]
    if rule_type == "always_completes":
        return True
    if rule_type == "abandon_if_cart_modified":
        proposal_applied = checkout.proposal is not None and checkout.proposal.status == ProposalStatus.PROPOSAL_ALLOWED
        return not proposal_applied
    raise ValueError(f"Unknown completion_rule type: {rule_type!r}")


async def run_persona(persona: dict, *, arm: str, intent_gate_enabled: bool) -> PersonaRunResult:
    """
    Run one persona through one arm: create its mandate and starting cart,
    call request_checkout(), and score the result against the persona's
    frozen expectations.

    Args:
        persona: One entry from personas.json.
        arm: Label for the result record ("cap_only" or "intent_aware") --
            purely descriptive; intent_gate_enabled is what actually
            controls behavior.
        intent_gate_enabled: Passed straight through to request_checkout().

    Returns:
        PersonaRunResult describing what happened.
    """
    factory = get_session_factory()
    run_suffix = uuid.uuid4().hex[:8]

    async with factory() as session:
        merchant, user = await _get_urbannest_context(session)

        payload = _mandate_payload_for(persona, merchant.id, run_suffix)
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

        cart = await create_cart(session, user.id, merchant.id, "INR")
        starting_subtotal = 0
        for item in persona["starting_cart_items"]:
            product = await _get_product_by_sku(session, item["sku"])
            cart = await add_cart_item(session, uuid.UUID(cart.cart_id), product.id, item["quantity"])
            starting_subtotal = cart.subtotal_minor
        await session.commit()

        # model_invoked is derived from the code path actually taken, not
        # instrumentation: the Merchant Revenue Agent (and therefore Gemini)
        # is only ever reached after hard checks pass (plan.md Rule 2).
        try:
            checkout = await request_checkout(
                session, uuid.UUID(cart.cart_id), payload.mandate_id, intent_gate_enabled=intent_gate_enabled
            )
            await session.commit()
        except ValidationError as exc:
            expected = persona.get("expected_hard_check_block")
            matched = expected is not None and expected["reason_code"] == exc.reason_code
            return PersonaRunResult(
                persona_id=persona["persona_id"],
                arm=arm,
                category=persona["category"],
                model_invoked=False,
                hard_check_blocked=True,
                hard_check_reason_code=exc.reason_code,
                starting_subtotal_minor=starting_subtotal,
                matched_expectation=matched,
            )

        completed = _apply_completion_rule(persona, checkout, starting_subtotal)
        approved_subtotal = checkout.cart.subtotal_minor
        return PersonaRunResult(
            persona_id=persona["persona_id"],
            arm=arm,
            category=persona["category"],
            model_invoked=True,
            hard_check_blocked=False,
            proposal_status=checkout.proposal.status.value if checkout.proposal else None,
            proposal_reason_code=checkout.proposal.reason_code if checkout.proposal else None,
            starting_subtotal_minor=starting_subtotal,
            approved_subtotal_minor=approved_subtotal,
            completed=completed,
            completed_spend_minor=approved_subtotal if completed else None,
            matched_expectation=persona.get("expected_hard_check_block") is None,
        )


async def run_arm(arm: str, *, intent_gate_enabled: bool) -> list[PersonaRunResult]:
    """Run every persona in personas.json through one arm."""
    personas = load_personas()
    return [await run_persona(persona, arm=arm, intent_gate_enabled=intent_gate_enabled) for persona in personas]


def results_to_dicts(results: list[PersonaRunResult]) -> list[dict]:
    """Convert PersonaRunResult records into plain JSON-serializable dicts."""
    return [
        {k: v for k, v in vars(r).items()}
        for r in results
    ]
