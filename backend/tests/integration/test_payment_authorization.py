"""
Purpose: Integration tests for Automatic Payments (plan.md Phase 5) --
app.payments.authorization_service's setup/confirm/revoke lifecycle, and its
integration into the existing checkout path
(app.payments.checkout.create_checkout_session).

No live Razorpay account is used: every app.payments.razorpay_client call is
mocked. app.payments.authorization_service reaches razorpay_client via `from
app.payments import razorpay_client` (a module import), so its calls are
patched at the source (app.payments.razorpay_client.*) -- the attribute is
looked up on the module at call time, so patching the source affects every
such caller uniformly. app.payments.checkout, however, does `from
app.payments.razorpay_client import create_order` (a NAME import, binding
its own reference at import time) -- that one must be patched at
app.payments.checkout.create_order instead, matching
tests/integration/test_order_sync.py's and test_webhooks.py's own
established pattern for that exact function.

Every test builds its own isolated merchant/user/product/mandate/cart with
unique identifiers, matching this project's established convention.
"""
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import select

from app.carts.service import add_cart_item, create_cart
from app.db.models.cart import Cart
from app.db.models.inventory import Inventory
from app.db.models.merchant import Merchant
from app.db.models.order import Order
from app.db.models.payment_authorization import PaymentAuthorization, PaymentAuthorizationStatus
from app.db.models.product import Product
from app.db.models.transaction import Transaction
from app.db.models.user import User
from app.db.session import get_session_factory
from app.mandates.service import create_mandate, get_mandate_by_business_id
from app.mcp.tools import ALL_TOOLS
from app.payments.authorization_service import (
    confirm_payment_authorization,
    create_payment_authorization_setup,
    execute_authorized_payment,
    get_active_payment_authorization,
    revoke_payment_authorization,
)
from app.payments.checkout import create_checkout_session
from app.policy import reason_codes
from app.schemas.common import AgentPayError
from app.schemas.mandate import MandateIntent, MandatePayload
from app.schemas.payment_authorization import ConfirmPaymentAuthorizationRequest, SetupPaymentAuthorizationRequest
from app.services.checkout_service import request_checkout

RAZORPAY_CLIENT = "app.payments.razorpay_client"
# Appended to every fake Razorpay id literal below so re-running this file
# against the same persistent dev Postgres never collides with a previous
# run's rows (Order.razorpay_order_id is unique) -- these ids are never
# meant to look like real Razorpay ids, just to be distinct per run.
_RUN = uuid.uuid4().hex[:8]


async def _build_fixture(*, price_minor: int = 200_000, max_amount_minor: int = 300_000) -> dict:
    """Create an isolated merchant/user/product/mandate and a FROZEN cart, ready for checkout."""
    factory = get_session_factory()
    unique = uuid.uuid4().hex[:8]
    async with factory() as session:
        merchant = Merchant(slug=f"payauth-test-{unique}", name="Payment Auth Test Merchant", currency="INR")
        user = User(email=f"payauth-{unique}@agentpay.test", name="Payment Auth Test Buyer")
        session.add_all([merchant, user])
        await session.flush()

        product = Product(
            merchant_id=merchant.id, sku=f"PAYAUTH-{unique}", name="Wireless Earbuds", description="d",
            price_minor=price_minor, currency="INR", category="audio", is_active=True,
        )
        session.add(product)
        await session.flush()
        session.add(Inventory(product_id=product.id, quantity=10, reserved_quantity=0))
        await session.commit()

        payload = MandatePayload(
            mandate_id=f"M-payauth-{unique}",
            merchant_id=str(merchant.id),
            currency="INR",
            max_amount=max_amount_minor,
            allowed_categories=[product.category],
            allow_addons=False,
            delivery_requirement="under_3_days",
            single_use=True,
            expires_at=datetime.now(UTC) + timedelta(days=1),
            intent=MandateIntent(product_type=product.name),
        )
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

        cart = await create_cart(session, user.id, merchant.id, "INR")
        cart_id = uuid.UUID(cart.cart_id)
        await add_cart_item(session, cart_id, product.id, 1)
        await session.commit()

        await request_checkout(session, cart_id, payload.mandate_id)
        await session.commit()

        return {"user_id": user.id, "cart_id": cart_id, "mandate_id": payload.mandate_id, "price_minor": price_minor}


async def _add_active_authorization(user_id: uuid.UUID, *, max_amount_minor: int, expires_in_days: int = 30) -> None:
    """Directly insert an ACTIVE PaymentAuthorization row, bypassing the interactive setup flow (for tests that only need it already active)."""
    factory = get_session_factory()
    async with factory() as session:
        session.add(
            PaymentAuthorization(
                user_id=user_id,
                provider="razorpay",
                razorpay_customer_id="cust_fake",
                razorpay_token_id="token_fake",
                status=PaymentAuthorizationStatus.ACTIVE,
                currency="INR",
                max_amount_minor=max_amount_minor,
                authorized_at=datetime.now(UTC),
                expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
            )
        )
        await session.commit()


# --- 1. No payment authorization -> existing manual checkout unchanged ---


async def test_no_payment_authorization_leaves_manual_checkout_unchanged() -> None:
    fixture = await _build_fixture()
    factory = get_session_factory()
    async with factory() as session:
        with patch("app.payments.checkout.create_order", return_value={"id": "order_fake_" + _RUN}):
            result = await create_checkout_session(session, fixture["cart_id"], fixture["mandate_id"])
        await session.commit()

    assert result.auto_payment_status is None
    assert result.razorpay_order_id == "order_fake_" + _RUN


# --- 2. Successful setup + confirm -> ACTIVE ---


async def test_setup_and_confirm_activates_payment_authorization() -> None:
    fixture = await _build_fixture()
    factory = get_session_factory()
    async with factory() as session:
        with patch(f"{RAZORPAY_CLIENT}.create_customer", return_value={"id": "cust_123"}), patch(
            f"{RAZORPAY_CLIENT}.create_recurring_registration_order", return_value={"id": "order_setup_123_" + _RUN}
        ):
            setup = await create_payment_authorization_setup(
                session, fixture["user_id"], SetupPaymentAuthorizationRequest(max_amount_minor=500_000)
            )
        await session.commit()

        assert setup.razorpay_order_id == "order_setup_123_" + _RUN
        assert setup.razorpay_customer_id == "cust_123"

        with patch(
            f"{RAZORPAY_CLIENT}.fetch_payment",
            return_value={"id": "pay_setup_123_" + _RUN, "order_id": "order_setup_123_" + _RUN, "status": "captured", "token_id": "token_abc"},
        ):
            confirmed = await confirm_payment_authorization(
                session,
                fixture["user_id"],
                ConfirmPaymentAuthorizationRequest(razorpay_order_id="order_setup_123_" + _RUN, razorpay_payment_id="pay_setup_123_" + _RUN),
            )
        await session.commit()

    assert confirmed.is_active is True
    assert confirmed.status == "ACTIVE"
    assert confirmed.max_amount_minor == 500_000

    async with factory() as session:
        fetched = await get_active_payment_authorization(session, fixture["user_id"])
    assert fetched.is_active is True


async def test_confirm_rejects_a_payment_razorpay_does_not_report_as_successful() -> None:
    """Never trust the frontend's claim of success -- confirm re-checks with Razorpay directly."""
    fixture = await _build_fixture()
    factory = get_session_factory()
    async with factory() as session:
        with patch(f"{RAZORPAY_CLIENT}.create_customer", return_value={"id": "cust_456"}), patch(
            f"{RAZORPAY_CLIENT}.create_recurring_registration_order", return_value={"id": "order_setup_456_" + _RUN}
        ):
            await create_payment_authorization_setup(
                session, fixture["user_id"], SetupPaymentAuthorizationRequest(max_amount_minor=500_000)
            )
        await session.commit()

        with patch(
            f"{RAZORPAY_CLIENT}.fetch_payment",
            return_value={"id": "pay_setup_456_" + _RUN, "order_id": "order_setup_456_" + _RUN, "status": "failed"},
        ):
            try:
                await confirm_payment_authorization(
                    session,
                    fixture["user_id"],
                    ConfirmPaymentAuthorizationRequest(
                        razorpay_order_id="order_setup_456_" + _RUN, razorpay_payment_id="pay_setup_456_" + _RUN
                    ),
                )
                raised = None
            except AgentPayError as exc:
                raised = exc

    assert raised is not None
    assert raised.reason_code == reason_codes.PAYMENT_AUTHORIZATION_INVALID

    async with factory() as session:
        fetched = await get_active_payment_authorization(session, fixture["user_id"])
    assert fetched.is_active is False


async def test_confirm_rejects_a_payment_for_a_different_order() -> None:
    """Frontend cannot submit an arbitrary Razorpay reference -- it must belong to the order this service itself created."""
    fixture = await _build_fixture()
    factory = get_session_factory()
    async with factory() as session:
        with patch(f"{RAZORPAY_CLIENT}.create_customer", return_value={"id": "cust_789"}), patch(
            f"{RAZORPAY_CLIENT}.create_recurring_registration_order", return_value={"id": "order_setup_789_" + _RUN}
        ):
            await create_payment_authorization_setup(
                session, fixture["user_id"], SetupPaymentAuthorizationRequest(max_amount_minor=500_000)
            )
        await session.commit()

        with patch(
            f"{RAZORPAY_CLIENT}.fetch_payment",
            return_value={"id": "pay_other", "order_id": "order_SOMETHING_ELSE", "status": "captured", "token_id": "tok"},
        ):
            try:
                await confirm_payment_authorization(
                    session,
                    fixture["user_id"],
                    ConfirmPaymentAuthorizationRequest(razorpay_order_id="order_setup_789_" + _RUN, razorpay_payment_id="pay_other"),
                )
                raised = None
            except AgentPayError as exc:
                raised = exc

    assert raised is not None
    assert raised.reason_code == "PAYMENT_AUTHORIZATION_MISMATCH"


# --- 3/8. Invalid payment authorization (amount exceeds it) -> automatic payment blocked ---


async def test_automatic_payment_blocked_when_amount_exceeds_authorization_ceiling() -> None:
    fixture = await _build_fixture(price_minor=200_000, max_amount_minor=300_000)
    await _add_active_authorization(fixture["user_id"], max_amount_minor=100_000)  # below the cart's 200_000

    factory = get_session_factory()
    async with factory() as session:
        with patch("app.payments.checkout.create_order", return_value={"id": "order_fake_2_" + _RUN}), patch(
            f"{RAZORPAY_CLIENT}.create_recurring_payment"
        ) as recurring_mock:
            result = await create_checkout_session(session, fixture["cart_id"], fixture["mandate_id"])
        await session.commit()

        order = (await session.execute(
            select(Order).where(Order.razorpay_order_id == "order_fake_2_" + _RUN)
        )).scalar_one()

    assert result.auto_payment_status == "INVALID"
    assert order.status == "CREATED"  # never marked PAID
    recurring_mock.assert_not_called()  # never even attempted a charge above the authorized ceiling


# --- 4/13. Revoked payment authorization -> automatic payment blocked ---


async def test_revoked_authorization_prevents_automatic_payment() -> None:
    fixture = await _build_fixture()
    await _add_active_authorization(fixture["user_id"], max_amount_minor=500_000)

    factory = get_session_factory()
    async with factory() as session:
        revoked = await revoke_payment_authorization(session, fixture["user_id"])
        await session.commit()
    assert revoked.is_active is False

    async with factory() as session:
        with patch("app.payments.checkout.create_order", return_value={"id": "order_fake_3_" + _RUN}), patch(
            f"{RAZORPAY_CLIENT}.create_recurring_payment"
        ) as recurring_mock:
            result = await create_checkout_session(session, fixture["cart_id"], fixture["mandate_id"])
        await session.commit()

    assert result.auto_payment_status is None  # falls back to manual, exactly like "no authorization at all"
    recurring_mock.assert_not_called()


# --- 5. Expired payment authorization -> automatic payment blocked ---


async def test_expired_authorization_prevents_automatic_payment() -> None:
    fixture = await _build_fixture()
    await _add_active_authorization(fixture["user_id"], max_amount_minor=500_000, expires_in_days=-1)  # already expired

    factory = get_session_factory()
    async with factory() as session:
        with patch("app.payments.checkout.create_order", return_value={"id": "order_fake_4_" + _RUN}), patch(
            f"{RAZORPAY_CLIENT}.create_recurring_payment"
        ) as recurring_mock:
            result = await create_checkout_session(session, fixture["cart_id"], fixture["mandate_id"])
        await session.commit()

    assert result.auto_payment_status is None
    recurring_mock.assert_not_called()


# --- 6. Valid mandate + valid payment authorization -> automatic payment executes ---


async def test_automatic_payment_executes_and_captures() -> None:
    fixture = await _build_fixture(price_minor=200_000, max_amount_minor=300_000)
    await _add_active_authorization(fixture["user_id"], max_amount_minor=500_000)

    factory = get_session_factory()
    async with factory() as session:
        with (
            patch("app.payments.checkout.create_order", return_value={"id": "order_fake_5_" + _RUN}),
            patch(
                f"{RAZORPAY_CLIENT}.create_recurring_payment",
                return_value={"id": "pay_auto_5_" + _RUN, "status": "captured"},
            ) as recurring_mock,
            patch("app.payments.reconciliation.fetch_order", return_value={"status": "paid"}),
            patch(
                "app.payments.reconciliation.fetch_order_payments",
                return_value=[{"id": "pay_auto_5_" + _RUN, "status": "captured"}],
            ),
        ):
            result = await create_checkout_session(session, fixture["cart_id"], fixture["mandate_id"])
        await session.commit()

        order = (await session.execute(
            select(Order).where(Order.razorpay_order_id == "order_fake_5_" + _RUN)
        )).scalar_one()
        transaction = (await session.execute(
            select(Transaction).where(Transaction.order_id == order.id)
        )).scalar_one()

        mandate_row = await get_mandate_by_business_id(session, fixture["mandate_id"])

    assert result.auto_payment_status == "CAPTURED"
    assert order.status == "PAID"
    assert order.amount_minor == 200_000  # the server-side frozen cart's own total, exactly
    assert transaction.status == "CAPTURED"
    assert transaction.razorpay_payment_id == "pay_auto_5_" + _RUN
    recurring_mock.assert_called_once()
    # The mandate is consumed via the SAME reconciliation path a real webhook uses -- no separate implementation.
    assert mandate_row.status.value == "CONSUMED"


# --- 7. Defense in depth: amount somehow exceeds the mandate's own cap ---


async def test_automatic_payment_blocked_if_amount_ever_exceeded_the_mandate_cap() -> None:
    """
    request_checkout() already guarantees a FROZEN cart's total can never
    exceed its mandate's cap -- this test exercises execute_authorized_payment's
    own redundant, defense-in-depth check directly, for the case that
    guarantee were ever violated by a bug elsewhere.
    """
    fixture = await _build_fixture(price_minor=200_000, max_amount_minor=300_000)
    await _add_active_authorization(fixture["user_id"], max_amount_minor=500_000)

    factory = get_session_factory()
    async with factory() as session:
        cart_row = await session.get(Cart, fixture["cart_id"])
        mandate_row = await get_mandate_by_business_id(session, fixture["mandate_id"])
        # An order somehow priced above the mandate's own 300_000 cap.
        order = Order(cart_id=cart_row.id, mandate_id=mandate_row.id, status="CREATED", amount_minor=999_999, currency="INR")
        session.add(order)
        await session.flush()

        with patch(f"{RAZORPAY_CLIENT}.create_recurring_payment") as recurring_mock:
            outcome = await execute_authorized_payment(session, cart_row, order, mandate_row)
        await session.commit()

    assert outcome == "INVALID"
    recurring_mock.assert_not_called()


# --- 10. Duplicate payment request must not charge twice ---


async def test_duplicate_checkout_completion_does_not_charge_twice() -> None:
    fixture = await _build_fixture(price_minor=200_000, max_amount_minor=300_000)
    await _add_active_authorization(fixture["user_id"], max_amount_minor=500_000)

    factory = get_session_factory()
    async with factory() as session:
        with (
            patch("app.payments.checkout.create_order", return_value={"id": "order_fake_dup_" + _RUN}),
            patch(
                f"{RAZORPAY_CLIENT}.create_recurring_payment",
                return_value={"id": "pay_dup_" + _RUN, "status": "captured"},
            ) as recurring_mock,
            patch("app.payments.reconciliation.fetch_order", return_value={"status": "paid"}),
            patch("app.payments.reconciliation.fetch_order_payments", return_value=[{"id": "pay_dup_" + _RUN, "status": "captured"}]),
        ):
            first = await create_checkout_session(session, fixture["cart_id"], fixture["mandate_id"])
            await session.commit()
            second = await create_checkout_session(session, fixture["cart_id"], fixture["mandate_id"])
            await session.commit()

    assert first.order_id == second.order_id
    assert first.auto_payment_status == "CAPTURED"
    # The second call hit the pre-existing idempotency early-return (same
    # Transaction.idempotency_key) before ever reaching automatic payment
    # again -- the charge was only ever attempted once.
    recurring_mock.assert_called_once()


# --- 11. Razorpay reports payment failure -> order must NOT become PAID ---


async def test_razorpay_failure_leaves_order_unpaid() -> None:
    fixture = await _build_fixture(price_minor=200_000, max_amount_minor=300_000)
    await _add_active_authorization(fixture["user_id"], max_amount_minor=500_000)

    factory = get_session_factory()
    async with factory() as session:
        with (
            patch("app.payments.checkout.create_order", return_value={"id": "order_fake_fail_" + _RUN}),
            patch(f"{RAZORPAY_CLIENT}.create_recurring_payment", side_effect=Exception("card_declined: insufficient funds")),
        ):
            result = await create_checkout_session(session, fixture["cart_id"], fixture["mandate_id"])
        await session.commit()

        order = (await session.execute(
            select(Order).where(Order.razorpay_order_id == "order_fake_fail_" + _RUN)
        )).scalar_one()

    assert result.auto_payment_status == "FAILED"
    assert order.status == "CREATED"


# --- 12. Razorpay requires additional authentication -> correct, unpaid state ---


async def test_razorpay_requires_authentication_leaves_order_unpaid() -> None:
    fixture = await _build_fixture(price_minor=200_000, max_amount_minor=300_000)
    await _add_active_authorization(fixture["user_id"], max_amount_minor=500_000)

    factory = get_session_factory()
    async with factory() as session:
        with (
            patch("app.payments.checkout.create_order", return_value={"id": "order_fake_auth_" + _RUN}),
            patch(
                f"{RAZORPAY_CLIENT}.create_recurring_payment",
                side_effect=Exception("BAD_REQUEST_ERROR: payment requires additional authentication"),
            ),
        ):
            result = await create_checkout_session(session, fixture["cart_id"], fixture["mandate_id"])
        await session.commit()

        order = (await session.execute(
            select(Order).where(Order.razorpay_order_id == "order_fake_auth_" + _RUN)
        )).scalar_one()

    assert result.auto_payment_status == "REQUIRES_AUTHENTICATION"
    assert order.status == "CREATED"  # never falsely marked paid


# --- 14 is covered by the full existing suite staying green (164 passed unaffected by this file) ---


# --- Security tests ---


def test_claude_has_no_payment_authorization_mcp_tool() -> None:
    """Claude cannot create/modify/execute a payment authorization -- no such MCP tool exists."""
    assert len(ALL_TOOLS) == 8
    tool_names = {fn.__name__ for fn in ALL_TOOLS}
    assert not any("payment" in name for name in tool_names)
    assert not any("automatic" in name for name in tool_names)


async def test_payment_authorization_is_scoped_to_the_requesting_user_only() -> None:
    """A user's active payment authorization is never visible/usable for a different user's cart."""
    fixture_a = await _build_fixture(price_minor=200_000, max_amount_minor=300_000)
    fixture_b = await _build_fixture(price_minor=200_000, max_amount_minor=300_000)
    await _add_active_authorization(fixture_a["user_id"], max_amount_minor=500_000)
    # fixture_b's user has NO authorization.

    factory = get_session_factory()
    async with factory() as session:
        with patch("app.payments.checkout.create_order", return_value={"id": "order_fake_scope_" + _RUN}), patch(
            f"{RAZORPAY_CLIENT}.create_recurring_payment"
        ) as recurring_mock:
            result = await create_checkout_session(session, fixture_b["cart_id"], fixture_b["mandate_id"])
        await session.commit()

    assert result.auto_payment_status is None  # b's cart never borrows a's authorization
    recurring_mock.assert_not_called()
