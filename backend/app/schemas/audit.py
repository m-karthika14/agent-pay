"""
Purpose: Pydantic schemas for the AgentPay hash-chained audit log.

Defines the shape of an audit event before/after hashing, and the result of
verifying a chain of events. Hashing logic itself lives in app.audit.hashing;
this module is pure data shape (plan.md Section 23).
"""
from datetime import datetime

from pydantic import BaseModel


class AuditEventInput(BaseModel):
    """
    The caller-supplied content of a new audit event, before hashing.

    `payload` is an arbitrary JSON-serializable dict describing what
    happened (e.g. {"mandate_id": "M-001", "signature_valid": true}) — it is
    hashed into `payload_hash` but the raw dict itself is not persisted
    (plan.md Section 8.10 only stores the hash, not the raw payload).
    """

    event_type: str
    actor_type: str
    payload: dict
    decision: str | None = None
    reason_code: str | None = None
    mandate_id: str | None = None
    order_id: str | None = None


class AuditEventRecord(BaseModel):
    """
    A fully-hashed audit event, ready to persist as an AuditEvent row.

    Also reused (by app.services.audit_service) to serialize an
    already-persisted row back out over the API for the Merchant Console's
    Audit viewer (plan.md Section 24: "event, timestamp, decision, reason,
    previous_hash, current_hash") -- `created_at` is only known once a row
    is actually persisted, so it stays optional here and is populated by
    the caller reading it back, not by app.audit.service.build_audit_event
    (which runs before the row exists).
    """

    event_id: str
    event_type: str
    actor_type: str
    payload_hash: str
    payload: dict | None = None
    previous_hash: str | None
    event_hash: str
    decision: str | None = None
    reason_code: str | None = None
    mandate_id: str | None = None
    order_id: str | None = None
    created_at: datetime | None = None


class ChainMismatch(BaseModel):
    """Describes the first point at which the audit chain fails to verify."""

    event_id: str
    position: int
    reason: str


class ChainVerificationResult(BaseModel):
    """Result of verifying a sequence of audit events for tamper-evidence."""

    valid: bool
    events_checked: int
    first_mismatch: ChainMismatch | None = None
    verified_at: datetime
