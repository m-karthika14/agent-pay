"""
Purpose: Mutable-cart API routes (plan.md Section 18 — Cart).

Thin HTTP layer over app.carts.service — the same functions MCP's future
create_cart()/add_to_cart() tools (Phase 5) will call directly, so REST and
MCP never diverge into two cart implementations (plan.md Section 17).
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.carts import service as carts_service
from app.db.session import get_db_session
from app.schemas.cart import (
    AddCartItemRequest,
    CartResponse,
    CreateCartRequest,
    UpdateCartItemRequest,
)
from app.schemas.common import ApiSuccessResponse

router = APIRouter(prefix="/api/carts", tags=["carts"])


@router.post("", response_model=ApiSuccessResponse[CartResponse])
async def create_cart(
    body: CreateCartRequest, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[CartResponse]:
    """Create a new, empty, OPEN cart."""
    cart = await carts_service.create_cart(
        session, uuid.UUID(body.user_id), uuid.UUID(body.merchant_id), body.currency
    )
    return ApiSuccessResponse(data=cart)


@router.get("/{cart_id}", response_model=ApiSuccessResponse[CartResponse])
async def get_cart(
    cart_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[CartResponse]:
    """Fetch a cart with its current line items."""
    cart = await carts_service.get_cart(session, cart_id)
    return ApiSuccessResponse(data=cart)


@router.post("/{cart_id}/items", response_model=ApiSuccessResponse[CartResponse])
async def add_cart_item(
    cart_id: uuid.UUID, body: AddCartItemRequest, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[CartResponse]:
    """Add a product to an OPEN cart (merges into an existing line if already present)."""
    cart = await carts_service.add_cart_item(
        session, cart_id, uuid.UUID(body.product_id), body.quantity
    )
    return ApiSuccessResponse(data=cart)


@router.patch("/{cart_id}/items/{item_id}", response_model=ApiSuccessResponse[CartResponse])
async def update_cart_item(
    cart_id: uuid.UUID,
    item_id: uuid.UUID,
    body: UpdateCartItemRequest,
    session: AsyncSession = Depends(get_db_session),
) -> ApiSuccessResponse[CartResponse]:
    """Change a line item's quantity in an OPEN cart."""
    cart = await carts_service.update_cart_item_quantity(session, cart_id, item_id, body.quantity)
    return ApiSuccessResponse(data=cart)


@router.delete("/{cart_id}/items/{item_id}", response_model=ApiSuccessResponse[CartResponse])
async def remove_cart_item(
    cart_id: uuid.UUID, item_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)
) -> ApiSuccessResponse[CartResponse]:
    """Remove a line item from an OPEN cart."""
    cart = await carts_service.remove_cart_item(session, cart_id, item_id)
    return ApiSuccessResponse(data=cart)
