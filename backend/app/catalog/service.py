"""
Purpose: Read-only product catalog and inventory lookups.

Responsibilities:
- List/fetch active products, formatted as the machine-readable catalog
  shape MCP and the frontend both consume (plan.md Section 2 / Section 17 —
  "there must be one source of truth" between REST and MCP).
- Fetch a product's current inventory level.

This module only reads from the database; it never mutates products or
inventory (that belongs to future admin/ops tooling, out of scope here).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DEFAULT_DELIVERY_POLICY, DEFAULT_RETURN_POLICY, URBANNEST_SLUG
from app.db.models.inventory import Inventory
from app.db.models.merchant import Merchant
from app.db.models.product import Product
from app.schemas.common import NotFoundError
from app.schemas.product import InventoryResponse, ProductResponse


def _to_product_response(product: Product, inventory: Inventory | None) -> ProductResponse:
    """Build the API-facing ProductResponse from a Product row and its (optional) inventory."""
    available = inventory.quantity - inventory.reserved_quantity if inventory else 0
    availability = "in_stock" if available > 0 else "out_of_stock"
    return ProductResponse(
        product_id=str(product.id),
        merchant_id=str(product.merchant_id),
        sku=product.sku,
        name=product.name,
        description=product.description,
        price_minor=product.price_minor,
        currency=product.currency,
        category=product.category,
        availability=availability,
        delivery=DEFAULT_DELIVERY_POLICY,
        return_policy=DEFAULT_RETURN_POLICY,
    )


async def list_products(session: AsyncSession) -> list[ProductResponse]:
    """
    List all active products in the UrbanNest catalog.

    Scoped to the one real demo merchant (URBANNEST_SLUG), not every
    Product row in the database -- the integration test suite creates its
    own isolated, throwaway merchant+product fixtures per test (see e.g.
    tests/integration/test_cart_checkout.py's `_create_fixture_data()`),
    and without this filter every one of those would leak into what's
    supposed to be a single-merchant storefront/MCP catalog.

    Args:
        session: Active AsyncSession.

    Returns:
        ProductResponse list, one per active UrbanNest product, each
        carrying its current availability derived from the inventory table.
        Empty if the UrbanNest merchant hasn't been seeded yet
        (scripts/seed_database.py), rather than an error.
    """
    result = await session.execute(
        select(Product, Inventory)
        .join(Merchant, Merchant.id == Product.merchant_id)
        .outerjoin(Inventory, Inventory.product_id == Product.id)
        .where(Product.is_active.is_(True), Merchant.slug == URBANNEST_SLUG)
        .order_by(Product.name)
    )
    return [_to_product_response(product, inventory) for product, inventory in result.all()]


async def get_product(session: AsyncSession, product_id: uuid.UUID) -> ProductResponse:
    """
    Fetch a single active product by id.

    Args:
        session: Active AsyncSession.
        product_id: Internal UUID of the product.

    Returns:
        ProductResponse for the product.

    Raises:
        NotFoundError: If no active product exists with that id.
    """
    result = await session.execute(
        select(Product, Inventory)
        .outerjoin(Inventory, Inventory.product_id == Product.id)
        .where(Product.id == product_id, Product.is_active.is_(True))
    )
    row = result.first()
    if row is None:
        raise NotFoundError("PRODUCT_NOT_FOUND", f"No active product with id '{product_id}'.")
    product, inventory = row
    return _to_product_response(product, inventory)


async def get_inventory(session: AsyncSession, product_id: uuid.UUID) -> InventoryResponse:
    """
    Fetch the current stock level for a product.

    Args:
        session: Active AsyncSession.
        product_id: Internal UUID of the product.

    Returns:
        InventoryResponse describing quantity, reserved_quantity, and the
        derived available_quantity.

    Raises:
        NotFoundError: If no inventory row exists for that product.
    """
    result = await session.execute(select(Inventory).where(Inventory.product_id == product_id))
    inventory = result.scalar_one_or_none()
    if inventory is None:
        raise NotFoundError(
            "INVENTORY_NOT_FOUND", f"No inventory record for product '{product_id}'."
        )
    return InventoryResponse(
        product_id=str(product_id),
        quantity=inventory.quantity,
        reserved_quantity=inventory.reserved_quantity,
        available_quantity=inventory.quantity - inventory.reserved_quantity,
    )
