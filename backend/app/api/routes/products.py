"""
Purpose: Catalog API routes (plan.md Section 18 — Products).

Thin HTTP layer: all real logic lives in app.catalog.service, so MCP's
future search_products()/get_product() tools (Phase 5) can call the exact
same functions rather than duplicating catalog logic (plan.md Section 17's
"one source of truth" rule).
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog import service as catalog_service
from app.db.session import get_db_session
from app.schemas.common import ApiSuccessResponse
from app.schemas.product import InventoryResponse, ProductResponse

router = APIRouter(prefix="/api/products", tags=["products"])


@router.get("", response_model=ApiSuccessResponse[list[ProductResponse]])
async def list_products(
    session: AsyncSession = Depends(get_db_session),
) -> ApiSuccessResponse[list[ProductResponse]]:
    """List every active product in the catalog."""
    products = await catalog_service.list_products(session)
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
