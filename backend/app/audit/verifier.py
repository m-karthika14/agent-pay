"""
Purpose: Verify the integrity of the AgentPay hash-chained audit log.

Responsibilities:
- Walk an ordered sequence of audit events.
- Recompute each event_hash from (previous_hash, payload_hash) and check it
  matches the stored value.
- Check each event's previous_hash matches the prior event's event_hash.
- Report the first mismatch found (plan.md Section 23.3).

This module is pure: it operates on any sequence of objects exposing the
four chain fields (event_id, payload_hash, previous_hash, event_hash), so it
can be unit tested with plain fixtures and reused unchanged by
scripts/verify_audit_chain.py against real database rows.
"""
from datetime import UTC, datetime
from typing import Protocol

from app.audit.hashing import hash_event
from app.schemas.audit import ChainMismatch, ChainVerificationResult


class ChainEventLike(Protocol):
    """Structural type: anything with these four fields can be chain-verified."""

    event_id: str
    payload_hash: str
    previous_hash: str | None
    event_hash: str


def verify_chain(events: list[ChainEventLike]) -> ChainVerificationResult:
    """
    Verify a sequence of audit events, oldest first, for tamper-evidence.

    Args:
        events: Audit events in chronological (append) order.

    Returns:
        ChainVerificationResult. `valid=True` only if every event's stored
        event_hash matches the recomputed value AND every event's
        previous_hash correctly points at the prior event's event_hash.
        Verification stops at the first mismatch and reports it — later
        events are not checked, since one broken link already proves
        tampering (or corruption) occurred at that point.
    """
    expected_previous_hash: str | None = None

    for position, event in enumerate(events):
        if event.previous_hash != expected_previous_hash:
            return ChainVerificationResult(
                valid=False,
                events_checked=position + 1,
                first_mismatch=ChainMismatch(
                    event_id=event.event_id,
                    position=position,
                    reason=(
                        f"previous_hash '{event.previous_hash}' does not match the "
                        f"prior event's event_hash '{expected_previous_hash}'."
                    ),
                ),
                verified_at=datetime.now(UTC),
            )

        recomputed_hash = hash_event(event.payload_hash, event.previous_hash)
        if recomputed_hash != event.event_hash:
            return ChainVerificationResult(
                valid=False,
                events_checked=position + 1,
                first_mismatch=ChainMismatch(
                    event_id=event.event_id,
                    position=position,
                    reason=(
                        f"stored event_hash '{event.event_hash}' does not match "
                        f"recomputed hash '{recomputed_hash}'."
                    ),
                ),
                verified_at=datetime.now(UTC),
            )

        expected_previous_hash = event.event_hash

    return ChainVerificationResult(
        valid=True, events_checked=len(events), first_mismatch=None, verified_at=datetime.now(UTC)
    )
