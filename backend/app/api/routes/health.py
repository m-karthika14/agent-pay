"""
Purpose: Liveness endpoint for AgentPay's backend (plan.md Section 18 — Health).
"""
from fastapi import APIRouter

from app.schemas.common import ApiSuccessResponse

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=ApiSuccessResponse[dict])
async def health_check() -> ApiSuccessResponse[dict]:
    """Return a trivial 200 OK payload confirming the API process is up."""
    return ApiSuccessResponse(data={"status": "ok"})
