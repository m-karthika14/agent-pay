#!/usr/bin/env python
"""
Purpose: Seed the AgentPay database with the UrbanNest demo merchant,
its small product catalog, inventory, and one demo user (plan.md Section 18).

Responsibilities:
- Idempotently create the UrbanNest merchant (looked up by slug).
- Idempotently create its 8 products (looked up by SKU) with inventory.
- Idempotently create one demo user (looked up by email).

The catalog is deliberately small and interconnected -- each product has one
or two natural companions in a different category (earbuds -> case/adapter,
watch -> strap, power bank -> cable/charger) -- so the Merchant Revenue
Agent (app.agents.merchant) has genuine, LLM-legible cross-sell
opportunities to reason about from the product names/descriptions alone.
There are no bundle SKUs: the agent creates combinations by proposing
separate products, never a pre-packaged bundle.

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
        "category": "audio",
        "quantity": 50,
    },
    {
        "sku": "CASE-001",
        "name": "Protective Earbuds Case",
        "description": "Silicone protective case designed for the wireless earbuds.",
        "price_minor": 29_900,
        "category": "accessories",
        "quantity": 100,
    },
    {
        "sku": "ADAPTER-001",
        "name": "USB-C Audio Adapter",
        "description": "USB-C to 3.5mm adapter for wired listening alongside the wireless earbuds.",
        "price_minor": 39_900,
        "category": "accessories",
        "quantity": 60,
    },
    {
        "sku": "WATCH-001",
        "name": "Smart Watch",
        "description": "Fitness-tracking smart watch with heart-rate monitor.",
        "price_minor": 349_900,
        "category": "wearables",
        "quantity": 30,
    },
    {
        "sku": "STRAP-001",
        "name": "Smart Watch Strap",
        "description": "Adjustable replacement strap for the smart watch.",
        "price_minor": 49_900,
        "category": "accessories",
        "quantity": 70,
    },
    {
        "sku": "POWERBANK-001",
        "name": "10,000mAh Power Bank",
        "description": "10,000 mAh USB-C power bank.",
        "price_minor": 129_900,
        "category": "power",
        "quantity": 80,
    },
    {
        "sku": "CHARGER-001",
        "name": "65W USB-C Charger",
        "description": "65W USB-C fast charger, ideal for quickly topping up the power bank or other USB-C devices.",
        "price_minor": 179_900,
        "category": "power",
        "quantity": 40,
    },
    {
        "sku": "CABLE-001",
        "name": "USB-C Charging Cable",
        "description": "1-meter USB-C charging cable, compatible with the power bank and charger.",
        "price_minor": 39_900,
        "category": "accessories",
        "quantity": 100,
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
