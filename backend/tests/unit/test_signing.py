"""
Purpose: The first security test in the AgentPay repository.

This is the tamper test required by plan.md Section 7.4 / final.md Section 7.4:
sign a valid mandate payload, flip a single byte in the signed bytes, and assert
that verification rejects it. This test is written before `app.security.signing`
exists, so it is expected to fail on collection until that module is implemented.

This module only exercises the low-level Ed25519 primitives in
`app.security.signing` — it does not touch the database, FastAPI, or any
higher-level mandate business rules (those are covered in
test_mandate_verifier.py).
"""
from app.security.signing import generate_ed25519_keypair, sign_bytes, verify_signature


def test_valid_signature_is_accepted() -> None:
    """A signature produced by sign_bytes() must verify against the matching public key."""
    private_key, public_key = generate_ed25519_keypair()
    payload = b'{"mandate_id": "M-001", "max_amount": 3000}'

    signature = sign_bytes(payload, private_key)

    assert verify_signature(payload, signature, public_key) is True


def test_tampered_payload_is_rejected() -> None:
    """
    The core tamper test: sign a payload, flip one byte of the SIGNED PAYLOAD,
    and verify with the original signature. This must be rejected.

    This is the first true milestone for AgentPay: a one-byte change to a
    signed mandate must make the transaction invalid.
    """
    private_key, public_key = generate_ed25519_keypair()
    payload = bytearray(b'{"mandate_id": "M-001", "max_amount": 3000}')

    signature = sign_bytes(bytes(payload), private_key)

    # Flip a single byte in the payload that was actually signed.
    payload[10] ^= 0xFF
    tampered_payload = bytes(payload)

    assert verify_signature(tampered_payload, signature, public_key) is False


def test_tampered_signature_is_rejected() -> None:
    """Corrupting the signature itself (payload untouched) must also be rejected."""
    private_key, public_key = generate_ed25519_keypair()
    payload = b'{"mandate_id": "M-001", "max_amount": 3000}'

    signature = bytearray(sign_bytes(payload, private_key))
    signature[0] ^= 0xFF

    assert verify_signature(payload, bytes(signature), public_key) is False


def test_signature_from_wrong_key_is_rejected() -> None:
    """A signature verified against the wrong public key must be rejected."""
    private_key_a, _public_key_a = generate_ed25519_keypair()
    _private_key_b, public_key_b = generate_ed25519_keypair()
    payload = b'{"mandate_id": "M-001", "max_amount": 3000}'

    signature = sign_bytes(payload, private_key_a)

    assert verify_signature(payload, signature, public_key_b) is False
