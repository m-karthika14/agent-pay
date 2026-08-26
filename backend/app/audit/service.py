"""
Purpose: Append events to AgentPay's hash-chained audit log.

Responsibilities:
- Build a fully-hashed AuditEventRecord from caller-supplied event content,
  chaining it to the current latest event.
- Persist that record as a new AuditEvent row.

This is the ONLY module allowed to write to the `audit_events` table -
every other part of the system that needs to record a decision calls
append_event() rather than constructing AuditEvent rows directly, so the
hash chain can never accidentally be built inconsistently.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.hashing import hash_event, hash_payload
from app.db.models.audit_event import AuditEvent
from app.schemas.audit import AuditEventInput, AuditEventRecord


def build_audit_event(event: AuditEventInput, previous_hash: str | None) -> AuditEventRecord:
    """
    Build a fully-hashed audit event record, given the current chain tip.

    Args:
        event: Caller-supplied event content (type, actor, payload, etc.).
        previous_hash: event_hash of the current latest event in the chain,
            or None if this is the first event ever recorded.

    Returns:
        AuditEventRecord with a freshly generated event_id and computed
        payload_hash / event_hash. This is a pure function — no I/O.
    """
    payload_hash = hash_payload(event.payload)
    event_hash = hash_event(payload_hash, previous_hash)
    return AuditEventRecord(
        event_id=f"evt_{uuid.uuid4().hex}",
        event_type=event.event_type,
        actor_type=event.actor_type,
        payload_hash=payload_hash,
        previous_hash=previous_hash,
        event_hash=event_hash,
        decision=event.decision,
        reason_code=event.reason_code,
        mandate_id=event.mandate_id,
        order_id=event.order_id,
        user_id=event.user_id,
    )


async def get_latest_event_hash(session: AsyncSession) -> str | None:
    """
    Return the event_hash of the most recently appended audit event.

    Returns:
        The latest event_hash, or None if the audit log is empty (the next
        event appended will be the first link in the chain).
    """
    result = await session.execute(
        select(AuditEvent.event_hash).order_by(AuditEvent.sequence.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def append_event(session: AsyncSession, event: AuditEventInput) -> AuditEvent:
    """
    Append a new event to the audit hash chain and persist it.

    Args:
        session: Active AsyncSession. The caller is responsible for
            committing (or letting the surrounding transaction commit) —
            this keeps append_event() composable within a larger
            multi-step transaction (e.g. "verify mandate, then audit the
            result, then commit once").
        event: The event content to record.

    Returns:
        The persisted AuditEvent ORM row (flushed, with its generated id).
    """
    previous_hash = await get_latest_event_hash(session)
    record = build_audit_event(event, previous_hash)

    row = AuditEvent(
        event_id=record.event_id,
        mandate_id=uuid.UUID(record.mandate_id) if record.mandate_id else None,
        order_id=uuid.UUID(record.order_id) if record.order_id else None,
        user_id=uuid.UUID(record.user_id) if record.user_id else None,
        event_type=record.event_type,
        actor_type=record.actor_type,
        payload_hash=record.payload_hash,
        payload_json=event.payload,
        previous_hash=record.previous_hash,
        event_hash=record.event_hash,
        decision=record.decision,
        reason_code=record.reason_code,
        created_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    return row
