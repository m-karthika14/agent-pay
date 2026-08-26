"""
Purpose: Pydantic schemas for the machine-readable product catalog API.

Fields match plan.md's "Catalog APIs" description (Section 2 of final.md /
plan.md Section 18/19): product_id, name, price, currency, category,
availability, delivery, return_policy. `delivery` and `return_policy` are not
per-product database columns (plan.md Section 8.3 defines the products
table without them) — each demo merchant has one uniform delivery/return
policy, so these are attached as constants by app.catalog.service rather
than invented as new schema columns.

`merchant_name`/`merchant_slug` (added alongside the bare `merchant_id` UUID
when AgentPay grew a second merchant) let a caller comparing products across
merchants -- e.g. a buyer agent choosing between UrbanNest and TechHub --
attribute each result to a merchant by name without a second lookup.
"""
from pydantic import BaseModel


class ProductResponse(BaseModel):
    """A single catalog product, as returned by GET /api/products and /api/products/{id}."""

    product_id: str
    merchant_id: str
    merchant_name: str
    merchant_slug: str
    sku: str
    name: str
    description: str
    price_minor: int
    currency: str
    category: str
    availability: str
    delivery: str
    return_policy: str


class InventoryResponse(BaseModel):
    """Stock level for a single product, returned by GET /api/products/{id}/inventory."""

    product_id: str
    quantity: int
    reserved_quantity: int
    available_quantity: int
