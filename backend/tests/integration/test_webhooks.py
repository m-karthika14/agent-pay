"""
Purpose: Integration tests for Phase 4 -- Razorpay order creation and
webhook processing -- exercised through the real FastAPI app against the
real PostgreSQL database.

No live Razorpay account is used: `app.payments.checkout.create_order` is
mocked to return a synthetic order dict (this project's own logic --
persisting the Order/Transaction rows and driving reconciliation off webhook
events -- is what's under test, not Razorpay's actual API). Webhook
signatures are computed locally against a known test secret, exercising the
exact same HMAC verification code that will run against real Razorpay
deliveries once live keys are configured.
"""
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models.cart import Cart
from app.db.models.inventory import Inventory
from app.db.models.mandate import Mandate
from app.db.models.merchant import Merchant
from app.db.models.order import Order
from app.db.models.product import Product
from app.db.models.transaction import Transaction
from app.db.models.user import User
from app.db.session import get_session_factory
from app.main import app
from app.mandates.service import create_mandate
from app.schemas.mandate import MandateIntent, MandatePayload, MandateStatus

WEBHOOK_SECRET = "fake_webhook_secret_for_tests"


@pytest.fixture
def razorpay_test_secrets(monkeypatch):
    """Configure known Test Mode-shaped secrets for the duration of one test."""
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_fake_key_id")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "fake_key_secret_for_tests")
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", WEBHOOK_SECRET)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _client() -> httpx.AsyncClient:
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def _create_fixture_data():
    """Create an isolated merchant + product + inventory + user for one test."""
    factory = get_session_factory()
    async with factory() as session:
        unique = uuid.uuid4().hex[:8]
        merchant = Merchant(slug=f"test-merchant-{unique}", name="Test Merchant", currency="INR")
        user = User(email=f"test-{unique}@agentpay.test", name="Test User")
        session.add_all([merchant, user])
        await session.flush()

        product = Product(
            merchant_id=merchant.id,
            sku=f"SKU-{unique}",
            name="Test Widget",
            description="A widget used only in tests.",
            price_minor=10_000,
            currency="INR",
            category="electronics",
            is_active=True,
        )
        session.add(product)
        await session.flush()
        session.add(Inventory(product_id=product.id, quantity=5, reserved_quantity=0))
        await session.commit()
        return merchant, product, user


async def _create_mandate_for(merchant, user) -> str:
    payload = MandatePayload(
        mandate_id=f"M-{uuid.uuid4().hex[:8]}",
        merchant_id=str(merchant.id),
        currency="INR",
        max_amount=500_000,
        allowed_categories=["electronics"],
        allow_addons=False,
        delivery_requirement="under_3_days",
        single_use=True,
        expires_at=datetime.now(UTC) + timedelta(days=1),
        intent=MandateIntent(product_type="test widget"),
    )
    factory = get_session_factory()
    async with factory() as session:
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()
    return payload.mandate_id


async def _freeze_cart(client: httpx.AsyncClient, merchant, product, user, mandate_id: str) -> str:
    """Create a cart, add an item, and run it through /checkout/request. Returns cart_id."""
    create_response = await client.post(
        "/api/carts", json={"user_id": str(user.id), "merchant_id": str(merchant.id), "currency": "INR"}
    )
    cart_id = create_response.json()["data"]["cart_id"]
    await client.post(f"/api/carts/{cart_id}/items", json={"product_id": str(product.id), "quantity": 1})
    checkout_response = await client.post(
        "/api/checkout/request", json={"cart_id": cart_id, "mandate_id": mandate_id}
    )
    assert checkout_response.status_code == 200
    return cart_id


def _sign_webhook(body: bytes) -> str:
    return hmac.new(key=WEBHOOK_SECRET.encode("utf-8"), msg=body, digestmod=hashlib.sha256).hexdigest()


def _payment_captured_payload(razorpay_order_id: str, razorpay_payment_id: str) -> bytes:
    return json.dumps(
        {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": razorpay_payment_id,
                        "order_id": razorpay_order_id,
                        "status": "captured",
                    }
                }
            },
        }
    ).encode("utf-8")


def _payment_failed_payload(razorpay_order_id: str, razorpay_payment_id: str) -> bytes:
    return json.dumps(
        {
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": razorpay_payment_id,
                        "order_id": razorpay_order_id,
                        "status": "failed",
                        "error_code": "BAD_REQUEST_ERROR",
                        "error_description": "Card declined.",
                    }
                }
            },
        }
    ).encode("utf-8")


async def test_complete_checkout_creates_order_with_mocked_razorpay(razorpay_test_secrets) -> None:
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)
    fake_order_id = f"order_test_{uuid.uuid4().hex[:8]}"

    with patch("app.payments.checkout.create_order", return_value={"id": fake_order_id}):
        async with await _client() as client:
            cart_id = await _freeze_cart(client, merchant, product, user, mandate_id)
            response = await client.post(f"/api/checkout/{cart_id}/complete", json={"mandate_id": mandate_id})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["razorpay_order_id"] == fake_order_id
    assert data["razorpay_key_id"] == "rzp_test_fake_key_id"
    assert data["amount_minor"] == 10_000


async def test_complete_checkout_is_idempotent(razorpay_test_secrets) -> None:
    """A retried /complete call must not create a second Razorpay order."""
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)
    fake_order_id = f"order_test_{uuid.uuid4().hex[:8]}"

    with patch(
        "app.payments.checkout.create_order", return_value={"id": fake_order_id}
    ) as mock_create_order:
        async with await _client() as client:
            cart_id = await _freeze_cart(client, merchant, product, user, mandate_id)
            first = await client.post(f"/api/checkout/{cart_id}/complete", json={"mandate_id": mandate_id})
            second = await client.post(f"/api/checkout/{cart_id}/complete", json={"mandate_id": mandate_id})

    assert first.json()["data"]["order_id"] == second.json()["data"]["order_id"]
    assert mock_create_order.call_count == 1


async def test_complete_checkout_before_freeze_is_rejected(razorpay_test_secrets) -> None:
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)

    async with await _client() as client:
        create_response = await client.post(
            "/api/carts", json={"user_id": str(user.id), "merchant_id": str(merchant.id), "currency": "INR"}
        )
        cart_id = create_response.json()["data"]["cart_id"]

        response = await client.post(f"/api/checkout/{cart_id}/complete", json={"mandate_id": mandate_id})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CART_NOT_FROZEN"


async def test_webhook_payment_captured_completes_transaction_and_consumes_mandate(razorpay_test_secrets) -> None:
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)
    fake_order_id = f"order_captured_{uuid.uuid4().hex[:8]}"
    fake_payment_id = f"pay_captured_{uuid.uuid4().hex[:8]}"

    with patch("app.payments.checkout.create_order", return_value={"id": fake_order_id}):
        async with await _client() as client:
            cart_id = await _freeze_cart(client, merchant, product, user, mandate_id)
            await client.post(f"/api/checkout/{cart_id}/complete", json={"mandate_id": mandate_id})

    body = _payment_captured_payload(fake_order_id, fake_payment_id)
    signature = _sign_webhook(body)

    async with await _client() as client:
        response = await client.post(
            "/api/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": signature}
        )
    assert response.status_code == 200

    factory = get_session_factory()
    async with factory() as session:
        order_result = await session.execute(select(Order).where(Order.razorpay_order_id == fake_order_id))
        order = order_result.scalar_one()
        assert order.status == "PAID"

        txn_result = await session.execute(select(Transaction).where(Transaction.order_id == order.id))
        transaction = txn_result.scalar_one()
        assert transaction.status == "CAPTURED"
        assert transaction.razorpay_payment_id == fake_payment_id

        mandate_result = await session.execute(select(Mandate).where(Mandate.mandate_id == mandate_id))
        mandate = mandate_result.scalar_one()
        assert mandate.status == MandateStatus.CONSUMED


async def test_webhook_payment_failed_does_not_consume_mandate(razorpay_test_secrets) -> None:
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)
    fake_order_id = f"order_failed_{uuid.uuid4().hex[:8]}"
    fake_payment_id = f"pay_failed_{uuid.uuid4().hex[:8]}"

    with patch("app.payments.checkout.create_order", return_value={"id": fake_order_id}):
        async with await _client() as client:
            cart_id = await _freeze_cart(client, merchant, product, user, mandate_id)
            await client.post(f"/api/checkout/{cart_id}/complete", json={"mandate_id": mandate_id})

    body = _payment_failed_payload(fake_order_id, fake_payment_id)
    signature = _sign_webhook(body)

    async with await _client() as client:
        response = await client.post(
            "/api/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": signature}
        )
    assert response.status_code == 200

    factory = get_session_factory()
    async with factory() as session:
        order_result = await session.execute(select(Order).where(Order.razorpay_order_id == fake_order_id))
        order = order_result.scalar_one()
        assert order.status == "PAYMENT_FAILED"

        txn_result = await session.execute(select(Transaction).where(Transaction.order_id == order.id))
        transaction = txn_result.scalar_one()
        assert transaction.status == "FAILED"
        assert transaction.failure_code == "BAD_REQUEST_ERROR"

        mandate_result = await session.execute(select(Mandate).where(Mandate.mandate_id == mandate_id))
        mandate = mandate_result.scalar_one()
        assert mandate.status == MandateStatus.ACTIVE


async def test_webhook_with_invalid_signature_is_rejected(razorpay_test_secrets) -> None:
    body = _payment_captured_payload("order_whatever", "pay_whatever")

    async with await _client() as client:
        response = await client.post(
            "/api/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": "not-a-real-signature"}
        )

    assert response.status_code == 400


async def test_duplicate_webhook_event_is_ignored(razorpay_test_secrets) -> None:
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)
    fake_order_id = f"order_dup_{uuid.uuid4().hex[:8]}"
    fake_payment_id = f"pay_dup_{uuid.uuid4().hex[:8]}"
    fake_event_id = f"evt_dup_{uuid.uuid4().hex[:8]}"

    with patch("app.payments.checkout.create_order", return_value={"id": fake_order_id}):
        async with await _client() as client:
            cart_id = await _freeze_cart(client, merchant, product, user, mandate_id)
            await client.post(f"/api/checkout/{cart_id}/complete", json={"mandate_id": mandate_id})

    body = _payment_captured_payload(fake_order_id, fake_payment_id)
    signature = _sign_webhook(body)
    headers = {"X-Razorpay-Signature": signature, "X-Razorpay-Event-Id": fake_event_id}

    async with await _client() as client:
        first = await client.post("/api/webhooks/razorpay", content=body, headers=headers)
        second = await client.post("/api/webhooks/razorpay", content=body, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert "Duplicate" in second.json()["detail"]

    factory = get_session_factory()
    async with factory() as session:
        mandate_result = await session.execute(select(Mandate).where(Mandate.mandate_id == mandate_id))
        mandate = mandate_result.scalar_one()
        # Consumed exactly once despite two webhook deliveries -- if the
        # duplicate had been reprocessed, consume_mandate's second call
        # would still leave status=CONSUMED, so we also check only one
        # MANDATE_CONSUMED audit event exists.
        assert mandate.status == MandateStatus.CONSUMED

        from app.db.models.audit_event import AuditEvent

        consumed_events = await session.execute(
            select(AuditEvent).where(
                AuditEvent.mandate_id == mandate.id, AuditEvent.event_type == "MANDATE_CONSUMED"
            )
        )
        assert len(consumed_events.scalars().all()) == 1
