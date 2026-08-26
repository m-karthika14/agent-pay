"""
Purpose: Integration tests for the buyer order-history route (GET
/api/orders/by-user/{user_id}), exercised through the real FastAPI app
against the real PostgreSQL database.

No live Razorpay account is used, matching test_webhooks.py's pattern:
app.payments.checkout.create_order is mocked to return a synthetic order
dict, since Razorpay's own API isn't what's under test here.
"""
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import httpx
from httpx import ASGITransport

from app.db.models.inventory import Inventory
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
    """Create an isolated merchant + product + inventory + user for one test."""
    factory = get_session_factory()
    async with factory() as session:
        unique = uuid.uuid4().hex[:8]
        merchant = Merchant(slug=f"orders-route-test-{unique}", name="Orders Route Test Merchant", currency="INR")
        user = User(email=f"orders-route-{unique}@agentpay.test", name="Orders Route Test Buyer")
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


async def _place_one_order(client: httpx.AsyncClient, merchant, product, user, mandate_id: str) -> None:
    """Create a cart, add one item, freeze it, and create its (mocked) Razorpay order."""
    create_response = await client.post(
        "/api/carts", json={"user_id": str(user.id), "merchant_id": str(merchant.id), "currency": "INR"}
    )
    cart_id = create_response.json()["data"]["cart_id"]
    await client.post(f"/api/carts/{cart_id}/items", json={"product_id": str(product.id), "quantity": 2})
    checkout_response = await client.post(
        "/api/checkout/request", json={"cart_id": cart_id, "mandate_id": mandate_id}
    )
    assert checkout_response.status_code == 200

    with patch("app.payments.checkout.create_order", return_value={"id": f"order_{uuid.uuid4().hex[:12]}"}):
        complete_response = await client.post(
            f"/api/checkout/{cart_id}/complete", json={"mandate_id": mandate_id}
        )
    assert complete_response.status_code == 200


async def test_order_history_lists_placed_orders() -> None:
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)

    async with await _client() as client:
        await _place_one_order(client, merchant, product, user, mandate_id)

        response = await client.get(f"/api/orders/by-user/{user.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert len(body["data"]) == 1
    entry = body["data"][0]
    assert entry["mandate_id"] == mandate_id
    assert entry["status"] == "CREATED"
    assert entry["amount_minor"] == 20_000
    assert entry["currency"] == "INR"
    assert entry["item_summary"] == "2x Test Widget"


async def test_order_history_is_empty_for_a_new_buyer() -> None:
    _merchant, _product, user = await _create_fixture_data()

    async with await _client() as client:
        response = await client.get(f"/api/orders/by-user/{user.id}")

    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_order_history_is_newest_first() -> None:
    merchant, product, user = await _create_fixture_data()
    mandate_a = await _create_mandate_for(merchant, user)
    mandate_b = await _create_mandate_for(merchant, user)

    async with await _client() as client:
        await _place_one_order(client, merchant, product, user, mandate_a)
        await _place_one_order(client, merchant, product, user, mandate_b)

        response = await client.get(f"/api/orders/by-user/{user.id}")

    data = response.json()["data"]
    assert len(data) == 2
    assert data[0]["mandate_id"] == mandate_b
    assert data[1]["mandate_id"] == mandate_a
