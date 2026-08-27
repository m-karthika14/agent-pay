#!/usr/bin/env python
"""
Purpose: Seed the AgentPay database with its two AI-transactable demo
merchants (UrbanNest and TechHub), their product catalogs, inventory, and
one demo user (plan.md Section 18).

Responsibilities:
- Idempotently create each merchant (looked up by slug).
- Idempotently create-or-update each merchant's products (looked up by SKU)
  with inventory -- an existing SKU's name/description/price/category is
  brought in line with this file (e.g. a rename) rather than left stale,
  since nothing else treats an existing Product row's identity as anything
  other than its SKU.
- Idempotently create one demo user (looked up by email).

Product names use real, recognizable brand names (boAt, Noise, Sony, JBL,
Fire-Boltt, etc.) for a realistic-feeling catalog -- fictional prices/stock
on a demo storefront, not an implied partnership with any of them. Every
name deliberately starts with its brand as the first word, since
frontend/src/components/ProductImage.tsx derives each product's accent
color/wordmark from that first word.

UrbanNest's catalog is deliberately interconnected -- each product has one
or two natural companions in a different category (earbuds -> case/adapter,
watch -> strap, power bank -> cable/charger) -- so the Merchant Revenue
Agent (app.agents.merchant) has genuine, LLM-legible cross-sell
opportunities to reason about from the product names/descriptions alone.
There are no bundle SKUs: the agent creates combinations by proposing
separate products, never a pre-packaged bundle.

TechHub's catalog deliberately overlaps UrbanNest's product types (wireless
earbuds, smart watch, power bank, charger, earbuds case) at different
prices, so a buyer agent comparing merchants (app.mcp.tools.search_products
with no merchant argument) has a genuine reason to pick one over the other
-- not just two unrelated catalogs. Two SKUs' prices are held fixed across
any future catalog edit (EARBUDS-001 at Rs 2,499, TH-EARBUDS-001 at Rs
2,299) since that exact comparison is the one referenced throughout the
project's own demo walkthrough and reference docs.

UrbanNest's Wireless Earbuds and Smart Watch lines each span a full price
range (budget through flagship) so a mandate's spending cap actually has
meaningfully different options to land on, rather than one fixed price
point per product line.

Safe to run multiple times: existing rows (matched by SKU) are updated in
place rather than duplicated; inventory quantity is topped up to this
file's value without touching reserved_quantity (which reflects real
in-flight carts).

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

# Prices are in paise (minor units).
URBANNEST_PRODUCTS = [
    # --- Audio (earbuds) ---
    {
        "sku": "EARBUDS-001",
        "name": "boAt Airdopes 141",
        "description": "True wireless earbuds with ASAP charging and up to 42 hours of total playback.",
        "price_minor": 249_900,
        "category": "audio",
        "quantity": 50,
    },
    {
        "sku": "EARBUDS-002",
        "name": "Noise Buds VS104",
        "description": "Budget true wireless earbuds with quad-mic ENC and 40 hours of playback.",
        "price_minor": 99_900,
        "category": "audio",
        "quantity": 80,
    },
    {
        "sku": "EARBUDS-003",
        "name": "boAt Airdopes 161 Sport",
        "description": "Sweat and water-resistant sports earbuds with a secure ear-hook fit.",
        "price_minor": 179_900,
        "category": "audio",
        "quantity": 60,
    },
    {
        "sku": "EARBUDS-004",
        "name": "Sony WF-C500",
        "description": "Active noise-cancelling wireless earbuds with premium sound tuning.",
        "price_minor": 499_900,
        "category": "audio",
        "quantity": 35,
    },
    {
        "sku": "EARBUDS-005",
        "name": "JBL Tune Flex Ghost Edition",
        "description": "Flagship wireless earbuds tuned for studio-quality sound and all-day battery life.",
        "price_minor": 799_900,
        "category": "audio",
        "quantity": 20,
    },
    {
        "sku": "EARBUDS-006",
        "name": "Realme Buds Air 5",
        "description": "Hybrid ANC wireless earbuds with 45dB active noise cancellation.",
        "price_minor": 349_900,
        "category": "audio",
        "quantity": 45,
    },
    {
        "sku": "EARBUDS-007",
        "name": "OnePlus Nord Buds 2",
        "description": "Bass-boosted wireless earbuds with 12.4mm drivers and fast charging.",
        "price_minor": 299_900,
        "category": "audio",
        "quantity": 40,
    },
    {
        "sku": "EARBUDS-008",
        "name": "Mivi DuoPods A25",
        "description": "Compact true wireless earbuds with 32 hours total playback and IPX5 water resistance.",
        "price_minor": 119_900,
        "category": "audio",
        "quantity": 55,
    },
    # --- Wearables (smartwatches) ---
    {
        "sku": "WATCH-001",
        "name": "Noise ColorFit Pro 4",
        "description": "Fitness-tracking smartwatch with heart-rate and SpO2 monitoring.",
        "price_minor": 349_900,
        "category": "wearables",
        "quantity": 30,
    },
    {
        "sku": "WATCH-002",
        "name": "Fire-Boltt Ninja Call Pro",
        "description": "Entry-level smartwatch with Bluetooth calling and step tracking.",
        "price_minor": 149_900,
        "category": "wearables",
        "quantity": 50,
    },
    {
        "sku": "WATCH-003",
        "name": "boAt Wave Rider",
        "description": "Rugged smartwatch with built-in GPS and multiple workout tracking modes.",
        "price_minor": 299_900,
        "category": "wearables",
        "quantity": 40,
    },
    {
        "sku": "WATCH-004",
        "name": "Amazfit GTS 4",
        "description": "Premium smartwatch with an always-on AMOLED display and blood-oxygen sensor.",
        "price_minor": 699_900,
        "category": "wearables",
        "quantity": 25,
    },
    {
        "sku": "WATCH-005",
        "name": "Apple Watch SE",
        "description": "Flagship smartwatch with a durable aluminum frame and crash detection.",
        "price_minor": 1_299_900,
        "category": "wearables",
        "quantity": 12,
    },
    {
        "sku": "WATCH-006",
        "name": "Redmi Watch 3",
        "description": "AMOLED display smartwatch with 12-day battery life and Bluetooth calling.",
        "price_minor": 249_900,
        "category": "wearables",
        "quantity": 38,
    },
    {
        "sku": "WATCH-007",
        "name": "boAt Storm Call",
        "description": "Round-dial Bluetooth calling smartwatch with 100+ sports modes.",
        "price_minor": 179_900,
        "category": "wearables",
        "quantity": 42,
    },
    # --- Power (power banks, chargers) ---
    {
        "sku": "POWERBANK-001",
        "name": "Ambrane 10000mAh Power Bank",
        "description": "10,000mAh USB-C power bank with 22.5W fast charging.",
        "price_minor": 129_900,
        "category": "power",
        "quantity": 80,
    },
    {
        "sku": "CHARGER-001",
        "name": "Anker 65W GaN Charger",
        "description": "65W USB-C fast charger, ideal for laptops, tablets, and phones.",
        "price_minor": 179_900,
        "category": "power",
        "quantity": 40,
    },
    {
        "sku": "POWERBANK-002",
        "name": "Mi 20000mAh Power Bank",
        "description": "20,000mAh power bank with dual USB-C/USB-A fast charging output.",
        "price_minor": 199_900,
        "category": "power",
        "quantity": 50,
    },
    # --- Accessories ---
    {
        "sku": "CASE-001",
        "name": "boAt Silicone Case for Airdopes",
        "description": "Silicone protective case designed for true wireless earbuds.",
        "price_minor": 29_900,
        "category": "accessories",
        "quantity": 100,
    },
    {
        "sku": "ADAPTER-001",
        "name": "pTron USB-C to 3.5mm Adapter",
        "description": "USB-C to 3.5mm adapter for wired listening on the go.",
        "price_minor": 39_900,
        "category": "accessories",
        "quantity": 60,
    },
    {
        "sku": "STRAP-001",
        "name": "boAt Adjustable Watch Strap",
        "description": "Adjustable silicone replacement strap compatible with most smartwatches.",
        "price_minor": 49_900,
        "category": "accessories",
        "quantity": 70,
    },
    {
        "sku": "CABLE-001",
        "name": "Portronics Konnect Braided USB-C Cable",
        "description": "1-meter braided USB-C charging cable rated for 60W fast charging.",
        "price_minor": 39_900,
        "category": "accessories",
        "quantity": 100,
    },
    {
        "sku": "CABLE-002",
        "name": "boAt Deuce USB-C to Lightning Cable",
        "description": "Dual-connector charging cable for USB-C and Lightning devices.",
        "price_minor": 59_900,
        "category": "accessories",
        "quantity": 65,
    },
]

# TechHub's catalog: deliberately the same product types as UrbanNest's core
# line, at different prices and from a different brand mix, so a buyer
# agent comparing merchants has a real decision to make (plan.md's
# multi-merchant demo scenario) rather than choosing between two identical
# listings.
TECHHUB_PRODUCTS = [
    # --- Audio (earbuds) ---
    {
        "sku": "TH-EARBUDS-001",
        "name": "Noise Buds VS104 Plus",
        "description": "True wireless earbuds with quad-mic ENC and a low-latency gaming mode.",
        "price_minor": 229_900,
        "category": "audio",
        "quantity": 60,
    },
    {
        "sku": "TH-EARBUDS-002",
        "name": "boAt Airdopes 100",
        "description": "Budget-friendly true wireless earbuds with 8 hours of playtime per charge.",
        "price_minor": 129_900,
        "category": "audio",
        "quantity": 70,
    },
    {
        "sku": "TH-EARBUDS-003",
        "name": "Realme Buds T110",
        "description": "True wireless earbuds with 30 hours total battery and 10mm bass-boost drivers.",
        "price_minor": 179_900,
        "category": "audio",
        "quantity": 50,
    },
    # --- Wearables (smartwatches) ---
    {
        "sku": "TH-WATCH-001",
        "name": "Fire-Boltt Phoenix Pro",
        "description": "AMOLED smartwatch with Bluetooth calling and an AI voice assistant.",
        "price_minor": 269_900,
        "category": "wearables",
        "quantity": 35,
    },
    {
        "sku": "TH-WATCH-002",
        "name": "Noise Pulse 2 Max",
        "description": "1.85-inch HD display smartwatch with Bluetooth calling.",
        "price_minor": 199_900,
        "category": "wearables",
        "quantity": 40,
    },
    # --- Power (power banks, chargers) ---
    {
        "sku": "TH-POWERBANK-001",
        "name": "pTron Dynamo Evo 10000mAh",
        "description": "10,000mAh power bank with 22.5W fast charging and dual output.",
        "price_minor": 139_900,
        "category": "power",
        "quantity": 70,
    },
    {
        "sku": "TH-POWERBANK-002",
        "name": "Ambrane 20000mAh Power Bank",
        "description": "20,000mAh power bank with 20W fast charging across three output ports.",
        "price_minor": 219_900,
        "category": "power",
        "quantity": 45,
    },
    {
        "sku": "TH-CHARGER-001",
        "name": "Zebronics Zeb-CA9210 65W Charger",
        "description": "65W GaN fast charger with one USB-C and one USB-A port.",
        "price_minor": 169_900,
        "category": "power",
        "quantity": 45,
    },
    # --- Accessories ---
    {
        "sku": "TH-CASE-001",
        "name": "Boult Audio Silicone Earbuds Case",
        "description": "Compact silicone protective case for true wireless earbuds.",
        "price_minor": 24_900,
        "category": "accessories",
        "quantity": 90,
    },
    {
        "sku": "TH-CABLE-001",
        "name": "pTron Solero TB301 USB-C Cable",
        "description": "1-meter fast-charging USB-C cable.",
        "price_minor": 19_900,
        "category": "accessories",
        "quantity": 100,
    },
    {
        "sku": "TH-ADAPTER-001",
        "name": "Portronics Konnect Type-C Adapter",
        "description": "USB-C to 3.5mm audio adapter for wired listening.",
        "price_minor": 34_900,
        "category": "accessories",
        "quantity": 60,
    },
    {
        "sku": "TH-STRAP-001",
        "name": "boAt Watch Strap Xtend",
        "description": "Replacement silicone strap compatible with most smartwatches.",
        "price_minor": 39_900,
        "category": "accessories",
        "quantity": 55,
    },
]

MERCHANTS = [
    {"slug": "urbannest", "name": "UrbanNest", "products": URBANNEST_PRODUCTS},
    {"slug": "techhub", "name": "TechHub", "products": TECHHUB_PRODUCTS},
]

DEMO_USER_EMAIL = "demo@agentpay.test"
DEMO_USER_NAME = "AgentPay Demo User"


async def seed() -> None:
    """Idempotently seed both merchants, their catalogs, inventory, and the demo user."""
    factory = get_session_factory()
    async with factory() as session:
        for merchant_spec in MERCHANTS:
            merchant_result = await session.execute(select(Merchant).where(Merchant.slug == merchant_spec["slug"]))
            merchant = merchant_result.scalar_one_or_none()
            if merchant is None:
                merchant = Merchant(slug=merchant_spec["slug"], name=merchant_spec["name"], currency="INR")
                session.add(merchant)
                await session.flush()
                print(f"Created merchant: {merchant.name} ({merchant.id})")
            else:
                print(f"Merchant already exists: {merchant.name} ({merchant.id})")

            for spec in merchant_spec["products"]:
                product_result = await session.execute(select(Product).where(Product.sku == spec["sku"]))
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
                    changed = False
                    for field in ("name", "description", "price_minor", "category"):
                        if getattr(product, field) != spec[field]:
                            setattr(product, field, spec[field])
                            changed = True
                    if changed:
                        await session.flush()
                        print(f"  Updated product: {product.name} ({spec['sku']})")
                    else:
                        print(f"  Product already exists: {product.name} ({spec['sku']})")

                    inventory_result = await session.execute(select(Inventory).where(Inventory.product_id == product.id))
                    inventory = inventory_result.scalar_one_or_none()
                    if inventory is None:
                        session.add(Inventory(product_id=product.id, quantity=spec["quantity"], reserved_quantity=0))
                        await session.flush()
                    elif inventory.quantity != spec["quantity"]:
                        # Top up to this file's stock level without touching
                        # reserved_quantity, which reflects real in-flight
                        # carts, not something a catalog refresh should reset.
                        inventory.quantity = spec["quantity"]
                        await session.flush()

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
