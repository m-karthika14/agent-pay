"""
Purpose: Reconcile AgentPay's Order/Transaction state with Razorpay payment
events (plan.md Section 16.5).

Responsibilities:
- handle_payment_captured(): mark the transaction/order successful and,
  critically, consume the mandate here -- not at checkout/freeze time (see
  app.mandates.service module docstring / Phase 3 design decision). A
  mandate is only "used up" once money has actually moved.
- handle_payment_failed(): mark the transaction/order failed. The mandate
  is NOT consumed, so the buyer can retry with a new cart under the same
  mandate (until it expires or is otherwise exhausted).
- handle_unknown_event(): audit-log any webhook event type AgentPay doesn't
  specifically act on, without treating it as an error.
- reconcile_order_state(): pull the authoritative state directly from
  Razorpay and correct AgentPay's stored state if it has drifted --
  intended for manual/scripted reconciliation, not the webhook hot path.

Per plan.md Section 16.4/24.4: webhook events are not guaranteed to arrive
in a specific order, so every handler here derives the new state from the
event's own data rather than assuming what came before it.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import append_event
from app.db.models.mandate import Mandate
from app.db.models.order import Order
from app.db.models.transaction import Transaction
from app.mandates.service import consume_mandate
from app.payments.razorpay_client import fetch_order, fetch_order_payments
from app.schemas.audit import AuditEventInput
from app.schemas.common import NotFoundError, ValidationError
from app.schemas.payment import OrderSummary


async def _load_order_and_transaction(
    session: AsyncSession, razorpay_order_id: str
) -> tuple[Order, Transaction] | None:
    """Look up the Order + its Transaction row by Razorpay's order id."""
    result = await session.execute(
        select(Order, Transaction)
        .join(Transaction, Transaction.order_id == Order.id)
        .where(Order.razorpay_order_id == razorpay_order_id)
    )
    return result.first()


async def handle_payment_captured(
    session: AsyncSession, razorpay_order_id: str, razorpay_payment_id: str, event_id: str
) -> None:
    """
    Handle a `payment.captured` webhook event: mark the transaction/order
    successful and consume the authorizing mandate.

    Args:
        session: Active AsyncSession.
        razorpay_order_id: The Razorpay order id the payment belongs to.
        razorpay_payment_id: The captured payment's id.
        event_id: Razorpay's event id, stored for webhook-duplicate detection.

    If no matching Order/Transaction is found, this is logged as an
    unknown/unmatched event rather than raising -- a webhook handler must
    never 500 on data it doesn't recognize (plan.md Section 16.4 point 6:
    "return HTTP 200 quickly").
    """
    match = await _load_order_and_transaction(session, razorpay_order_id)
    if match is None:
        await handle_unknown_event(session, "payment.captured", event_id)
        return
    order, transaction = match

    transaction.razorpay_payment_id = razorpay_payment_id
    transaction.status = "CAPTURED"
    transaction.razorpay_event_id = event_id
    order.status = "PAID"
    await session.flush()

    await append_event(
        session,
        AuditEventInput(
            event_type="PAYMENT_CAPTURED",
            actor_type="SYSTEM",
            payload={"order_id": str(order.id), "razorpay_payment_id": razorpay_payment_id},
            order_id=str(order.id),
            mandate_id=str(order.mandate_id),
        ),
    )

    mandate_row = await session.get(Mandate, order.mandate_id)
    if mandate_row is not None:
        await consume_mandate(session, mandate_row)

    await append_event(
        session,
        AuditEventInput(
            event_type="TRANSACTION_COMPLETED",
            actor_type="SYSTEM",
            payload={"order_id": str(order.id)},
            decision="ALLOW",
            order_id=str(order.id),
            mandate_id=str(order.mandate_id),
        ),
    )


async def handle_payment_failed(
    session: AsyncSession,
    razorpay_order_id: str,
    razorpay_payment_id: str | None,
    event_id: str,
    failure_code: str | None,
    failure_message: str | None,
) -> None:
    """
    Handle a `payment.failed` webhook event: mark the transaction/order
    failed. The mandate is left ACTIVE so the buyer can retry.

    Args:
        session: Active AsyncSession.
        razorpay_order_id: The Razorpay order id the payment belongs to.
        razorpay_payment_id: The failed payment's id, if Razorpay assigned one.
        event_id: Razorpay's event id, stored for webhook-duplicate detection.
        failure_code: Razorpay's machine-readable failure reason.
        failure_message: Razorpay's human-readable failure description.
    """
    match = await _load_order_and_transaction(session, razorpay_order_id)
    if match is None:
        await handle_unknown_event(session, "payment.failed", event_id)
        return
    order, transaction = match

    transaction.razorpay_payment_id = razorpay_payment_id
    transaction.status = "FAILED"
    transaction.razorpay_event_id = event_id
    transaction.failure_code = failure_code
    transaction.failure_message = failure_message
    order.status = "PAYMENT_FAILED"
    await session.flush()

    await append_event(
        session,
        AuditEventInput(
            event_type="PAYMENT_FAILED",
            actor_type="SYSTEM",
            payload={"order_id": str(order.id), "failure_code": failure_code},
            decision="BLOCK",
            reason_code=failure_code,
            order_id=str(order.id),
            mandate_id=str(order.mandate_id),
        ),
    )
    await append_event(
        session,
        AuditEventInput(
            event_type="TRANSACTION_BLOCKED",
            actor_type="SYSTEM",
            payload={"order_id": str(order.id)},
            decision="BLOCK",
            reason_code=failure_code,
            order_id=str(order.id),
            mandate_id=str(order.mandate_id),
        ),
    )


async def handle_unknown_event(session: AsyncSession, event_type: str, event_id: str) -> None:
    """
    Record an audit trail entry for a webhook event type AgentPay does not
    specifically act on (e.g. order.paid, refund events).

    Args:
        session: Active AsyncSession.
        event_type: Razorpay's event type string.
        event_id: Razorpay's event id.

    This never raises -- an unrecognized or unmatched event must not turn
    into a webhook failure (plan.md Section 16.4 point 6).
    """
    await append_event(
        session,
        AuditEventInput(
            event_type="RAZORPAY_EVENT_UNHANDLED",
            actor_type="SYSTEM",
            payload={"razorpay_event_type": event_type, "razorpay_event_id": event_id},
        ),
    )


async def reconcile_order_state(session: AsyncSession, order: Order) -> None:
    """
    Pull the authoritative order/payment state directly from Razorpay and
    correct AgentPay's stored state if it has drifted from a missed or
    delayed webhook (e.g. a local dev backend with no public URL for
    Razorpay to deliver the webhook to at all).

    Args:
        session: Active AsyncSession.
        order: The order to reconcile. Must have razorpay_order_id set.

    The captured payment's id is looked up from Razorpay itself
    (fetch_order_payments), never from AgentPay's own Transaction row --
    that field is exactly what's still empty when the webhook never
    arrived, so reading it locally would always find nothing. Once a
    captured payment is found, this delegates to handle_payment_captured()
    -- the same function the webhook route calls -- so a reconciled order
    ends up in byte-for-byte the same state (payment id recorded, audit
    trail, mandate consumption) as if the webhook had actually arrived,
    rather than a second, partial reimplementation of that logic.

    Manual/scripted reconciliation helper (e.g. for ops use, or a
    storefront "check payment status" action), not part of the webhook hot
    path -- the webhook handlers above remain the primary state-update path.
    """
    razorpay_order = fetch_order(order.razorpay_order_id)
    if razorpay_order.get("status") != "paid":
        return

    result = await session.execute(select(Transaction).where(Transaction.order_id == order.id))
    transaction = result.scalar_one_or_none()
    if transaction is None or transaction.status == "CAPTURED":
        return

    payments = fetch_order_payments(order.razorpay_order_id)
    captured_payment = next((p for p in payments if p.get("status") == "captured"), None)
    if captured_payment is None:
        return

    await handle_payment_captured(
        session,
        razorpay_order_id=order.razorpay_order_id,
        razorpay_payment_id=captured_payment["id"],
        event_id=f"reconcile_{captured_payment['id']}",
    )


async def sync_order(session: AsyncSession, order_id: uuid.UUID) -> OrderSummary:
    """
    Re-check one order's payment status directly against Razorpay
    (reconcile_order_state) and return its current state -- the storefront's
    "check payment status" fallback for when Razorpay's webhook can't reach
    a local/unreachable backend (e.g. no public tunnel configured in dev).

    Args:
        session: Active AsyncSession.
        order_id: The order to sync.

    Returns:
        OrderSummary reflecting the order's state after reconciliation
        (unchanged if there was nothing to reconcile, or nothing captured
        yet on Razorpay's side).

    Raises:
        NotFoundError: If no order or its mandate exists with that id.
        ValidationError: If the order has no razorpay_order_id yet (i.e.
            /api/checkout/{cart_id}/complete was never called for it).
    """
    order_row = await session.get(Order, order_id)
    if order_row is None:
        raise NotFoundError("ORDER_NOT_FOUND", f"No order with id '{order_id}'.")
    if order_row.razorpay_order_id is None:
        raise ValidationError(
            "ORDER_NOT_READY", f"Order '{order_id}' has no Razorpay order yet.", retryable=True
        )

    await reconcile_order_state(session, order_row)
    await session.commit()
    await session.refresh(order_row)

    mandate_row = await session.get(Mandate, order_row.mandate_id)
    if mandate_row is None:
        raise NotFoundError("MANDATE_NOT_FOUND", f"No mandate with id '{order_row.mandate_id}'.")

    return OrderSummary(
        order_id=str(order_row.id),
        cart_id=str(order_row.cart_id),
        mandate_id=mandate_row.mandate_id,
        razorpay_order_id=order_row.razorpay_order_id,
        status=order_row.status,
        amount_minor=order_row.amount_minor,
        currency=order_row.currency,
    )
