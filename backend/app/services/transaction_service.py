"""
Purpose: Read-only transaction lookups, including a transaction's full
audit trace (plan.md Section 18 — Transactions, Section 45).

This module only reads. All mutation of transactions happens in
app.payments.reconciliation, driven by webhook events.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.audit_event import AuditEvent
from app.db.models.transaction import Transaction
from app.schemas.common import NotFoundError
from app.schemas.payment import TransactionResponse, TransactionTraceEvent, TransactionTraceResponse


def _to_transaction_response(row: Transaction) -> TransactionResponse:
    return TransactionResponse(
        transaction_id=str(row.id),
        order_id=str(row.order_id),
        razorpay_payment_id=row.razorpay_payment_id,
        status=row.status,
        failure_code=row.failure_code,
        failure_message=row.failure_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def get_transaction(session: AsyncSession, transaction_id: uuid.UUID) -> TransactionResponse:
    """
    Fetch a single transaction by id.

    Args:
        session: Active AsyncSession.
        transaction_id: The transaction to fetch.

    Returns:
        TransactionResponse.

    Raises:
        NotFoundError: If no transaction exists with that id.
    """
    row = await session.get(Transaction, transaction_id)
    if row is None:
        raise NotFoundError("TRANSACTION_NOT_FOUND", f"No transaction with id '{transaction_id}'.")
    return _to_transaction_response(row)


async def get_transaction_trace(session: AsyncSession, transaction_id: uuid.UUID) -> TransactionTraceResponse:
    """
    Fetch a transaction plus every audit event recorded against its order,
    in chronological order -- the full "why was this allowed/blocked" trace
    (plan.md Section 49 — Observability for demo).

    Args:
        session: Active AsyncSession.
        transaction_id: The transaction to trace.

    Returns:
        TransactionTraceResponse with the transaction and its ordered events.

    Raises:
        NotFoundError: If no transaction exists with that id.
    """
    row = await session.get(Transaction, transaction_id)
    if row is None:
        raise NotFoundError("TRANSACTION_NOT_FOUND", f"No transaction with id '{transaction_id}'.")

    events_result = await session.execute(
        select(AuditEvent).where(AuditEvent.order_id == row.order_id).order_by(AuditEvent.sequence)
    )
    events = [
        TransactionTraceEvent(
            event_type=event.event_type,
            decision=event.decision,
            reason_code=event.reason_code,
            created_at=event.created_at,
        )
        for event in events_result.scalars().all()
    ]

    return TransactionTraceResponse(transaction=_to_transaction_response(row), events=events)
