"""
Purpose: Read-only merchant lookups (plan.md Section 18).

Two demo merchants are AI-transactable via AgentPay -- UrbanNest and
TechHub (app.core.constants.DEMO_MERCHANT_SLUGS). This module is the one
place that resolves a merchant by its business-facing slug (e.g. "techhub"),
reused by the catalog API, the MCP tools, and cart creation, so a slug never
gets looked up two different ways.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DEMO_MERCHANT_SLUGS
from app.db.models.merchant import Merchant
from app.schemas.common import NotFoundError
from app.schemas.merchant import MerchantResponse


def _to_merchant_response(merchant: Merchant) -> MerchantResponse:
    return MerchantResponse(
        merchant_id=str(merchant.id), slug=merchant.slug, name=merchant.name, currency=merchant.currency
    )


async def get_merchant_by_slug(session: AsyncSession, slug: str) -> Merchant | None:
    """Fetch a merchant by its business-facing slug (e.g. "techhub"), or None if it doesn't exist."""
    result = await session.execute(select(Merchant).where(Merchant.slug == slug))
    return result.scalar_one_or_none()


async def get_merchant_name(session: AsyncSession, merchant_id: uuid.UUID) -> str:
    """
    Fetch a merchant's display name by its internal id.

    Used by the Merchant Revenue Agent (app.agents.merchant.nodes) to build
    a per-merchant system prompt -- e.g. "You are TechHub's revenue
    optimization agent" -- from a cart's merchant_id, since a cart only
    carries the merchant's internal UUID, not its name.

    Raises:
        NotFoundError: If no merchant exists with that id -- this should
            never happen for a real cart's merchant_id (a foreign key), so
            it signals actual data corruption rather than a normal
            not-found case.
    """
    merchant = await session.get(Merchant, merchant_id)
    if merchant is None:
        raise NotFoundError("MERCHANT_NOT_FOUND", f"No merchant with id '{merchant_id}'.")
    return merchant.name


async def list_merchants(session: AsyncSession) -> list[MerchantResponse]:
    """
    List every AI-transactable demo merchant (plan.md Section 18), for the
    storefront's landing page.

    Scoped to DEMO_MERCHANT_SLUGS, not every Merchant row -- same
    anti-pollution reasoning as app.catalog.service.list_products: the
    integration test suite creates its own throwaway merchant fixtures per
    test, and those must never appear as a real, shoppable storefront.
    """
    result = await session.execute(
        select(Merchant).where(Merchant.slug.in_(DEMO_MERCHANT_SLUGS)).order_by(Merchant.name)
    )
    return [_to_merchant_response(merchant) for merchant in result.scalars().all()]
