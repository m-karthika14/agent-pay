"""
Purpose: ORM model for the hash-chained audit log.

Each row's `event_hash` is a SHA-256 hash over its own canonical content plus
`previous_hash` (the prior event's hash), forming a tamper-evident chain
(plan.md Section 23.2). Rows in this table are never updated or deleted by
application code after creation — the chain's integrity depends on that.

This model only defines the schema; hashing and chain-append logic live in
app.audit.hashing / app.audit.service so they can be unit tested without a
live database.
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditEvent(Base):
    """One tamper-evident, hash-chained entry in the AgentPay audit log."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Strictly monotonic append order. Postgres's now()/CURRENT_TIMESTAMP
    # returns transaction-start time, so several events appended within one
    # transaction can share an identical created_at -- unsuitable for
    # ordering a hash chain, where link order must be unambiguous. This
    # DB-generated identity column is the authoritative chain order;
    # created_at remains only for human-readable display.
    sequence: Mapped[int] = mapped_column(
        BigInteger, Identity(always=True), unique=True, nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    mandate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mandates.id"), nullable=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("orders.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # Which side of the system produced this event, e.g. "SYSTEM", "USER",
    # "MERCHANT_AGENT", "INTENT_GATE" — kept as a plain string since the full
    # actor taxonomy is finalized when those components are built.
    actor_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    decision: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
