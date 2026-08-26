"""
Purpose: Integration tests for POST /api/orders/{order_id}/sync -- the
payment-status reconciliation fallback for when Razorpay's webhook can't
reach the backend (plan.md Section 16.5).

No live Razorpay account is used: app.payments.checkout.create_order and
the reconciliation-time lookups (fetch_order, fetch_order_payments) are all
mocked, matching test_webhooks.py's pattern.
"""
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
from httpx import ASGITransport
from sqlalchemy import select

from app.db.models.inventory import Inventory
from app.db.models.mandate import Mandate, MandateStatus
from app.db.models.merchant import Merchant
from app.db.models.product import Product
from app.db.models.user import User
from app.db.session import get_session_factory
from app.main import app
from app.mandates.service import create_mandate
from app.schemas.mandate import MandateIntent, MandatePayload


async def _client() -> httpx.AsyncClient:
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def _create_fixture_data():
    factory = get_session_factory()
    async with factory() as session:
        unique = uuid.uuid4().hex[:8]
        merchant = Merchant(slug=f"order-sync-test-{unique}", name="Order Sync Test Merchant", currency="INR")
        user = User(email=f"order-sync-{unique}@agentpay.test", name="Order Sync Test Buyer")
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


async def _place_order(client: httpx.AsyncClient, merchant, product, user, mandate_id: str, razorpay_order_id: str) -> str:
    """Create a cart, add one item, freeze it, and create its (mocked) Razorpay order. Returns AgentPay's order_id."""
    create_response = await client.post(
        "/api/carts", json={"user_id": str(user.id), "merchant_id": str(merchant.id), "currency": "INR"}
    )
    cart_id = create_response.json()["data"]["cart_id"]
    await client.post(f"/api/carts/{cart_id}/items", json={"product_id": str(product.id), "quantity": 1})
    checkout_response = await client.post(
        "/api/checkout/request", json={"cart_id": cart_id, "mandate_id": mandate_id}
    )
    assert checkout_response.status_code == 200

    with patch("app.payments.checkout.create_order", return_value={"id": razorpay_order_id}):
        complete_response = await client.post(
            f"/api/checkout/{cart_id}/complete", json={"mandate_id": mandate_id}
        )
    assert complete_response.status_code == 200
    return complete_response.json()["data"]["order_id"]


async def test_sync_finds_and_records_a_missed_captured_payment() -> None:
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)
    razorpay_order_id = f"order_{uuid.uuid4().hex[:12]}"
    razorpay_payment_id = f"pay_{uuid.uuid4().hex[:12]}"

    async with await _client() as client:
        order_id = await _place_order(client, merchant, product, user, mandate_id, razorpay_order_id)

        with (
            patch("app.payments.reconciliation.fetch_order", return_value={"status": "paid"}),
            patch(
                "app.payments.reconciliation.fetch_order_payments",
                return_value=[{"id": razorpay_payment_id, "status": "captured"}],
            ),
        ):
            response = await client.post(f"/api/orders/{order_id}/sync")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "PAID"
    assert body["data"]["mandate_id"] == mandate_id

    # The mandate must be consumed and a full audit trail recorded -- exactly
    # as if the webhook had actually arrived (see reconcile_order_state's
    # docstring: it delegates to the same handle_payment_captured()).
    factory = get_session_factory()
    async with factory() as session:
        mandate_result = await session.execute(select(Mandate).where(Mandate.mandate_id == mandate_id))
        mandate_row = mandate_result.scalar_one()
        assert mandate_row.status == MandateStatus.CONSUMED

    async with await _client() as client:
        audit_response = await client.get(f"/api/audit/by-mandate/{mandate_id}")
    event_types = [e["event_type"] for e in audit_response.json()["data"]]
    assert "PAYMENT_CAPTURED" in event_types
    assert "TRANSACTION_COMPLETED" in event_types


async def test_sync_leaves_state_unchanged_when_not_yet_paid() -> None:
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)
    razorpay_order_id = f"order_{uuid.uuid4().hex[:12]}"

    async with await _client() as client:
        order_id = await _place_order(client, merchant, product, user, mandate_id, razorpay_order_id)

        with patch("app.payments.reconciliation.fetch_order", return_value={"status": "created"}):
            response = await client.post(f"/api/orders/{order_id}/sync")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "CREATED"


async def test_sync_unknown_order_404s() -> None:
    async with await _client() as client:
        response = await client.post(f"/api/orders/{uuid.uuid4()}/sync")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ORDER_NOT_FOUND"
