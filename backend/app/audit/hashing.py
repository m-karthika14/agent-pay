"""
Purpose: Pure hashing primitives for the AgentPay audit hash chain.

Responsibilities:
- Deterministically hash an audit event's payload (payload_hash).
- Chain a payload_hash to the previous event's hash to produce event_hash.

This module has no database or side effects — it is pure functions over
bytes/strings, so the chain's cryptographic properties can be unit tested
without a live database (plan.md Section 23.2).
"""
import hashlib
import json


def hash_payload(payload: dict) -> str:
    """
    Compute the SHA-256 hex digest of a canonicalized event payload.

    Args:
        payload: Arbitrary JSON-serializable dict describing the event.

    Returns:
        Lowercase hex-encoded SHA-256 digest. Uses sort_keys + compact
        separators so the same logical payload always hashes identically,
        for the same reason mandate canonicalization does
        (app.security.canonical.canonicalize_mandate).
    """
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def hash_event(payload_hash: str, previous_hash: str | None) -> str:
    """
    Compute the chained event_hash from this event's payload_hash and the
    previous event's event_hash.

    Args:
        payload_hash: This event's own SHA-256 payload hash (from hash_payload).
        previous_hash: The previous event's event_hash, or None for the very
            first event in the chain.

    Returns:
        Lowercase hex-encoded SHA-256 digest of `previous_hash + payload_hash`.
        Any tampering with a prior event's stored hash changes every
        subsequent event_hash, making the chain tamper-evident.
    """
    chain_input = f"{previous_hash or ''}{payload_hash}"
    return hashlib.sha256(chain_input.encode("utf-8")).hexdigest()
