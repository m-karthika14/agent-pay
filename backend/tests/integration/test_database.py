"""
Purpose: Integration tests against the real native PostgreSQL database.

Unlike tests/unit/*, these tests require DATABASE_URL (see backend/.env) to
point at a running PostgreSQL instance with migrations applied
(`uv run alembic upgrade head`). They exercise the actual Phase 1 acceptance
criteria end to end:

    Valid mandate     -> PASS
    Tampered mandate  -> REJECT (covered at the unit level; signature
                                  tampering is orthogonal to persistence)
    Expired mandate   -> REJECT (covered at the unit level)
    Replay            -> REJECT
    Audit             -> STORED
    Hash chain        -> VALID

Test fixtures (users/merchants/mandates) are created with unique
`test-<uuid>` identifiers and intentionally left in the database rather than
deleted: audit_events are append-only by design (see
app/db/models/audit_event.py), and a mandate row cannot be deleted once an
audit event references it via FK. Accumulating a handful of clearly-named
test rows in the local dev database is expected and harmless; this mirrors
how the real system behaves (mandates and audit events are never deleted).
"""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.audit.service import append_event
from app.audit.verifier import verify_chain
from app.core.config import get_settings
from app.db.models.audit_event import AuditEvent
from app.db.models.merchant import Merchant
from app.db.models.user import User
from app.db.session import get_session_factory
from app.mandates.service import consume_mandate, create_mandate, to_signed_mandate
from app.schemas.audit import AuditEventInput
from app.schemas.mandate import MandateIntent, MandatePayload
from app.security.mandate_verifier import verify_mandate


async def _create_test_user_and_merchant(session):
    """Create uniquely-named user + merchant rows for a single test run."""
    unique = uuid.uuid4().hex[:8]
    user = User(email=f"test-{unique}@agentpay.test", name="Test User")
    merchant = Merchant(slug=f"urbannest-test-{unique}", name="UrbanNest Test", currency="INR")
    session.add_all([user, merchant])
    await session.flush()
    return user, merchant


def _sample_payload(merchant_id: str, **overrides: object) -> MandatePayload:
    defaults: dict[str, object] = {
        "mandate_id": f"M-{uuid.uuid4().hex[:8]}",
        "merchant_id": merchant_id,
        "currency": "INR",
        "max_amount": 300000,
        "allowed_categories": ["electronics"],
        "allow_addons": False,
        "delivery_requirement": "under_3_days",
        "single_use": True,
        "expires_at": datetime.now(UTC) + timedelta(days=1),
        "intent": MandateIntent(product_type="wireless earbuds", notes="no accessories"),
    }
    defaults.update(overrides)
    return MandatePayload(**defaults)  # type: ignore[arg-type]


async def test_valid_mandate_round_trips_through_the_database() -> None:
    """Create a mandate via the service layer, persist it, and verify it PASSES."""
    factory = get_session_factory()
    async with factory() as session:
        user, merchant = await _create_test_user_and_merchant(session)
        payload = _sample_payload(str(merchant.id))

        row = await create_mandate(session, payload, user.id, merchant.id)
        await session.commit()

        result = verify_mandate(
            to_signed_mandate(row),
            get_settings().ed25519_public_key_b64,
            current_status=row.status,
        )
        assert result.valid is True


async def test_consumed_mandate_is_rejected_as_replay() -> None:
    """Consume a single-use mandate, then verifying it again must be REPLAY_DETECTED."""
    factory = get_session_factory()
    async with factory() as session:
        user, merchant = await _create_test_user_and_merchant(session)
        payload = _sample_payload(str(merchant.id))

        row = await create_mandate(session, payload, user.id, merchant.id)
        await consume_mandate(session, row)
        await session.commit()

        result = verify_mandate(
            to_signed_mandate(row),
            get_settings().ed25519_public_key_b64,
            current_status=row.status,
        )
        assert result.valid is False
        assert result.reason_code == "REPLAY_DETECTED"


async def test_audit_events_are_stored_and_chain_verifies() -> None:
    """
    Append audit events to the real database and confirm:
    - they are actually STORED (readable back via a fresh query)
    - the FULL stored chain, from the very first event ever appended to this
      database, still VERIFIES (app.audit.verifier.verify_chain)

    Since AuditEvent rows are never deleted or updated by application code,
    verifying the entire table is a genuine proof that nothing in the
    persisted history has been tampered with -- not just the rows this test
    itself appended.
    """
    factory = get_session_factory()
    async with factory() as session:
        marker = uuid.uuid4().hex
        for i in range(3):
            await append_event(
                session,
                AuditEventInput(
                    event_type=f"TEST_EVENT_{i}",
                    actor_type="SYSTEM",
                    payload={"i": i, "marker": marker},
                ),
            )
        await session.commit()

        result = await session.execute(select(AuditEvent).order_by(AuditEvent.sequence))
        all_events = list(result.scalars().all())

        # Our 3 new events must actually be present.
        our_event_types = {f"TEST_EVENT_{i}" for i in range(3)}
        stored_types = {e.event_type for e in all_events[-3:]}
        assert stored_types == our_event_types

        chain_result = verify_chain(all_events)
        assert chain_result.valid is True
