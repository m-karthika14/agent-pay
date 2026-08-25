"""
Purpose: Integration tests for app.policy.final_revalidation.run_final_revalidation()
(plan.md Section 8.3 / Section 15 step 13), exercised against a real,
persisted, frozen cart -- unlike app.policy.checks.check_mandate() (a pure
function, tested in tests/unit/test_policy_engine.py), this module's
check_category/check_inventory/check_cart_integrity all query the database.
"""
import uuid
from datetime import UTC, datetime, timedelta

from app.carts.freeze import freeze_cart
from app.carts.service import add_cart_item, create_cart
from app.core.config import get_settings
from app.db.models.cart import Cart
from app.db.models.inventory import Inventory
from app.db.models.merchant import Merchant
from app.db.models.product import Product
from app.db.models.user import User
from app.db.session import get_session_factory
from app.mandates.service import create_mandate, get_mandate_by_business_id, to_signed_mandate
from app.policy import reason_codes
from app.policy.final_revalidation import run_final_revalidation
from app.schemas.mandate import MandateIntent, MandatePayload


async def _build_frozen_cart_fixture(*, max_amount: int) -> dict:
    """Create an isolated merchant/user/mandate and a FROZEN cart with one electronics item."""
    factory = get_session_factory()
    unique = uuid.uuid4().hex[:8]
    async with factory() as session:
        merchant = Merchant(slug=f"final-revalidation-{unique}", name="Final Revalidation Merchant", currency="INR")
        user = User(email=f"final-revalidation-{unique}@agentpay.test", name="Final Revalidation User")
        session.add_all([merchant, user])
        await session.flush()

        product = Product(
            merchant_id=merchant.id, sku=f"SKU-{unique}", name="Test Product", description="d",
            price_minor=250_000, currency="INR", category="electronics", is_active=True,
        )
        session.add(product)
        await session.flush()
        session.add(Inventory(product_id=product.id, quantity=5))
        await session.commit()

        payload = MandatePayload(
            mandate_id=f"M-final-revalidation-{unique}",
            merchant_id=str(merchant.id),
            currency="INR",
            max_amount=max_amount,
            allowed_categories=["electronics"],
            allow_addons=False,
            delivery_requirement="under_3_days",
            single_use=True,
            expires_at=datetime.now(UTC) + timedelta(days=1),
            intent=MandateIntent(product_type="test product"),
        )
        await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

        cart = await create_cart(session, user.id, merchant.id, "INR")
        await add_cart_item(session, uuid.UUID(cart.cart_id), product.id, 1)
        await session.commit()

        cart_row = await session.get(Cart, uuid.UUID(cart.cart_id))
        await freeze_cart(session, cart_row)
        await session.commit()

        return {"cart_id": cart_row.id, "mandate_id": payload.mandate_id}


async def test_final_revalidation_passes_for_a_within_cap_frozen_cart() -> None:
    """A frozen cart within the mandate's cap passes final re-validation."""
    fixture = await _build_frozen_cart_fixture(max_amount=500_000)
    factory = get_session_factory()
    async with factory() as session:
        cart = await session.get(Cart, fixture["cart_id"])
        mandate_row = await get_mandate_by_business_id(session, fixture["mandate_id"])
        signed_mandate = to_signed_mandate(mandate_row)
        public_key_b64 = get_settings().ed25519_public_key_b64

        result = await run_final_revalidation(
            session, signed_mandate, mandate_row, public_key_b64, cart, signed_mandate.payload.allowed_categories
        )

    assert result.passed is True


async def test_final_revalidation_blocks_when_cart_exceeds_mandate_cap() -> None:
    """
    A frozen cart whose subtotal exceeds the mandate's cap fails final
    re-validation with MANDATE_AMOUNT_EXCEEDED -- this is the defense-in-
    depth check that stops an AI-approved modification from silently
    expanding the money boundary (plan.md Rule 1).
    """
    fixture = await _build_frozen_cart_fixture(max_amount=100_000)  # cart's single item costs 250,000
    factory = get_session_factory()
    async with factory() as session:
        cart = await session.get(Cart, fixture["cart_id"])
        mandate_row = await get_mandate_by_business_id(session, fixture["mandate_id"])
        signed_mandate = to_signed_mandate(mandate_row)
        public_key_b64 = get_settings().ed25519_public_key_b64

        result = await run_final_revalidation(
            session, signed_mandate, mandate_row, public_key_b64, cart, signed_mandate.payload.allowed_categories
        )

    assert result.passed is False
    assert result.reason_code == reason_codes.MANDATE_AMOUNT_EXCEEDED
