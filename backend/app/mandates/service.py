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
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.service import append_event
from app.core.config import get_settings
from app.db.models.mandate import Mandate
from app.db.models.merchant import Merchant
from app.db.models.user import User
from app.schemas.audit import AuditEventInput
from app.schemas.common import NotFoundError
from app.schemas.mandate import (
    CreateMandateRequest,
    MandateIntent,
    MandatePayload,
    MandateResponse,
    MandateStatus,
    SignedMandate,
)
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


async def get_or_create_user(session: AsyncSession, email: str, name: str) -> User:
    """
    Look up a user by email, creating one if none exists yet.

    The demo storefront has no real authentication (plan.md Section 18's
    mandate route never specified one), so email is the lightweight
    identity key -- mirrors scripts/seed_database.py's idempotent demo
    user creation.

    Args:
        session: Active AsyncSession.
        email: The buyer's email, used as the natural key.
        name: Display name to use if a new user row is created.

    Returns:
        The existing or newly-created User row.
    """
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user
    user = User(email=email, name=name)
    session.add(user)
    await session.flush()
    return user


async def create_mandate_from_request(session: AsyncSession, request: CreateMandateRequest) -> MandateResponse:
    """
    Create, sign, and persist a mandate from a buyer's stated intent
    (plan.md Section 18 `POST /api/mandates`).

    AgentPay generates the business-facing mandate_id itself -- never
    accepted from the caller -- so a buyer (or a compromised client) can
    never collide with or spoof another mandate's id.

    Args:
        session: Active AsyncSession.
        request: The buyer's stated constraints/intent.

    Returns:
        MandateResponse describing the newly-created mandate, including its
        mandate_id -- the value the buyer hands to Claude to authorize a
        purchase through MCP.

    Raises:
        NotFoundError: If no merchant exists with the given merchant_id.
        ValueError: If ED25519_PRIVATE_KEY_B64 is not configured (propagated
            from create_mandate()).
    """
    merchant_id = uuid.UUID(request.merchant_id)
    merchant = await session.get(Merchant, merchant_id)
    if merchant is None:
        raise NotFoundError("MERCHANT_NOT_FOUND", f"No merchant with id '{request.merchant_id}'.")

    user = await get_or_create_user(session, request.user_email, request.user_name)

    payload = MandatePayload(
        mandate_id=f"M-{uuid.uuid4().hex[:8]}",
        merchant_id=request.merchant_id,
        currency=request.currency,
        max_amount=request.max_amount_minor,
        allowed_categories=request.allowed_categories,
        allow_addons=request.allow_addons,
        delivery_requirement=request.delivery_requirement,
        single_use=request.single_use,
        expires_at=datetime.now(UTC) + timedelta(hours=request.expires_in_hours),
        intent=MandateIntent(product_type=request.product_type, notes=request.notes),
    )
    row = await create_mandate(session, payload, user.id, merchant_id)
    return to_mandate_response(row)


def to_mandate_response(row: Mandate) -> MandateResponse:
    """Decode a persisted Mandate row's signed_payload into the public MandateResponse shape."""
    signed_mandate = to_signed_mandate(row)
    payload = signed_mandate.payload
    return MandateResponse(
        mandate_id=payload.mandate_id,
        merchant_id=payload.merchant_id,
        currency=payload.currency,
        max_amount_minor=payload.max_amount,
        allowed_categories=payload.allowed_categories,
        allow_addons=payload.allow_addons,
        delivery_requirement=payload.delivery_requirement,
        single_use=payload.single_use,
        expires_at=payload.expires_at,
        product_type=payload.intent.product_type,
        notes=payload.intent.notes,
        status=row.status.value,
    )
