"""
Purpose: Catalog API routes (plan.md Section 18 — Products).

Thin HTTP layer: all real logic lives in app.catalog.service, so MCP's
search_products()/get_product() tools call the exact same functions rather
than duplicating catalog logic (plan.md Section 17's "one source of truth"
rule).
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import service as catalog_service
from app.db.session import get_db_session
from app.merchants.service import get_merchant_by_slug
from app.schemas.common import ApiSuccessResponse, NotFoundError
from app.schemas.product import InventoryResponse, ProductResponse

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=ApiSuccessResponse[list[ProductResponse]])
async def list_products(
    merchant: str | None = Query(default=None, description='Merchant slug, e.g. "techhub" -- omit to search every merchant.'),
    session: AsyncSession = Depends(get_db_session),
) -> ApiSuccessResponse[list[ProductResponse]]:
    """List active products -- every demo merchant's, or just one merchant's if `merchant` is given."""
    merchant_id = None
    if merchant is not None:
        merchant_row = await get_merchant_by_slug(session, merchant)
        if merchant_row is None:
            raise NotFoundError("MERCHANT_NOT_FOUND", f"No merchant with slug '{merchant}'.")
        merchant_id = merchant_row.id
    products = await catalog_service.list_products(session, merchant_id)
    return ApiSuccessResponse(data=products)


@router.get("/{product_id}", response_model=ApiSuccessResponse[ProductResponse])
async def get_product(
    product_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[ProductResponse]:
    """Fetch a single product by id."""
    product = await catalog_service.get_product(session, product_id)
    return ApiSuccessResponse(data=product)


@router.get("/{product_id}/inventory", response_model=ApiSuccessResponse[InventoryResponse])
async def get_product_inventory(
    product_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[InventoryResponse]:
    """Fetch current stock level for a product."""
    inventory = await catalog_service.get_inventory(session, product_id)
    return ApiSuccessResponse(data=inventory)
