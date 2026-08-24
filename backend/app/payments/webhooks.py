"""
Purpose: Process incoming Razorpay webhook deliveries (plan.md Section 16.4).

Responsibilities, in the exact order plan.md specifies:
    1. (caller reads the raw request body)
    2. verify X-Razorpay-Signature over the raw body
    3. read an event identifier
    4. reject duplicate event ids
    5. record minimal event/audit information
    6. (caller returns HTTP 200 quickly)
    7. reconcile/update state safely

This module is a thin dispatcher: the actual Order/Transaction mutation
logic lives in app.payments.reconciliation, so this file only verifies,
parses, deduplicates, and routes to the right handler.

Event-id note: Razorpay does not always guarantee a single canonical
top-level "event id" field across all webhook payload shapes/versions. To
make duplicate-detection robust either way, this module prefers the
`X-Razorpay-Event-Id` header when Razorpay sends one, and otherwise derives
a deterministic id from the event type + the relevant entity id (a given
payment can only be captured/failed once, so `"payment.captured:pay_xxx"`
is itself a stable, unique identifier for that occurrence).
"""
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.transaction import Transaction
from app.payments import reconciliation
from app.payments.signatures import verify_webhook_signature


@dataclass
class WebhookResult:
    """Outcome of processing one webhook delivery."""

    accepted: bool
    http_status: int
    detail: str


def _extract_event_id(headers_event_id: str | None, event_type: str, payload: dict[str, Any]) -> str:
    """Determine a stable event id for this webhook delivery (see module docstring)."""
    if headers_event_id:
        return headers_event_id

    entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    entity_id = entity.get("id", "unknown")
    return f"{event_type}:{entity_id}"


async def _is_duplicate_event(session: AsyncSession, event_id: str) -> bool:
    """Check whether this exact event id has already been processed."""
    result = await session.execute(
        select(Transaction.id).where(Transaction.razorpay_event_id == event_id)
    )
    return result.scalar_one_or_none() is not None


async def handle_webhook(
    session: AsyncSession, raw_body: bytes, signature: str, header_event_id: str | None = None
) -> WebhookResult:
    """
    Verify, deduplicate, and dispatch one Razorpay webhook delivery.

    Args:
        session: Active AsyncSession.
        raw_body: The exact raw request body bytes.
        signature: The `X-Razorpay-Signature` header value.
        header_event_id: The `X-Razorpay-Event-Id` header value, if present.

    Returns:
        WebhookResult. `accepted=False` with http_status=400 means the
        signature was invalid -- the caller should NOT return 200 for that
        (an invalid signature is a real security failure, not routine
        webhook noise). `accepted=True` covers both "processed" and
        "duplicate, already processed" -- both get HTTP 200 so Razorpay
        does not retry unnecessarily (plan.md Section 16.4 point 6).
    """
    if not verify_webhook_signature(raw_body, signature):
        return WebhookResult(accepted=False, http_status=400, detail="Invalid webhook signature.")

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        return WebhookResult(accepted=False, http_status=400, detail="Malformed webhook payload.")

    event_type = payload.get("event", "unknown")
    event_id = _extract_event_id(header_event_id, event_type, payload)

    if await _is_duplicate_event(session, event_id):
        return WebhookResult(accepted=True, http_status=200, detail=f"Duplicate event '{event_id}' ignored.")

    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    razorpay_order_id = payment_entity.get("order_id")
    razorpay_payment_id = payment_entity.get("id")

    if event_type == "payment.captured" and razorpay_order_id:
        await reconciliation.handle_payment_captured(session, razorpay_order_id, razorpay_payment_id, event_id)
    elif event_type == "payment.failed" and razorpay_order_id:
        await reconciliation.handle_payment_failed(
            session,
            razorpay_order_id,
            razorpay_payment_id,
            event_id,
            failure_code=payment_entity.get("error_code"),
            failure_message=payment_entity.get("error_description"),
        )
    else:
        await reconciliation.handle_unknown_event(session, event_type, event_id)

    return WebhookResult(accepted=True, http_status=200, detail=f"Processed event '{event_id}'.")
