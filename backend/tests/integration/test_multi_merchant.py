"""
Purpose: Integration tests for AgentPay's multi-merchant support (plan.md
Section 18 -- TechHub, AgentPay's second demo merchant, added alongside
UrbanNest).

Every test here uses its own isolated, throwaway merchants -- never the
real seeded UrbanNest/TechHub rows -- matching this suite's established
fixture convention. Testing "search with no merchant returns every real
demo merchant" therefore needs one exception: app.catalog.service.
DEMO_MERCHANT_SLUGS is patched per-test to the test's own two throwaway
slugs, so the real filtering logic is exercised without depending on
scripts/seed_database.py having been run (or colliding with real seeded
merchant slugs, which are globally unique).
"""
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import httpx
from httpx import ASGITransport

from app.agents.merchant.nodes import _CandidateProposal, _CandidateProposalList
from app.carts.service import add_cart_item, create_cart, get_open_cart_for_user
from app.catalog.service import list_products
from app.db.models.inventory import Inventory
from app.db.models.merchant import Merchant
from app.db.models.product import Product
from app.db.models.user import User
from app.db.session import get_session_factory
from app.intent.models import IntentDecisionType, _IntentClassification
from app.main import app
from app.mandates.service import create_mandate
from app.schemas.mandate import MandateIntent, MandatePayload
from app.schemas.proposal import ProposalStatus
from app.services.checkout_service import request_checkout


async def _client() -> httpx.AsyncClient:
    transport = ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")

MERCHANT_PATCH_TARGET = "app.agents.merchant.nodes.classify_with_schema"
INTENT_PATCH_TARGET = "app.intent.gate.classify_with_schema"


async def _create_merchant_with_product(*, category: str = "audio") -> tuple[Merchant, Product, User]:
    """Create one isolated merchant, one active product with stock, and one user."""
    factory = get_session_factory()
    unique = uuid.uuid4().hex[:8]
    async with factory() as session:
        merchant = Merchant(slug=f"mm-test-{unique}", name=f"Test Merchant {unique}", currency="INR")
        user = User(email=f"mm-{unique}@agentpay.test", name="Multi-Merchant Test Buyer")
        session.add_all([merchant, user])
        await session.flush()

        product = Product(
            merchant_id=merchant.id,
            sku=f"MM-{unique}",
            name="Wireless Earbuds",
            description="Test product for multi-merchant tests.",
            price_minor=200_000,
            currency="INR",
            category=category,
            is_active=True,
        )
        session.add(product)
        await session.flush()
        session.add(Inventory(product_id=product.id, quantity=10, reserved_quantity=0))
        await session.commit()
        return merchant, product, user


async def test_search_with_specific_merchant_returns_only_that_merchant() -> None:
    merchant_a, product_a, _user_a = await _create_merchant_with_product()
    merchant_b, product_b, _user_b = await _create_merchant_with_product()

    factory = get_session_factory()
    async with factory() as session:
        results_a = await list_products(session, merchant_id=merchant_a.id)
        results_b = await list_products(session, merchant_id=merchant_b.id)

    assert {p.product_id for p in results_a} == {str(product_a.id)}
    assert {p.product_id for p in results_b} == {str(product_b.id)}
    assert results_a[0].merchant_name == merchant_a.name
    assert results_b[0].merchant_name == merchant_b.name


async def test_search_with_no_merchant_searches_every_demo_merchant() -> None:
    """The cross-merchant comparison path: no merchant given -> every DEMO_MERCHANT_SLUGS merchant's products together."""
    merchant_a, product_a, _user_a = await _create_merchant_with_product()
    merchant_b, product_b, _user_b = await _create_merchant_with_product()

    factory = get_session_factory()
    async with factory() as session:
        with patch("app.catalog.service.DEMO_MERCHANT_SLUGS", (merchant_a.slug, merchant_b.slug)):
            results = await list_products(session, merchant_id=None)

    product_ids = {p.product_id for p in results}
    assert str(product_a.id) in product_ids
    assert str(product_b.id) in product_ids
    merchant_names = {p.merchant_name for p in results}
    assert merchant_names == {merchant_a.name, merchant_b.name}


async def _authorize_and_freeze(merchant: Merchant, product: Product, user: User) -> tuple[uuid.UUID, str]:
    """Create a mandate and a frozen (checked-out, no advisory) cart for one merchant/product/user."""
    factory = get_session_factory()
    async with factory() as session:
        payload = MandatePayload(
            mandate_id=f"M-mm-{uuid.uuid4().hex[:8]}",
            merchant_id=str(merchant.id),
            currency="INR",
            max_amount=500_000,
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
        await add_cart_item(session, uuid.UUID(cart.cart_id), product.id, 1)
        await session.commit()

        result = await request_checkout(session, uuid.UUID(cart.cart_id), payload.mandate_id)
        await session.commit()
        return uuid.UUID(result.cart.cart_id), payload.mandate_id


async def test_checkout_succeeds_at_an_arbitrary_merchant() -> None:
    """The checkout boundary is merchant-agnostic -- a second/third/etc. merchant works exactly like the first."""
    merchant, product, user = await _create_merchant_with_product()
    cart_id, mandate_id = await _authorize_and_freeze(merchant, product, user)

    assert cart_id is not None
    assert mandate_id.startswith("M-")


async def test_merchant_agent_never_proposes_a_different_merchants_product() -> None:
    """
    The core multi-merchant safety property: a cart's Merchant Revenue
    Agent can only ever be offered its OWN merchant's products as upsell
    candidates, never a different merchant's -- even when a same-category,
    in-stock, cheaper candidate exists at another merchant.
    """
    merchant_a, product_a, user = await _create_merchant_with_product(category="accessories")
    merchant_b, _product_b, _ = await _create_merchant_with_product(category="accessories")

    factory = get_session_factory()
    async with factory() as session:
        # A second, in-cart product at merchant A (so there's a real "cart"
        # for the agent to analyze) and a candidate upsell also at merchant A.
        candidate_a = Product(
            merchant_id=merchant_a.id, sku=f"MM-CAND-{uuid.uuid4().hex[:8]}", name="Merchant A Candidate",
            description="d", price_minor=50_000, currency="INR", category="accessories", is_active=True,
        )
        session.add(candidate_a)
        await session.flush()
        session.add(Inventory(product_id=candidate_a.id, quantity=10, reserved_quantity=0))
        await session.commit()

        payload = MandatePayload(
            mandate_id=f"M-mm-{uuid.uuid4().hex[:8]}",
            merchant_id=str(merchant_a.id),
            currency="INR",
            max_amount=500_000,
            allowed_categories=["accessories"],
            allow_addons=True,
            delivery_requirement="under_3_days",
            single_use=True,
            expires_at=datetime.now(UTC) + timedelta(days=1),
            intent=MandateIntent(product_type=product_a.name, notes="open to add-ons"),
        )
        await create_mandate(session, payload, user.id, merchant_a.id)
        await session.commit()

        cart = await create_cart(session, user.id, merchant_a.id, "INR")
        await add_cart_item(session, uuid.UUID(cart.cart_id), product_a.id, 1)
        await session.commit()

        candidates = _CandidateProposalList(
            candidates=[
                _CandidateProposal(
                    product_id=str(candidate_a.id), quantity=1, reason="Goes well with your purchase.",
                    estimated_value_add_minor=50_000,
                )
            ]
        )
        classification = _IntentClassification(decision=IntentDecisionType.ALLOW, confidence=0.95, reason="Consistent with intent.")

        captured_prompts: list[str] = []

        async def _capture_and_return(prompt: str, *_args, **_kwargs):
            captured_prompts.append(prompt)
            return candidates

        with (
            patch(MERCHANT_PATCH_TARGET, new=AsyncMock(side_effect=_capture_and_return)),
            patch(INTENT_PATCH_TARGET, new=AsyncMock(return_value=classification)),
        ):
            result = await request_checkout(session, uuid.UUID(cart.cart_id), payload.mandate_id)
            await session.commit()

    # merchant_b's product name must never appear in what the agent was shown as candidates.
    assert captured_prompts, "the merchant agent's LLM call was never made"
    assert merchant_b.name not in captured_prompts[0]
    # And the only proposal actually allowed/applied was merchant A's own candidate.
    assert result.proposal is not None
    assert result.proposal.status == ProposalStatus.PROPOSAL_ALLOWED
    assert result.proposal.product_id == str(candidate_a.id)


async def test_products_route_with_unknown_merchant_slug_404s() -> None:
    async with await _client() as client:
        response = await client.get("/api/products?merchant=not-a-real-merchant")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "MERCHANT_NOT_FOUND"


async def test_cart_by_user_is_scoped_per_merchant() -> None:
    """A user can have a separate OPEN cart at each of two merchants without either overwriting the other."""
    merchant_a, product_a, user = await _create_merchant_with_product()
    merchant_b, product_b, _ = await _create_merchant_with_product()

    factory = get_session_factory()
    async with factory() as session:
        cart_a = await create_cart(session, user.id, merchant_a.id, "INR")
        await add_cart_item(session, uuid.UUID(cart_a.cart_id), product_a.id, 1)
        # Committing between the two carts (rather than creating both in one
        # transaction) matters here: Postgres's now()/created_at reflects
        # transaction-start time, so two carts created in the same
        # transaction would tie on created_at, making the "most recent"
        # ordering this test checks non-deterministic.
        await session.commit()

        cart_b = await create_cart(session, user.id, merchant_b.id, "INR")
        await add_cart_item(session, uuid.UUID(cart_b.cart_id), product_b.id, 1)
        await session.commit()

        found_a = await get_open_cart_for_user(session, user.id, merchant_a.id)
        found_b = await get_open_cart_for_user(session, user.id, merchant_b.id)
        found_any = await get_open_cart_for_user(session, user.id, None)

    assert found_a is not None and found_a.cart_id == cart_a.cart_id
    assert found_b is not None and found_b.cart_id == cart_b.cart_id
    # Merchant-agnostic lookup returns whichever is most recent (cart_b), not a mix of both.
    assert found_any is not None and found_any.cart_id == cart_b.cart_id
