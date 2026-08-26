"""
Purpose: Merchant-listing API route (plan.md Section 18) -- the storefront
landing page's "which merchant do you want to shop" picker.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.merchants.service import list_merchants
from app.schemas.common import ApiSuccessResponse
from app.schemas.merchant import MerchantResponse

router = APIRouter(prefix="/api/merchants", tags=["merchants"])


@router.get("", response_model=ApiSuccessResponse[list[MerchantResponse]])
async def list_merchants_route(session: AsyncSession = Depends(get_db_session)) -> ApiSuccessResponse[list[MerchantResponse]]:
    """List every AI-transactable demo merchant."""
    merchants = await list_merchants(session)
    return ApiSuccessResponse(data=merchants)
