"""
Purpose: Integration tests for the catalog + mutable-cart API (Phase 2) and
the deterministic checkout boundary (Phase 3: request_checkout, cart
freeze/hash, the policy engine's hard checks), exercised through the real
FastAPI app (ASGI, in-process) against the real PostgreSQL database.

Each test creates its own merchant/product/inventory/user/mandate fixtures
with unique identifiers, independent of the seeded UrbanNest data, so this
suite never depends on scripts/seed_database.py having been run.
"""
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from httpx import ASGITransport
from sqlalchemy import select

from app.db.models.cart_item import CartItem
from app.db.models.inventory import Inventory
from app.db.models.merchant import Merchant
from app.db.models.product import Product
from app.db.models.user import User
from app.db.session import get_session_factory
from app.main import app
from app.mandates.service import create_mandate
from app.schemas.mandate import MandateIntent, MandatePayload


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


async def _client() -> httpx.AsyncClient:
    """Build an httpx client that talks to the FastAPI app in-process (no real server)."""
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def _create_mandate_for(merchant, user, **overrides: object) -> str:
    """
    Create and persist a signed mandate for the given merchant/user, returning
    its business-facing mandate_id. Defaults authorize up to 500,000 minor
    units in the "electronics" category -- override per test as needed.
    """
    defaults: dict[str, object] = {
        "mandate_id": f"M-{uuid.uuid4().hex[:8]}",
        "merchant_id": str(merchant.id),
        "currency": "INR",
        "max_amount": 500_000,
        "allowed_categories": ["electronics"],
        "allow_addons": False,
        "delivery_requirement": "under_3_days",
        "single_use": True,
        "expires_at": datetime.now(UTC) + timedelta(days=1),
        "intent": MandateIntent(product_type="test widget"),
    }
    defaults.update(overrides)
    payload = MandatePayload(**defaults)  # type: ignore[arg-type]

    factory = get_session_factory()
    async with factory() as session:
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()
    return payload.mandate_id


async def test_list_products_returns_200() -> None:
    """
    GET /api/products is scoped to the seeded UrbanNest merchant
    (app.catalog.service.list_products), not every Product row in the
    database -- a throwaway fixture merchant's product (as _create_fixture_data
    creates) is deliberately NOT expected to show up here, so this only
    checks the endpoint's shape, not fixture-specific content.
    """
    async with await _client() as client:
        response = await client.get("/api/products")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)


async def test_get_product() -> None:
    merchant, product, _user = await _create_fixture_data()

    async with await _client() as client:
        get_response = await client.get(f"/api/products/{product.id}")
        assert get_response.status_code == 200
        product_data = get_response.json()["data"]
        assert product_data["name"] == "Test Widget"
        assert product_data["merchant_id"] == str(merchant.id)
        assert product_data["availability"] == "in_stock"
        assert product_data["delivery"]
        assert product_data["return_policy"]


async def test_get_unknown_product_returns_404() -> None:
    async with await _client() as client:
        response = await client.get(f"/api/products/{uuid.uuid4()}")

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "PRODUCT_NOT_FOUND"


async def test_get_product_inventory() -> None:
    _merchant, product, _user = await _create_fixture_data()

    async with await _client() as client:
        response = await client.get(f"/api/products/{product.id}/inventory")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["quantity"] == 5
    assert data["reserved_quantity"] == 0
    assert data["available_quantity"] == 5


async def test_full_cart_lifecycle() -> None:
    """create_cart -> add_to_cart (merge) -> update -> remove, per plan.md Section 10."""
    merchant, product, user = await _create_fixture_data()

    async with await _client() as client:
        create_response = await client.post(
            "/api/carts",
            json={"user_id": str(user.id), "merchant_id": str(merchant.id), "currency": "INR"},
        )
        assert create_response.status_code == 200
        cart = create_response.json()["data"]
        assert cart["status"] == "OPEN"
        assert cart["subtotal_minor"] == 0
        cart_id = cart["cart_id"]

        # Add 1, then add 2 more of the same product -- must merge into one line.
        await client.post(f"/api/carts/{cart_id}/items", json={"product_id": str(product.id), "quantity": 1})
        add_response = await client.post(
            f"/api/carts/{cart_id}/items", json={"product_id": str(product.id), "quantity": 2}
        )
        assert add_response.status_code == 200
        cart = add_response.json()["data"]
        assert len(cart["items"]) == 1
        assert cart["items"][0]["quantity"] == 3
        assert cart["subtotal_minor"] == 30_000
        item_id = cart["items"][0]["item_id"]

        # Requesting more than available inventory must fail cleanly.
        over_response = await client.patch(
            f"/api/carts/{cart_id}/items/{item_id}", json={"quantity": 999}
        )
        assert over_response.status_code == 400
        assert over_response.json()["error"]["code"] == "INSUFFICIENT_INVENTORY"

        # Update to a valid quantity.
        update_response = await client.patch(
            f"/api/carts/{cart_id}/items/{item_id}", json={"quantity": 2}
        )
        assert update_response.status_code == 200
        assert update_response.json()["data"]["subtotal_minor"] == 20_000

        # get_cart reflects the same state.
        get_response = await client.get(f"/api/carts/{cart_id}")
        assert get_response.json()["data"]["subtotal_minor"] == 20_000

        # Remove the item -- subtotal returns to zero.
        remove_response = await client.delete(f"/api/carts/{cart_id}/items/{item_id}")
        assert remove_response.status_code == 200
        cart = remove_response.json()["data"]
        assert cart["items"] == []
        assert cart["subtotal_minor"] == 0


async def test_get_unknown_cart_returns_404() -> None:
    async with await _client() as client:
        response = await client.get(f"/api/carts/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CART_NOT_FOUND"


async def _create_cart_with_item(client: httpx.AsyncClient, merchant, product, user, quantity: int = 1) -> str:
    """Create a cart and add `quantity` of `product` to it via the real API. Returns cart_id."""
    create_response = await client.post(
        "/api/carts", json={"user_id": str(user.id), "merchant_id": str(merchant.id), "currency": "INR"}
    )
    cart_id = create_response.json()["data"]["cart_id"]
    await client.post(f"/api/carts/{cart_id}/items", json={"product_id": str(product.id), "quantity": quantity})
    return cart_id


async def test_checkout_freezes_cart_when_everything_is_valid() -> None:
    """plan.md Phase 3 acceptance: 'Authorized cart freezes.'"""
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)

    async with await _client() as client:
        cart_id = await _create_cart_with_item(client, merchant, product, user, quantity=1)

        response = await client.post("/api/checkout/request", json={"cart_id": cart_id, "mandate_id": mandate_id})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["cart"]["status"] == "FROZEN"
    assert data["frozen_hash"]
    assert data["frozen_at"] is not None


async def test_checkout_blocks_amount_exceeding_mandate_cap() -> None:
    """plan.md Phase 3 acceptance: 'unauthorized amount fails.'"""
    merchant, product, user = await _create_fixture_data()
    # Cart total will be 3 * 10_000 = 30_000; cap it well below that.
    mandate_id = await _create_mandate_for(merchant, user, max_amount=10_000)

    async with await _client() as client:
        cart_id = await _create_cart_with_item(client, merchant, product, user, quantity=3)

        response = await client.post("/api/checkout/request", json={"cart_id": cart_id, "mandate_id": mandate_id})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MANDATE_AMOUNT_EXCEEDED"

    async with await _client() as client:
        cart_response = await client.get(f"/api/carts/{cart_id}")
    assert cart_response.json()["data"]["status"] == "OPEN"


async def test_checkout_blocks_disallowed_category() -> None:
    merchant, product, user = await _create_fixture_data()  # product category is "electronics"
    mandate_id = await _create_mandate_for(merchant, user, allowed_categories=["accessories"])

    async with await _client() as client:
        cart_id = await _create_cart_with_item(client, merchant, product, user, quantity=1)

        response = await client.post("/api/checkout/request", json={"cart_id": cart_id, "mandate_id": mandate_id})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "MANDATE_CATEGORY_FORBIDDEN"


async def test_checkout_blocks_insufficient_inventory_at_checkout_time() -> None:
    """Stock can drop between add-to-cart and checkout; checkout must re-verify it."""
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)

    async with await _client() as client:
        cart_id = await _create_cart_with_item(client, merchant, product, user, quantity=5)

    # Simulate stock depletion after the item was added (e.g. another buyer took it).
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(Inventory).where(Inventory.product_id == product.id))
        inventory = result.scalar_one()
        inventory.quantity = 1
        await session.commit()

    async with await _client() as client:
        response = await client.post("/api/checkout/request", json={"cart_id": cart_id, "mandate_id": mandate_id})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVENTORY_INVALID"


async def test_duplicate_checkout_request_is_rejected() -> None:
    """plan.md Phase 3 acceptance: 'duplicate request fails.'"""
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)

    async with await _client() as client:
        cart_id = await _create_cart_with_item(client, merchant, product, user, quantity=1)

        first_response = await client.post(
            "/api/checkout/request", json={"cart_id": cart_id, "mandate_id": mandate_id}
        )
        assert first_response.status_code == 200

        second_response = await client.post(
            "/api/checkout/request", json={"cart_id": cart_id, "mandate_id": mandate_id}
        )

    assert second_response.status_code == 400
    assert second_response.json()["error"]["code"] == "IDEMPOTENCY_DUPLICATE"


async def test_mandate_cannot_be_reused_to_freeze_a_second_cart() -> None:
    """
    Phase 10 regression: an ACTIVE-but-unpaid mandate must not be reusable
    to freeze a second, DIFFERENT cart -- found by the adversarial suite
    (eval/scenarios.json's cap_splitting cases). Distinct from the
    duplicate-checkout test above: that one retries the SAME cart; this one
    uses the SAME mandate against a brand-new cart.
    """
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user, max_amount=500_000)

    async with await _client() as client:
        first_cart_id = await _create_cart_with_item(client, merchant, product, user, quantity=1)
        first_response = await client.post(
            "/api/checkout/request", json={"cart_id": first_cart_id, "mandate_id": mandate_id}
        )
        assert first_response.status_code == 200

        second_cart_id = await _create_cart_with_item(client, merchant, product, user, quantity=1)
        second_response = await client.post(
            "/api/checkout/request", json={"cart_id": second_cart_id, "mandate_id": mandate_id}
        )

    assert second_response.status_code == 400
    assert second_response.json()["error"]["code"] == "MANDATE_ALREADY_ASSOCIATED_WITH_ANOTHER_CART"


async def test_cart_tampered_after_freeze_is_blocked() -> None:
    """plan.md Phase 3 acceptance: 'modified cart fails' (frozen hash != final hash -> BLOCK)."""
    merchant, product, user = await _create_fixture_data()
    mandate_id = await _create_mandate_for(merchant, user)

    async with await _client() as client:
        cart_id = await _create_cart_with_item(client, merchant, product, user, quantity=1)
        freeze_response = await client.post(
            "/api/checkout/request", json={"cart_id": cart_id, "mandate_id": mandate_id}
        )
    assert freeze_response.status_code == 200

    # Simulate tampering: directly mutate a line item's quantity after freezing,
    # bypassing the API (which would normally refuse to mutate a FROZEN cart).
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(CartItem).where(CartItem.cart_id == uuid.UUID(cart_id)))
        item = result.scalars().first()
        item.quantity = 999
        item.line_total_minor = item.unit_price_minor * 999
        await session.commit()

    async with await _client() as client:
        response = await client.post("/api/checkout/request", json={"cart_id": cart_id, "mandate_id": mandate_id})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CART_HASH_MISMATCH"


async def test_checkout_with_unknown_mandate_returns_404() -> None:
    merchant, product, user = await _create_fixture_data()

    async with await _client() as client:
        cart_id = await _create_cart_with_item(client, merchant, product, user, quantity=1)

        response = await client.post(
            "/api/checkout/request", json={"cart_id": cart_id, "mandate_id": "M-does-not-exist"}
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MANDATE_NOT_FOUND"
