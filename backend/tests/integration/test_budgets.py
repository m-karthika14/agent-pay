"""
Purpose: Integration tests for a user's own "AI Shopping Budget"
(plan.md Phase 4) -- app.budgets.service's set/get round trip, expiry, and
its enforcement inside app.authorization.service (both at
create_authorization_request() -- what Claude asks for -- and
approve_authorization_request() -- what a human's Edit could push back up).
"""
import uuid
from datetime import UTC, datetime, timedelta

from app.authorization.service import approve_authorization_request, create_authorization_request
from app.budgets.service import get_active_budget, set_budget
from app.carts.service import add_cart_item, create_cart
from app.db.models.inventory import Inventory
from app.db.models.merchant import Merchant
from app.db.models.product import Product
from app.db.models.user import User
from app.db.session import get_session_factory
from app.schemas.authorization import ApproveAuthorizationRequest, RequestAuthorizationInput
from app.schemas.budget import SetBudgetRequest
from app.schemas.common import AgentPayError


async def _create_merchant_with_product(*, price_minor: int = 200_000) -> tuple[Merchant, Product, User]:
    factory = get_session_factory()
    unique = uuid.uuid4().hex[:8]
    async with factory() as session:
        merchant = Merchant(slug=f"budget-test-{unique}", name=f"Budget Test Merchant {unique}", currency="INR")
        user = User(email=f"budget-{unique}@agentpay.test", name="Budget Test Buyer")
        session.add_all([merchant, user])
        await session.flush()

        product = Product(
            merchant_id=merchant.id,
            sku=f"BUDGET-{unique}",
            name="Wireless Earbuds",
            description="Test product for budget tests.",
            price_minor=price_minor,
            currency="INR",
            category="audio",
            is_active=True,
        )
        session.add(product)
        await session.flush()
        session.add(Inventory(product_id=product.id, quantity=10, reserved_quantity=0))
        await session.commit()
        return merchant, product, user


async def test_unset_budget_is_inactive() -> None:
    _, _, user = await _create_merchant_with_product()
    factory = get_session_factory()
    async with factory() as session:
        budget = await get_active_budget(session, user.id)

    assert budget.is_active is False
    assert budget.max_amount_minor is None
    assert budget.allow_addons is None


async def test_set_and_get_budget_round_trip() -> None:
    _, _, user = await _create_merchant_with_product()
    factory = get_session_factory()
    async with factory() as session:
        set_result = await set_budget(
            session, user.id, SetBudgetRequest(max_amount_minor=500_000, allow_addons=True, expires_in_hours=24)
        )
        await session.commit()

        fetched = await get_active_budget(session, user.id)

    assert set_result.is_active is True
    assert set_result.max_amount_minor == 500_000
    assert fetched.max_amount_minor == 500_000
    assert fetched.allow_addons is True


async def test_set_budget_overwrites_prior() -> None:
    _, _, user = await _create_merchant_with_product()
    factory = get_session_factory()
    async with factory() as session:
        await set_budget(session, user.id, SetBudgetRequest(max_amount_minor=500_000, allow_addons=True))
        await session.commit()

        await set_budget(session, user.id, SetBudgetRequest(max_amount_minor=200_000, allow_addons=False))
        await session.commit()

        fetched = await get_active_budget(session, user.id)

    assert fetched.max_amount_minor == 200_000
    assert fetched.allow_addons is False


async def test_expired_budget_is_treated_as_unset() -> None:
    _, _, user = await _create_merchant_with_product()
    factory = get_session_factory()
    async with factory() as session:
        await set_budget(session, user.id, SetBudgetRequest(max_amount_minor=500_000, allow_addons=True))
        await session.commit()

        # Force it into the past, bypassing set_budget's own expires_in_hours math.
        row = await session.get(User, user.id)
        row.ai_budget_expires_at = datetime.now(UTC) - timedelta(hours=1)
        await session.commit()

        fetched = await get_active_budget(session, user.id)

    assert fetched.is_active is False
    assert fetched.max_amount_minor is None


async def test_create_authorization_request_rejected_when_over_budget() -> None:
    merchant, product, user = await _create_merchant_with_product(price_minor=200_000)
    factory = get_session_factory()
    async with factory() as session:
        await set_budget(session, user.id, SetBudgetRequest(max_amount_minor=500_000, allow_addons=True))
        await session.commit()

        cart = await create_cart(session, user.id, merchant.id, "INR")
        cart_id = uuid.UUID(cart.cart_id)
        await add_cart_item(session, cart_id, product.id, 1)
        await session.commit()

        try:
            await create_authorization_request(
                session,
                RequestAuthorizationInput(
                    cart_id=str(cart_id),
                    product_type=product.name,
                    max_amount_minor=799_900,  # over the Rs 5,000 budget
                    allowed_categories=[product.category],
                ),
            )
            raised = None
        except AgentPayError as exc:
            raised = exc

    assert raised is not None
    assert raised.reason_code == "EXCEEDS_AI_SHOPPING_BUDGET"


async def test_create_authorization_request_unaffected_when_no_budget_set() -> None:
    """Backward compatibility: a user who never set a budget sees no new restriction."""
    merchant, product, user = await _create_merchant_with_product(price_minor=200_000)
    factory = get_session_factory()
    async with factory() as session:
        cart = await create_cart(session, user.id, merchant.id, "INR")
        cart_id = uuid.UUID(cart.cart_id)
        await add_cart_item(session, cart_id, product.id, 1)
        await session.commit()

        request = await create_authorization_request(
            session,
            RequestAuthorizationInput(
                cart_id=str(cart_id),
                product_type=product.name,
                max_amount_minor=799_900,
                allowed_categories=[product.category],
            ),
        )
        await session.commit()

    assert request.status == "PENDING"
    assert request.max_amount_minor == 799_900


async def test_create_authorization_request_clamps_addons_when_budget_disallows() -> None:
    merchant, product, user = await _create_merchant_with_product(price_minor=200_000)
    factory = get_session_factory()
    async with factory() as session:
        await set_budget(session, user.id, SetBudgetRequest(max_amount_minor=500_000, allow_addons=False))
        await session.commit()

        cart = await create_cart(session, user.id, merchant.id, "INR")
        cart_id = uuid.UUID(cart.cart_id)
        await add_cart_item(session, cart_id, product.id, 1)
        await session.commit()

        request = await create_authorization_request(
            session,
            RequestAuthorizationInput(
                cart_id=str(cart_id),
                product_type=product.name,
                max_amount_minor=300_000,
                allowed_categories=[product.category],
                allow_addons=True,
            ),
        )
        await session.commit()

    assert request.allow_addons is False


async def test_approve_with_edit_above_budget_is_rejected() -> None:
    """
    Defense in depth: even though create_authorization_request() already
    keeps Claude's own ask under the budget, a human's Edit form could still
    submit a higher number at approval time -- that must be rejected too.
    """
    merchant, product, user = await _create_merchant_with_product(price_minor=200_000)
    factory = get_session_factory()
    async with factory() as session:
        await set_budget(session, user.id, SetBudgetRequest(max_amount_minor=500_000, allow_addons=True))
        await session.commit()

        cart = await create_cart(session, user.id, merchant.id, "INR")
        cart_id = uuid.UUID(cart.cart_id)
        await add_cart_item(session, cart_id, product.id, 1)
        await session.commit()

        request = await create_authorization_request(
            session,
            RequestAuthorizationInput(
                cart_id=str(cart_id),
                product_type=product.name,
                max_amount_minor=400_000,
                allowed_categories=[product.category],
            ),
        )
        await session.commit()

        try:
            await approve_authorization_request(
                session,
                uuid.UUID(request.request_id),
                ApproveAuthorizationRequest(
                    product_type=product.name,
                    max_amount_minor=600_000,  # human edits UP, above the Rs 5,000 budget
                    allowed_categories=[product.category],
                ),
            )
            raised = None
        except AgentPayError as exc:
            raised = exc

    assert raised is not None
    assert raised.reason_code == "EXCEEDS_AI_SHOPPING_BUDGET"
