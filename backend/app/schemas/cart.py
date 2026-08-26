"""
Purpose: Pydantic schemas for cart requests/responses.

Covers only the Phase 2 mutable-cart lifecycle (create/add/update/remove/get).
Freeze/hash fields exist on the response shape because they're columns on
the Cart model, but they stay null until Phase 3 implements freeze_cart().
"""
from datetime import datetime

from pydantic import BaseModel, Field


class CreateCartRequest(BaseModel):
    """Request body for POST /api/carts."""

    user_id: str
    merchant_id: str
    currency: str = Field(default="INR", description="ISO 4217 currency code")


class AddCartItemRequest(BaseModel):
    """Request body for POST /api/carts/{cart_id}/items."""

    product_id: str
    quantity: int = Field(gt=0)


class UpdateCartItemRequest(BaseModel):
    """Request body for PATCH /api/carts/{cart_id}/items/{item_id}."""

    quantity: int = Field(gt=0)


class CartItemResponse(BaseModel):
    """A single line item within a cart."""

    item_id: str
    product_id: str
    product_name: str
    quantity: int
    unit_price_minor: int
    line_total_minor: int


class CartResponse(BaseModel):
    """A full cart with its line items."""

    cart_id: str
    user_id: str
    merchant_id: str
    status: str
    currency: str
    subtotal_minor: int
    frozen_at: datetime | None
    frozen_hash: str | None
    mandate_id: str | None = Field(
        default=None, description='Business-facing mandate_id (e.g. "M-001") that froze this cart, if any.'
    )
    items: list[CartItemResponse]
