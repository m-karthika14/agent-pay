#!/usr/bin/env python
"""
Purpose: Standalone CLI tool to verify AgentPay's hash-chained audit log
against the live database (plan.md Section 23.3).

Responsibilities:
- Load every audit event, oldest first.
- Recompute each event_hash and compare it to what's stored.
- Report the first mismatch found, if any.
- Exit 0 if the chain is valid, non-zero if tampering/corruption is detected.

Run from the repo root or from backend/:
    uv run python scripts/verify_audit_chain.py
    (or, from backend/:  uv run python ../scripts/verify_audit_chain.py)

This script is intentionally a thin CLI wrapper: all real verification logic
lives in app.audit.verifier.verify_chain, which is unit tested directly in
backend/tests/unit/test_audit_chain.py.
"""
import asyncio
import sys
from pathlib import Path

# Make the backend/app package importable regardless of current working
# directory, since this script lives in scripts/ but depends on backend/app.
_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.audit.verifier import verify_chain  # noqa: E402
from app.db.models.audit_event import AuditEvent  # noqa: E402
from app.db.session import get_session_factory  # noqa: E402


async def main() -> int:
    """
    Load all audit events and verify the chain.

    Returns:
        Process exit code: 0 if the chain is valid, 1 if a mismatch is
        found or the audit log could not be read.
    """
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(AuditEvent).order_by(AuditEvent.sequence))
        events = list(result.scalars().all())

    if not events:
        print("Audit log is empty — nothing to verify.")
        return 0

    verification = verify_chain(events)

    print(f"Checked {verification.events_checked} of {len(events)} audit events.")

    if verification.valid:
        print("Hash chain VALID.")
        return 0

    mismatch = verification.first_mismatch
    print("Hash chain INVALID.")
    if mismatch is not None:
        print(f"First mismatch at position {mismatch.position} (event_id={mismatch.event_id}):")
        print(f"  {mismatch.reason}")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
