"""
Purpose: Pydantic schemas for the merchant-listing API (plan.md Section 18).

Lets the storefront's landing page show every AI-transactable merchant
(currently UrbanNest and TechHub) without hardcoding their names/slugs on
the frontend.
"""
from pydantic import BaseModel


class MerchantResponse(BaseModel):
    """One merchant a buyer (or buyer agent) can shop at."""

    merchant_id: str
    slug: str
    name: str
    currency: str
