"""
Purpose: Verify the audit hash chain is internally consistent and
tamper-evident, per the Phase 1 acceptance criteria:

    Audit      -> STORED   (covered by tests/integration/test_database.py)
    Hash chain -> VALID    (covered here)

This module is pure — it builds a chain of AuditEventRecord objects via
app.audit.service.build_audit_event() and checks app.audit.verifier without
touching a database.
"""
from app.audit.service import build_audit_event
from app.audit.verifier import verify_chain
from app.schemas.audit import AuditEventInput


def _build_chain(length: int) -> list:
    events = []
    previous_hash = None
    for i in range(length):
        record = build_audit_event(
            AuditEventInput(
                event_type=f"EVENT_{i}",
                actor_type="SYSTEM",
                payload={"index": i},
            ),
            previous_hash,
        )
        events.append(record)
        previous_hash = record.event_hash
    return events


def test_valid_chain_verifies() -> None:
    chain = _build_chain(5)

    result = verify_chain(chain)

    assert result.valid is True
    assert result.events_checked == 5
    assert result.first_mismatch is None


def test_first_event_has_no_previous_hash() -> None:
    chain = _build_chain(1)

    assert chain[0].previous_hash is None


def test_each_event_links_to_the_previous_event_hash() -> None:
    chain = _build_chain(3)

    assert chain[1].previous_hash == chain[0].event_hash
    assert chain[2].previous_hash == chain[1].event_hash


def test_tampered_payload_hash_is_detected() -> None:
    """Directly mutating a stored payload_hash must break that event's own hash check."""
    chain = _build_chain(4)

    tampered = chain[2].model_copy(update={"payload_hash": "0" * 64})
    chain[2] = tampered

    result = verify_chain(chain)

    assert result.valid is False
    assert result.first_mismatch is not None
    assert result.first_mismatch.position == 2
    assert result.events_checked == 3


def test_tampered_event_hash_is_detected() -> None:
    chain = _build_chain(4)

    tampered = chain[1].model_copy(update={"event_hash": "f" * 64})
    chain[1] = tampered

    result = verify_chain(chain)

    assert result.valid is False
    assert result.first_mismatch is not None
    assert result.first_mismatch.position == 1


def test_removing_a_middle_event_breaks_the_chain_link() -> None:
    """Deleting/skipping an event must be detectable via the previous_hash link."""
    chain = _build_chain(4)

    del chain[1]  # remove the second event; chain[1] (was index 2) now points to a hash that no longer precedes it

    result = verify_chain(chain)

    assert result.valid is False
    assert result.first_mismatch is not None
    assert result.first_mismatch.position == 1
