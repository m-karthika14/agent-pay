"""
Purpose: Read-only audit log lookups for the API layer (plan.md Section
18 — Audit, Section 23.3).

This module only reads app.audit's already-built pieces (app.audit.service
for storage shape, app.audit.verifier for chain verification) -- it never
appends events or reimplements hashing logic itself (plan.md's "one source
of truth" rule).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.verifier import verify_chain
from app.db.models.audit_event import AuditEvent
from app.db.models.order import Order
from app.db.models.transaction import Transaction
from app.mandates.service import get_mandate_by_business_id
from app.schemas.audit import AuditEventRecord, ChainVerificationResult
from app.schemas.common import NotFoundError


def _to_record(event: AuditEvent) -> AuditEventRecord:
    return AuditEventRecord(
        event_id=event.event_id,
        event_type=event.event_type,
        actor_type=event.actor_type,
        payload_hash=event.payload_hash,
        payload=event.payload_json,
        previous_hash=event.previous_hash,
        event_hash=event.event_hash,
        decision=event.decision,
        reason_code=event.reason_code,
        mandate_id=str(event.mandate_id) if event.mandate_id else None,
        order_id=str(event.order_id) if event.order_id else None,
        user_id=str(event.user_id) if event.user_id else None,
        created_at=event.created_at,
    )


async def get_events_for_transaction(session: AsyncSession, transaction_id: uuid.UUID) -> list[AuditEventRecord]:
    """
    Fetch a transaction's own audit events, in chain order, with full hash
    fields (plan.md Section 24 "Audit viewer": event, timestamp, decision,
    reason, previous_hash, current_hash).

    Filtered by mandate_id, not order_id: checkout_service.py's pre-order
    events (HARD_POLICY_PASSED, CART_FROZEN, MERCHANT_PROPOSAL_CREATED,
    INTENT_GATE_*, CART_REVALIDATION_*) are recorded before any Order row
    exists, so they only ever carry mandate_id -- only later events
    (RAZORPAY_ORDER_CREATED onward) also carry order_id. mandate_id is set
    on every event throughout the whole flow, so it's the complete key.

    Args:
        session: Active AsyncSession.
        transaction_id: The transaction whose mandate's events to fetch.

    Returns:
        AuditEventRecord list, oldest first.

    Raises:
        NotFoundError: If no transaction, or its order, exists.
    """
    transaction_row = await session.get(Transaction, transaction_id)
    if transaction_row is None:
        raise NotFoundError("TRANSACTION_NOT_FOUND", f"No transaction with id '{transaction_id}'.")

    order_row = await session.get(Order, transaction_row.order_id)
    if order_row is None:
        raise NotFoundError("ORDER_NOT_FOUND", f"No order with id '{transaction_row.order_id}'.")

    result = await session.execute(
        select(AuditEvent).where(AuditEvent.mandate_id == order_row.mandate_id).order_by(AuditEvent.sequence)
    )
    return [_to_record(event) for event in result.scalars().all()]


async def verify_full_chain(session: AsyncSession, transaction_id: uuid.UUID) -> ChainVerificationResult:
    """
    Verify AgentPay's entire hash-chained audit log (plan.md Section 23.3).

    The chain is global -- every event links to whichever event preceded it
    system-wide (app.audit.service.get_latest_event_hash has no per-mandate
    or per-order scoping) -- so a single transaction's events cannot be
    verified in isolation from a filtered slice; verifying "this
    transaction's chain" means verifying the whole ledger it's part of.
    Mirrors scripts/verify_audit_chain.py exactly.

    Args:
        session: Active AsyncSession.
        transaction_id: The transaction whose audit page triggered this
            check -- validated to exist (so a bogus id 404s) even though
            the verification itself is necessarily system-wide.

    Returns:
        ChainVerificationResult for the complete audit log.

    Raises:
        NotFoundError: If no transaction exists with that id.
    """
    if await session.get(Transaction, transaction_id) is None:
        raise NotFoundError("TRANSACTION_NOT_FOUND", f"No transaction with id '{transaction_id}'.")

    result = await session.execute(select(AuditEvent).order_by(AuditEvent.sequence))
    events = list(result.scalars().all())
    return verify_chain(events)


async def get_events_for_mandate(session: AsyncSession, mandate_id: str) -> list[AuditEventRecord]:
    """
    Fetch every audit event recorded against one mandate, in chain order,
    identified by its business-facing mandate_id (e.g. "M-001").

    Unlike get_events_for_transaction (which needs a Transaction/Order row
    to already exist), this works from the moment a mandate is created --
    before any cart is even frozen under it -- so it's what a live
    "watch this purchase happen" activity panel polls while a buyer agent
    is still shopping, not just after a payment attempt exists.

    Args:
        session: Active AsyncSession.
        mandate_id: Business-facing mandate_id.

    Returns:
        AuditEventRecord list, oldest first.

    Raises:
        NotFoundError: If no mandate exists with that id.
    """
    mandate_row = await get_mandate_by_business_id(session, mandate_id)
    if mandate_row is None:
        raise NotFoundError("MANDATE_NOT_FOUND", f"No mandate with id '{mandate_id}'.")

    result = await session.execute(
        select(AuditEvent).where(AuditEvent.mandate_id == mandate_row.id).order_by(AuditEvent.sequence)
    )
    return [_to_record(event) for event in result.scalars().all()]


async def get_events_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[AuditEventRecord]:
    """
    Fetch every audit event recorded directly against one buyer, in chain
    order -- includes events that predate any mandate (CART_CREATED,
    AUTHORIZATION_REQUESTED/APPROVED/REJECTED), which get_events_for_mandate
    can never see since they carry no mandate_id.

    Note this does NOT include a mandate's own later events (HARD_POLICY_
    PASSED, CART_FROZEN, etc.) -- those still only carry mandate_id, not
    user_id, so watching a purchase all the way through still means pairing
    this with get_events_for_mandate once a mandate exists.

    Args:
        session: Active AsyncSession.
        user_id: The buyer's internal User.id.

    Returns:
        AuditEventRecord list, oldest first. Empty if this user has no
        pre-mandate events yet, not an error.
    """
    result = await session.execute(
        select(AuditEvent).where(AuditEvent.user_id == user_id).order_by(AuditEvent.sequence)
    )
    return [_to_record(event) for event in result.scalars().all()]


async def get_recent_events(session: AsyncSession, limit: int) -> list[AuditEventRecord]:
    """
    Fetch the most recent audit events system-wide (plan.md Section 18
    `GET /api/console/events` -- a live feed across all transactions).

    Args:
        session: Active AsyncSession.
        limit: Maximum number of events to return, most recent first.

    Returns:
        AuditEventRecord list, newest first.
    """
    result = await session.execute(select(AuditEvent).order_by(AuditEvent.sequence.desc()).limit(limit))
    return [_to_record(event) for event in result.scalars().all()]
