#!/usr/bin/env python
"""
Purpose: Seed the AgentPay database with the UrbanNest demo merchant,
its small product catalog, inventory, and one demo user (plan.md Section 18).

Responsibilities:
- Idempotently create the UrbanNest merchant (looked up by slug).
- Idempotently create its 5 products (looked up by SKU) with inventory.
- Idempotently create one demo user (looked up by email).

Safe to run multiple times: existing rows (matched by their natural key)
are left untouched rather than duplicated.

Run from the repo root or from backend/:
    uv run python scripts/seed_database.py
    (or, from backend/:  uv run python ../scripts/seed_database.py)
"""
import asyncio
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.db.models.inventory import Inventory  # noqa: E402
from app.db.models.merchant import Merchant  # noqa: E402
from app.db.models.product import Product  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402

# UrbanNest catalog (plan.md Section 18). Prices are in paise (minor units).
URBANNEST_PRODUCTS = [
    {
        "sku": "EARBUDS-001",
        "name": "Wireless Earbuds",
        "description": "Compact true-wireless earbuds with charging case.",
        "price_minor": 249_900,
        "category": "electronics",
        "quantity": 50,
    },
    {
        "sku": "WATCH-001",
        "name": "Smart Watch",
        "description": "Fitness-tracking smart watch with heart-rate monitor.",
        "price_minor": 349_900,
        "category": "electronics",
        "quantity": 30,
    },
    {
        "sku": "POWERBANK-001",
        "name": "Power Bank",
        "description": "10,000 mAh USB-C power bank.",
        "price_minor": 129_900,
        "category": "electronics",
        "quantity": 80,
    },
    {
        "sku": "CASE-001",
        "name": "Protective Case",
        "description": "Silicone protective case for the wireless earbuds.",
        "price_minor": 29_900,
        "category": "accessories",
        "quantity": 100,
    },
    {
        "sku": "BUNDLE-001",
        "name": "Premium Bundle",
        "description": "Wireless earbuds bundled with a protective case.",
        "price_minor": 279_900,
        "category": "electronics",
        "quantity": 20,
    },
]

DEMO_USER_EMAIL = "demo@agentpay.test"
DEMO_USER_NAME = "AgentPay Demo User"
URBANNEST_SLUG = "urbannest"


async def seed() -> None:
    """Idempotently seed the merchant, catalog, inventory, and demo user."""
    factory = get_session_factory()
    async with factory() as session:
        merchant_result = await session.execute(
            select(Merchant).where(Merchant.slug == URBANNEST_SLUG)
        )
        merchant = merchant_result.scalar_one_or_none()
        if merchant is None:
            merchant = Merchant(slug=URBANNEST_SLUG, name="UrbanNest", currency="INR")
            session.add(merchant)
            await session.flush()
            print(f"Created merchant: {merchant.name} ({merchant.id})")
        else:
            print(f"Merchant already exists: {merchant.name} ({merchant.id})")

        for spec in URBANNEST_PRODUCTS:
            product_result = await session.execute(
                select(Product).where(Product.sku == spec["sku"])
            )
            product = product_result.scalar_one_or_none()
            if product is None:
                product = Product(
                    merchant_id=merchant.id,
                    sku=spec["sku"],
                    name=spec["name"],
                    description=spec["description"],
                    price_minor=spec["price_minor"],
                    currency="INR",
                    category=spec["category"],
                    is_active=True,
                )
                session.add(product)
                await session.flush()
                session.add(Inventory(product_id=product.id, quantity=spec["quantity"], reserved_quantity=0))
                await session.flush()
                print(f"  Created product: {product.name} ({spec['sku']}) x{spec['quantity']}")
            else:
                print(f"  Product already exists: {product.name} ({spec['sku']})")

        user_result = await session.execute(select(User).where(User.email == DEMO_USER_EMAIL))
        user = user_result.scalar_one_or_none()
        if user is None:
            user = User(email=DEMO_USER_EMAIL, name=DEMO_USER_NAME)
            session.add(user)
            await session.flush()
            print(f"Created demo user: {user.email} ({user.id})")
        else:
            print(f"Demo user already exists: {user.email} ({user.id})")

        await session.commit()
        print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
