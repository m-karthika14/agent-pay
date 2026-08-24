"""
Purpose: Razorpay webhook endpoint (plan.md Section 16.4).

This route is intentionally thin: it reads the raw request body and
relevant headers and hands them straight to app.payments.webhooks.
handle_webhook(), which does the real verify/dedupe/dispatch work. Reading
the RAW body here (not a parsed model) is required -- signature
verification must be computed over the exact bytes Razorpay sent, before
any framework re-serialization could change them (plan.md Section 16.3).
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.payments.webhooks import handle_webhook

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/razorpay")
async def razorpay_webhook(request: Request, session: AsyncSession = Depends(get_db_session)) -> JSONResponse:
    """
    Receive and process a Razorpay webhook delivery.

    Returns HTTP 200 for both newly-processed and duplicate-but-valid
    events (so Razorpay does not retry unnecessarily), and HTTP 400 for an
    invalid signature or malformed payload.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    header_event_id = request.headers.get("X-Razorpay-Event-Id")

    result = await handle_webhook(session, raw_body, signature, header_event_id)

    return JSONResponse(status_code=result.http_status, content={"success": result.accepted, "detail": result.detail})
