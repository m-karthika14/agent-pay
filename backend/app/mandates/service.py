"""
Purpose: Create, persist, and consume AgentPay mandates.

Responsibilities:
- Sign a new mandate and persist it (status=ACTIVE).
- Look up a mandate's current persisted state for verification.
- Mark a single-use mandate CONSUMED after a successful transaction, so a
  later replay attempt is rejected by app.security.mandate_verifier.

This module is the only place that writes to the `mandates` table. It calls
into app.security (signing/verification) and app.audit (so mandate lifecycle
events are always recorded) rather than duplicating their logic.
"""
import base64
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import append_event
from app.core.config import get_settings
from app.db.models.mandate import Mandate
from app.schemas.audit import AuditEventInput
from app.schemas.mandate import MandatePayload, MandateStatus, SignedMandate
from app.security.canonical import canonicalize_mandate
from app.security.signing import decode_private_key, sign_bytes


async def create_mandate(
    session: AsyncSession, payload: MandatePayload, user_id: uuid.UUID, merchant_id: uuid.UUID
) -> Mandate:
    """
    Canonicalize, sign, and persist a new mandate. Records a MANDATE_CREATED
    audit event in the same session (caller commits).

    Args:
        session: Active AsyncSession.
        payload: The mandate content to sign and store.
        user_id: Internal UUID of the authorizing user.
        merchant_id: Internal UUID of the merchant the mandate is for.

    Returns:
        The persisted Mandate ORM row.

    Raises:
        ValueError: If ED25519_PRIVATE_KEY_B64 is not configured.
    """
    settings = get_settings()
    if not settings.ed25519_private_key_b64:
        raise ValueError(
            "ED25519_PRIVATE_KEY_B64 is not configured; cannot sign a mandate."
        )
    private_key = decode_private_key(settings.ed25519_private_key_b64)
    canonical_bytes = canonicalize_mandate(payload)
    signature = base64.b64encode(sign_bytes(canonical_bytes, private_key)).decode("ascii")

    row = Mandate(
        mandate_id=payload.mandate_id,
        user_id=user_id,
        merchant_id=merchant_id,
        signed_payload=canonical_bytes.decode("utf-8"),
        signature=signature,
        status=MandateStatus.ACTIVE,
        single_use=payload.single_use,
        expires_at=payload.expires_at,
    )
    session.add(row)
    await session.flush()

    await append_event(
        session,
        AuditEventInput(
            event_type="MANDATE_CREATED",
            actor_type="SYSTEM",
            payload={"mandate_id": payload.mandate_id, "merchant_id": str(merchant_id)},
            mandate_id=str(row.id),
        ),
    )
    return row


async def get_mandate_by_business_id(session: AsyncSession, mandate_id: str) -> Mandate | None:
    """Look up a persisted mandate row by its business-facing mandate_id (e.g. 'M-001')."""
    result = await session.execute(select(Mandate).where(Mandate.mandate_id == mandate_id))
    return result.scalar_one_or_none()


def to_signed_mandate(row: Mandate) -> SignedMandate:
    """Reconstruct a SignedMandate (for verification) from a persisted Mandate row."""
    payload_dict = json.loads(row.signed_payload)
    return SignedMandate(payload=MandatePayload(**payload_dict), signature=row.signature)


async def consume_mandate(session: AsyncSession, row: Mandate) -> Mandate:
    """
    Mark a mandate CONSUMED after it has authorized a completed transaction.

    A subsequent verify_mandate() call against this mandate will then see
    current_status=CONSUMED and reject any reuse as REPLAY_DETECTED
    (for single-use mandates) or MANDATE_ALREADY_CONSUMED otherwise.

    Args:
        session: Active AsyncSession.
        row: The mandate row to mark consumed.

    Returns:
        The updated Mandate row.
    """
    row.status = MandateStatus.CONSUMED
    row.consumed_at = datetime.now(UTC)
    await session.flush()

    await append_event(
        session,
        AuditEventInput(
            event_type="MANDATE_CONSUMED",
            actor_type="SYSTEM",
            payload={"mandate_id": row.mandate_id},
            mandate_id=str(row.id),
        ),
    )
    return row
