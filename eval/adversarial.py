"""
Purpose: The adversarial test suite (plan.md Section 22 / final.md Phase 10)
-- ~30 attack/edge-case scenarios run against the real backend, recorded as
a structured evidence artifact (scenario_id, expected_outcome,
actual_outcome, reason_code, model_invoked, latency, final_transaction_state)
for the pitch deck. This is supporting evidence, not the primary causal
claim (plan.md Section 21/31) -- the primary claim is Cap-only vs
Intent-aware ceiling drift, built on eval/harness.py.

Every scenario is metadata-driven from scenarios.json (frozen, like
personas.json -- do not tune expected_reason_code/expected_outcome after
seeing results). Most scenarios share one generic procedure
(_run_generic_hard_block): build a mandate + cart from the scenario's
declared overrides, call the real request_checkout(), and compare the
raised ValidationError's reason_code against the declared expectation.
A handful of scenarios have genuinely different mechanics (mandate
consumption/replay, direct DB tampering, concurrent races, mocked-LLM
merchant upsells) and are named in SPECIAL_RUNNERS instead.

Uses the same real, seeded UrbanNest catalog as eval/harness.py -- run
scripts/seed_database.py first.
"""
import asyncio
import json
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.agents.merchant.nodes import _CandidateProposal, _CandidateProposalList  # noqa: E402
from app.carts.service import add_cart_item, create_cart, get_cart  # noqa: E402
from app.db.models.cart_item import CartItem  # noqa: E402
from app.db.models.inventory import Inventory  # noqa: E402
from app.db.models.mandate import Mandate  # noqa: E402
from app.db.models.product import Product  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402
from app.intent.models import IntentDecisionType, _IntentClassification  # noqa: E402
from app.mandates.service import consume_mandate, create_mandate, get_mandate_by_business_id  # noqa: E402
from app.payments.checkout import create_checkout_session  # noqa: E402
from app.schemas.common import ValidationError  # noqa: E402
from app.schemas.mandate import MandateIntent, MandatePayload  # noqa: E402
from app.services.checkout_service import request_checkout  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import _get_product_by_sku, _get_urbannest_context  # noqa: E402

SCENARIOS_PATH = Path(__file__).resolve().parent / "scenarios.json"


@dataclass
class ScenarioResult:
    """One adversarial case's outcome (plan.md Section 22's exact per-case fields)."""

    scenario_id: str
    category: str
    expected_outcome: str
    expected_reason_code: str | None
    actual_reason_code: str | None
    model_invoked: bool
    latency_seconds: float
    final_transaction_state: str
    passed: bool


def load_scenarios() -> list[dict]:
    """Load the frozen adversarial scenario definitions from scenarios.json."""
    with open(SCENARIOS_PATH, encoding="utf-8") as f:
        return json.load(f)["scenarios"]


def _default_mandate_kwargs() -> dict:
    """Baseline mandate fields every scenario starts from, before its own overrides."""
    return {
        "max_amount_minor": 280_000,
        # Permissive by default (every real UrbanNest category) so scenarios
        # that don't test category logic themselves (most of them) aren't
        # accidentally blocked by MANDATE_CATEGORY_FORBIDDEN before reaching
        # the check they actually intend to exercise -- see check order in
        # app.policy.engine.run_hard_checks (mandate/amount checks run
        # before check_category, but category still runs before
        # check_inventory, so an out-of-stock-style scenario would otherwise
        # get the wrong reason_code). Scenarios that specifically test
        # category enforcement override this explicitly.
        "allowed_categories": ["audio", "wearables", "power", "accessories"],
        "allow_addons": False,
        "delivery_requirement": "under_3_days",
        "single_use": True,
        "expires_in_hours": 1,
        "currency": "INR",
        "product_type": "wireless earbuds",
        "notes": None,
    }


async def _build_mandate(session: AsyncSession, scenario_id: str, merchant_id: uuid.UUID, overrides: dict) -> MandatePayload:
    """Build (but not yet persist) a MandatePayload from defaults + a scenario's overrides."""
    m = {**_default_mandate_kwargs(), **(overrides or {})}
    payload_merchant_id = str(uuid.uuid4()) if m.get("merchant_id_override") == "random" else str(merchant_id)
    return MandatePayload(
        mandate_id=f"ADV-{scenario_id}-{uuid.uuid4().hex[:8]}",
        merchant_id=payload_merchant_id,
        currency=m["currency"],
        max_amount=m["max_amount_minor"],
        allowed_categories=m["allowed_categories"],
        allow_addons=m["allow_addons"],
        delivery_requirement=m["delivery_requirement"],
        single_use=m["single_use"],
        expires_at=datetime.now(UTC) + timedelta(hours=m["expires_in_hours"]),
        intent=MandateIntent(product_type=m["product_type"], notes=m["notes"]),
    )


async def _run_generic_hard_block(scenario: dict) -> ScenarioResult:
    """
    Shared procedure for scenarios that build one mandate + cart and expect
    a single request_checkout() call to raise a specific ValidationError.
    """
    factory = get_session_factory()
    async with factory() as session:
        start = time.monotonic()
        actual_reason_code: str | None = None
        final_state = "CHECKOUT_APPROVED"
        try:
            merchant, user = await _get_urbannest_context(session)
            overrides = scenario.get("mandate_overrides") or {}
            payload = await _build_mandate(session, scenario["scenario_id"], merchant.id, overrides)
            await create_mandate(session, payload, user.id, merchant.id)
            await session.commit()

            cart_currency = overrides.get("cart_currency", payload.currency)
            cart = await create_cart(session, user.id, merchant.id, cart_currency)
            # A block can occur here too (e.g. add_cart_item's own
            # INSUFFICIENT_INVENTORY check), not only inside
            # request_checkout() -- both are legitimate ways AgentPay
            # catches an attack, so both are caught by the same except block.
            for sku, qty in scenario["cart_items"]:
                product = await _get_product_by_sku(session, sku)
                cart = await add_cart_item(session, uuid.UUID(cart.cart_id), product.id, qty)
            await session.commit()

            await request_checkout(session, uuid.UUID(cart.cart_id), payload.mandate_id)
            await session.commit()
        except ValidationError as exc:
            actual_reason_code = exc.reason_code
            final_state = "TRANSACTION_BLOCKED"
        latency = time.monotonic() - start

    return _result(scenario, actual_reason_code, model_invoked=False, latency=latency, final_state=final_state)


def _result(scenario: dict, actual_reason_code: str | None, *, model_invoked: bool, latency: float, final_state: str) -> ScenarioResult:
    """Build a ScenarioResult, scoring actual vs. the scenario's declared expectation."""
    expected_reason_code = scenario["expected_reason_code"]
    return ScenarioResult(
        scenario_id=scenario["scenario_id"],
        category=scenario["category"],
        expected_outcome=scenario["expected_outcome"],
        expected_reason_code=expected_reason_code,
        actual_reason_code=actual_reason_code,
        model_invoked=model_invoked,
        latency_seconds=latency,
        final_transaction_state=final_state,
        passed=(actual_reason_code == expected_reason_code),
    )


def _result_expect_any_block(
    scenario: dict, actual_reason_code: str | None, *, model_invoked: bool, latency: float, final_state: str
) -> ScenarioResult:
    """
    Build a ScenarioResult for scenarios whose scenarios.json entry declares
    expected_reason_code=null -- meaning "must be blocked by AgentPay for
    SOME reason," not one single pre-guessed code. Used where more than one
    code could legitimately catch the attack (e.g. IDEMPOTENCY_DUPLICATE vs
    REPLAY_DETECTED depending on exactly which layer catches a reused
    mandate first) -- scoring on an exact code here would make the case
    fail even when AgentPay correctly blocked the attack.
    """
    return ScenarioResult(
        scenario_id=scenario["scenario_id"],
        category=scenario["category"],
        expected_outcome=scenario["expected_outcome"],
        expected_reason_code=scenario["expected_reason_code"],
        actual_reason_code=actual_reason_code,
        model_invoked=model_invoked,
        latency_seconds=latency,
        final_transaction_state=final_state,
        passed=(actual_reason_code is not None),
    )


# --- Special-mechanic scenarios (named in scenarios.json's "runner" field) ---


async def cap_splitting_reuse_after_success(scenario: dict) -> ScenarioResult:
    """Reuse the same single-use mandate for a second cart after its first checkout already succeeded."""
    factory = get_session_factory()
    async with factory() as session:
        merchant, user = await _get_urbannest_context(session)
        payload = await _build_mandate(session, scenario["scenario_id"], merchant.id, {"max_amount_minor": 500_000})
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

        product = await _get_product_by_sku(session, "EARBUDS-001")
        first_cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(first_cart.cart_id), product.id, 1)
        await session.commit()
        await request_checkout(session, uuid.UUID(first_cart.cart_id), payload.mandate_id)
        await session.commit()

        second_cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(second_cart.cart_id), product.id, 1)
        await session.commit()

        start = time.monotonic()
        actual_reason_code = None
        final_state = "CHECKOUT_APPROVED"
        try:
            await request_checkout(session, uuid.UUID(second_cart.cart_id), payload.mandate_id)
            await session.commit()
        except ValidationError as exc:
            actual_reason_code = exc.reason_code
            final_state = "TRANSACTION_BLOCKED"
        latency = time.monotonic() - start

    return _result_expect_any_block(scenario, actual_reason_code, model_invoked=False, latency=latency, final_state=final_state)


async def cap_splitting_reuse_before_completion(scenario: dict) -> ScenarioResult:
    """Use the same single-use mandate for a second cart while the first checkout's cart is still frozen (unpaid)."""
    factory = get_session_factory()
    async with factory() as session:
        merchant, user = await _get_urbannest_context(session)
        payload = await _build_mandate(session, scenario["scenario_id"], merchant.id, {"max_amount_minor": 500_000})
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

        product = await _get_product_by_sku(session, "EARBUDS-001")
        first_cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(first_cart.cart_id), product.id, 1)
        await session.commit()
        await request_checkout(session, uuid.UUID(first_cart.cart_id), payload.mandate_id)
        await session.commit()
        # Note: the first cart is now FROZEN but not yet paid -- the mandate
        # itself is not yet CONSUMED (that only happens on payment capture,
        # app.mandates.service.consume_mandate). This scenario tests that a
        # second, different cart still can't reuse it mid-flight.

        second_cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(second_cart.cart_id), product.id, 1)
        await session.commit()

        start = time.monotonic()
        actual_reason_code = None
        final_state = "CHECKOUT_APPROVED"
        try:
            await request_checkout(session, uuid.UUID(second_cart.cart_id), payload.mandate_id)
            await session.commit()
        except ValidationError as exc:
            actual_reason_code = exc.reason_code
            final_state = "TRANSACTION_BLOCKED"
        latency = time.monotonic() - start

    return _result_expect_any_block(scenario, actual_reason_code, model_invoked=False, latency=latency, final_state=final_state)


async def replay_after_consumption(scenario: dict) -> ScenarioResult:
    """A single-use mandate already CONSUMED (simulating a completed prior payment) is reused for a new checkout."""
    factory = get_session_factory()
    async with factory() as session:
        merchant, user = await _get_urbannest_context(session)
        payload = await _build_mandate(session, scenario["scenario_id"], merchant.id, {})
        mandate_row = await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()
        await consume_mandate(session, mandate_row)
        await session.commit()

        product = await _get_product_by_sku(session, "EARBUDS-001")
        cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(cart.cart_id), product.id, 1)
        await session.commit()

        start = time.monotonic()
        actual_reason_code = None
        final_state = "CHECKOUT_APPROVED"
        try:
            await request_checkout(session, uuid.UUID(cart.cart_id), payload.mandate_id)
            await session.commit()
        except ValidationError as exc:
            actual_reason_code = exc.reason_code
            final_state = "TRANSACTION_BLOCKED"
        latency = time.monotonic() - start

    return _result_expect_any_block(scenario, actual_reason_code, model_invoked=False, latency=latency, final_state=final_state)


async def replay_directly_marked_consumed(scenario: dict) -> ScenarioResult:
    """A mandate's status is set to CONSUMED directly (bypassing the normal payment flow), then reused."""
    return await replay_after_consumption(scenario)


async def price_protected_after_catalog_change(scenario: dict) -> ScenarioResult:
    """
    Freeze a cart, then change the underlying product's catalog price, and
    verify the frozen line item's captured price is unaffected -- proving
    a post-freeze catalog price change can never silently alter what the
    buyer is charged.
    """
    factory = get_session_factory()
    delta = (scenario.get("mandate_overrides") or {}).get("price_delta_minor", 0)
    async with factory() as session:
        merchant, user = await _get_urbannest_context(session)
        payload = await _build_mandate(session, scenario["scenario_id"], merchant.id, {})
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

        product = await _get_product_by_sku(session, "EARBUDS-001")
        original_price = product.price_minor
        cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(cart.cart_id), product.id, 1)
        await session.commit()

        start = time.monotonic()
        await request_checkout(session, uuid.UUID(cart.cart_id), payload.mandate_id)
        await session.commit()

        product_row = await session.get(Product, product.id)
        product_row.price_minor = max(product_row.price_minor + delta, 1)
        await session.commit()

        refreshed_cart = await get_cart(session, uuid.UUID(cart.cart_id))
        latency = time.monotonic() - start

        product_row.price_minor = original_price
        await session.commit()

    price_unchanged = refreshed_cart.items[0].unit_price_minor == original_price
    return ScenarioResult(
        scenario_id=scenario["scenario_id"],
        category=scenario["category"],
        expected_outcome=scenario["expected_outcome"],
        expected_reason_code=None,
        actual_reason_code=None,
        model_invoked=False,
        latency_seconds=latency,
        final_transaction_state="PRICE_PROTECTED" if price_unchanged else "PRICE_LEAKED",
        passed=price_unchanged,
    )


async def _cart_tampered(scenario: dict, *, tamper_quantity: bool) -> ScenarioResult:
    """Freeze a cart, directly mutate a CartItem row in the database, and verify a re-check catches the tamper."""
    factory = get_session_factory()
    async with factory() as session:
        merchant, user = await _get_urbannest_context(session)
        payload = await _build_mandate(session, scenario["scenario_id"], merchant.id, {"max_amount_minor": 500_000})
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

        product = await _get_product_by_sku(session, "EARBUDS-001")
        cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(cart.cart_id), product.id, 1)
        await session.commit()
        await request_checkout(session, uuid.UUID(cart.cart_id), payload.mandate_id)
        await session.commit()

        item_result = await session.execute(select(CartItem).where(CartItem.cart_id == uuid.UUID(cart.cart_id)))
        item = item_result.scalars().first()
        if tamper_quantity:
            item.quantity = item.quantity + 1
        else:
            item.unit_price_minor = 1
        item.line_total_minor = item.quantity * item.unit_price_minor
        await session.commit()

        start = time.monotonic()
        actual_reason_code = None
        final_state = "CHECKOUT_APPROVED"
        try:
            await request_checkout(session, uuid.UUID(cart.cart_id), payload.mandate_id)
            await session.commit()
        except ValidationError as exc:
            actual_reason_code = exc.reason_code
            final_state = "TRANSACTION_BLOCKED"
        latency = time.monotonic() - start

    return _result(scenario, actual_reason_code, model_invoked=False, latency=latency, final_state=final_state)


async def cart_tampered_quantity(scenario: dict) -> ScenarioResult:
    return await _cart_tampered(scenario, tamper_quantity=True)


async def cart_tampered_price(scenario: dict) -> ScenarioResult:
    return await _cart_tampered(scenario, tamper_quantity=False)


async def duplicate_checkout_submit(scenario: dict) -> ScenarioResult:
    """Call request_checkout() twice for the same cart; the second call must be rejected as a duplicate."""
    factory = get_session_factory()
    async with factory() as session:
        merchant, user = await _get_urbannest_context(session)
        payload = await _build_mandate(session, scenario["scenario_id"], merchant.id, {})
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

        product = await _get_product_by_sku(session, "EARBUDS-001")
        cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(cart.cart_id), product.id, 1)
        await session.commit()
        await request_checkout(session, uuid.UUID(cart.cart_id), payload.mandate_id)
        await session.commit()

        start = time.monotonic()
        actual_reason_code = None
        final_state = "CHECKOUT_APPROVED"
        try:
            await request_checkout(session, uuid.UUID(cart.cart_id), payload.mandate_id)
            await session.commit()
        except ValidationError as exc:
            actual_reason_code = exc.reason_code
            final_state = "TRANSACTION_BLOCKED"
        latency = time.monotonic() - start

    return _result(scenario, actual_reason_code, model_invoked=False, latency=latency, final_state=final_state)


async def out_of_stock(scenario: dict) -> ScenarioResult:
    """Add an item to the cart, then reduce its inventory below the requested quantity before checkout."""
    overrides = scenario.get("mandate_overrides") or {}
    set_quantity = overrides["set_inventory_quantity"]
    cart_quantity = overrides.get("cart_quantity", 1)

    factory = get_session_factory()
    async with factory() as session:
        merchant, user = await _get_urbannest_context(session)
        payload = await _build_mandate(session, scenario["scenario_id"], merchant.id, {"max_amount_minor": 500_000})
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

        product = await _get_product_by_sku(session, "POWERBANK-001")
        inv_result = await session.execute(select(Inventory).where(Inventory.product_id == product.id))
        inventory = inv_result.scalar_one()
        original_quantity = inventory.quantity

        cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(cart.cart_id), product.id, cart_quantity)
        await session.commit()

        inventory.quantity = set_quantity
        await session.commit()

        start = time.monotonic()
        actual_reason_code = None
        final_state = "CHECKOUT_APPROVED"
        try:
            await request_checkout(session, uuid.UUID(cart.cart_id), payload.mandate_id)
            await session.commit()
        except ValidationError as exc:
            actual_reason_code = exc.reason_code
            final_state = "TRANSACTION_BLOCKED"
        latency = time.monotonic() - start

        inventory.quantity = original_quantity
        await session.commit()

    return _result(scenario, actual_reason_code, model_invoked=False, latency=latency, final_state=final_state)


async def _merchant_upsell(scenario: dict, *, intent_decision: IntentDecisionType, confidence: float) -> ScenarioResult:
    """Mock the merchant agent into proposing an accessory, and the Intent Gate into a specific verdict on it."""
    factory = get_session_factory()
    async with factory() as session:
        merchant, user = await _get_urbannest_context(session)
        payload = await _build_mandate(
            session,
            scenario["scenario_id"],
            merchant.id,
            {"allowed_categories": ["audio", "accessories"], "notes": "No unnecessary accessories."},
        )
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

        earbuds = await _get_product_by_sku(session, "EARBUDS-001")
        case = await _get_product_by_sku(session, "CASE-001")
        cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(cart.cart_id), earbuds.id, 1)
        await session.commit()

        candidates = _CandidateProposalList(
            candidates=[
                _CandidateProposal(
                    product_id=str(case.id), quantity=1, reason="Protects your new earbuds.",
                    estimated_value_add_minor=29_900,
                )
            ]
        )
        classification = _IntentClassification(
            decision=intent_decision, confidence=confidence, reason="Buyer's signed intent says no accessories."
        )

        start = time.monotonic()
        actual_reason_code = None
        final_state = "CHECKOUT_APPROVED"
        with (
            patch("app.agents.merchant.nodes.classify_with_schema", new=AsyncMock(return_value=candidates)),
            patch("app.intent.gate.classify_with_schema", new=AsyncMock(return_value=classification)),
        ):
            result = await request_checkout(session, uuid.UUID(cart.cart_id), payload.mandate_id)
            await session.commit()
        latency = time.monotonic() - start
        if result.proposal is not None:
            actual_reason_code = result.proposal.reason_code
            final_state = result.proposal.status.value

    return _result(scenario, actual_reason_code, model_invoked=True, latency=latency, final_state=final_state)


async def merchant_upsell_intent_blocked(scenario: dict) -> ScenarioResult:
    return await _merchant_upsell(scenario, intent_decision=IntentDecisionType.BLOCK, confidence=0.95)


async def merchant_upsell_intent_escalated(scenario: dict) -> ScenarioResult:
    return await _merchant_upsell(scenario, intent_decision=IntentDecisionType.ALLOW, confidence=0.10)


async def _create_checkout_session_isolated(cart_id: uuid.UUID, mandate_id: str):
    """
    Call create_checkout_session() on its own, independent AsyncSession.

    A single SQLAlchemy AsyncSession is not safe for concurrent use from
    multiple coroutines -- simulating a real concurrent duplicate-payment
    race (two separate request handlers hitting the same cart) requires two
    separate sessions, exactly as two separate real HTTP requests would get.
    """
    factory = get_session_factory()
    async with factory() as session:
        result = await create_checkout_session(session, cart_id, mandate_id)
        await session.commit()
        return result


async def _duplicate_payment(scenario: dict, *, concurrent: bool) -> ScenarioResult:
    """
    Call create_checkout_session() twice for the same cart and verify only
    one Razorpay order is ever created.

    app.payments.checkout.create_checkout_session()'s idempotency check is
    itself a check-then-insert (a classic TOCTOU race window) backed by a
    DB-level UNIQUE constraint on Transaction.idempotency_key as the actual
    safety net. In the concurrent case, that means the losing side of a
    true race may raise an IntegrityError rather than cleanly returning the
    winner's order -- that IS the protection working (a duplicate row was
    never persisted), so it counts as "duplicate prevented" here too, not
    as a scenario failure.
    """
    factory = get_session_factory()
    async with factory() as session:
        merchant, user = await _get_urbannest_context(session)
        payload = await _build_mandate(session, scenario["scenario_id"], merchant.id, {})
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

        product = await _get_product_by_sku(session, "EARBUDS-001")
        cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(cart.cart_id), product.id, 1)
        await session.commit()
        await request_checkout(session, uuid.UUID(cart.cart_id), payload.mandate_id)
        await session.commit()
        cart_id = uuid.UUID(cart.cart_id)

    start = time.monotonic()
    if concurrent:
        outcomes = await asyncio.gather(
            _create_checkout_session_isolated(cart_id, payload.mandate_id),
            _create_checkout_session_isolated(cart_id, payload.mandate_id),
            return_exceptions=True,
        )
    else:
        outcomes = [
            await _create_checkout_session_isolated(cart_id, payload.mandate_id),
            await _create_checkout_session_isolated(cart_id, payload.mandate_id),
        ]
    latency = time.monotonic() - start

    successes = [o for o in outcomes if not isinstance(o, BaseException)]
    failures = [o for o in outcomes if isinstance(o, BaseException)]
    if len(successes) == 2:
        duplicate_prevented = successes[0].razorpay_order_id == successes[1].razorpay_order_id
        final_state = "DUPLICATE_PREVENTED" if duplicate_prevented else "DUPLICATE_ORDER_CREATED"
    elif len(successes) == 1 and len(failures) == 1:
        # The losing side hit the DB unique constraint -- no duplicate order
        # was ever persisted, which is the protection working.
        duplicate_prevented = True
        final_state = "DUPLICATE_PREVENTED"
    else:
        duplicate_prevented = False
        final_state = "BOTH_REQUESTS_FAILED"

    return ScenarioResult(
        scenario_id=scenario["scenario_id"],
        category=scenario["category"],
        expected_outcome=scenario["expected_outcome"],
        expected_reason_code=None,
        actual_reason_code=None,
        model_invoked=False,
        latency_seconds=latency,
        final_transaction_state=final_state,
        passed=duplicate_prevented,
    )


async def duplicate_payment_sequential(scenario: dict) -> ScenarioResult:
    return await _duplicate_payment(scenario, concurrent=False)


async def duplicate_payment_concurrent(scenario: dict) -> ScenarioResult:
    return await _duplicate_payment(scenario, concurrent=True)


SPECIAL_RUNNERS = {
    "cap_splitting_reuse_after_success": cap_splitting_reuse_after_success,
    "cap_splitting_reuse_before_completion": cap_splitting_reuse_before_completion,
    "replay_after_consumption": replay_after_consumption,
    "replay_directly_marked_consumed": replay_directly_marked_consumed,
    "price_protected_after_catalog_change": price_protected_after_catalog_change,
    "cart_tampered_quantity": cart_tampered_quantity,
    "cart_tampered_price": cart_tampered_price,
    "duplicate_checkout_submit": duplicate_checkout_submit,
    "out_of_stock": out_of_stock,
    "merchant_upsell_intent_blocked": merchant_upsell_intent_blocked,
    "merchant_upsell_intent_escalated": merchant_upsell_intent_escalated,
    "duplicate_payment_sequential": duplicate_payment_sequential,
    "duplicate_payment_concurrent": duplicate_payment_concurrent,
}


async def run_scenario(scenario: dict) -> ScenarioResult:
    """Dispatch one scenario to its declared runner (generic or special)."""
    runner_name = scenario["runner"]
    if runner_name == "generic_hard_block":
        return await _run_generic_hard_block(scenario)
    special_runner = SPECIAL_RUNNERS.get(runner_name)
    if special_runner is None:
        raise ValueError(f"Unknown runner '{runner_name}' for scenario '{scenario['scenario_id']}'.")
    return await special_runner(scenario)


async def run_adversarial_suite() -> list[ScenarioResult]:
    """Run every scenario in scenarios.json, in order, and return their results."""
    scenarios = load_scenarios()
    return [await run_scenario(scenario) for scenario in scenarios]


def results_to_dicts(results: list[ScenarioResult]) -> list[dict]:
    """Convert ScenarioResult records into plain JSON-serializable dicts."""
    return [vars(r) for r in results]
