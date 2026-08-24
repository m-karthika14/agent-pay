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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import append_event
from app.db.models.mandate import Mandate
from app.db.models.order import Order
from app.db.models.transaction import Transaction
from app.mandates.service import consume_mandate
from app.payments.razorpay_client import fetch_order, fetch_payment
from app.schemas.audit import AuditEventInput


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
    delayed webhook.

    Args:
        session: Active AsyncSession.
        order: The order to reconcile. Must have razorpay_order_id set.

    This is a manual/scripted reconciliation helper (e.g. for
    scripts/run_smoke_test.py or ops use), not part of the webhook hot
    path -- the webhook handlers above are the primary state-update path.
    """
    razorpay_order = fetch_order(order.razorpay_order_id)

    result = await session.execute(select(Transaction).where(Transaction.order_id == order.id))
    transaction = result.scalar_one_or_none()

    if razorpay_order.get("status") == "paid" and transaction is not None and transaction.status != "CAPTURED":
        payments_result = await session.execute(
            select(Transaction.razorpay_payment_id).where(Transaction.order_id == order.id)
        )
        payment_id = payments_result.scalar_one_or_none()
        if payment_id:
            payment = fetch_payment(payment_id)
            if payment.get("status") == "captured":
                transaction.status = "CAPTURED"
                order.status = "PAID"
                await session.flush()
