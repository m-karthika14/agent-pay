"""
Purpose: Ed25519 signing and verification primitives.

Responsibilities:
- Generate Ed25519 keypairs (used to provision ED25519_PRIVATE_KEY_B64 /
  ED25519_PUBLIC_KEY_B64, and by tests).
- Sign arbitrary canonical bytes and verify signatures against them.
- Base64 encode/decode keys and signatures for storage/transport.

This module operates purely on bytes. It has no knowledge of what a
"mandate" is — app.security.mandate_verifier is responsible for combining
this with app.security.canonical and the mandate's business rules. Keeping
this module mandate-agnostic makes the cryptographic core trivial to test in
isolation (see tests/unit/test_signing.py, the tamper test).
"""
import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


def generate_ed25519_keypair() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    """
    Generate a new Ed25519 keypair.

    Returns:
        (private_key, public_key) tuple. Used to provision AgentPay's signing
        key (stored as base64 in ED25519_PRIVATE_KEY_B64 / _PUBLIC_KEY_B64)
        and by tests that need a throwaway keypair.
    """
    private_key = Ed25519PrivateKey.generate()
    return private_key, private_key.public_key()


def sign_bytes(payload: bytes, private_key: Ed25519PrivateKey) -> bytes:
    """
    Sign canonical payload bytes with an Ed25519 private key.

    Args:
        payload: Canonical bytes to sign (e.g. from
            app.security.canonical.canonicalize_mandate()). Callers are
            responsible for canonicalizing first — this function signs
            exactly the bytes it is given.
        private_key: The signer's Ed25519 private key.

    Returns:
        Raw signature bytes (64 bytes for Ed25519).
    """
    return private_key.sign(payload)


def verify_signature(
    payload: bytes, signature: bytes, public_key: Ed25519PublicKey
) -> bool:
    """
    Verify an Ed25519 signature against payload bytes.

    Args:
        payload: The exact bytes that were supposedly signed.
        signature: The signature to check.
        public_key: The signer's Ed25519 public key.

    Returns:
        True if the signature is valid for this exact payload and key,
        False for ANY failure (wrong key, tampered payload, tampered
        signature, malformed signature). This function never raises for a
        bad signature — callers should never need to wrap it in try/except
        to implement "reject on failure" behavior, which keeps
        mandate_verifier's fail-closed logic simple and hard to get wrong.
    """
    try:
        public_key.verify(signature, payload)
        return True
    except InvalidSignature:
        return False


def encode_key(key: Ed25519PrivateKey | Ed25519PublicKey) -> str:
    """
    Base64-encode a raw Ed25519 key for storage in an environment variable.

    Args:
        key: An Ed25519 private or public key object.

    Returns:
        Base64 string of the key's raw bytes, suitable for
        ED25519_PRIVATE_KEY_B64 / ED25519_PUBLIC_KEY_B64.
    """
    if isinstance(key, Ed25519PrivateKey):
        from cryptography.hazmat.primitives import serialization

        raw = key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
    else:
        from cryptography.hazmat.primitives import serialization

        raw = key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    return base64.b64encode(raw).decode("ascii")


def decode_private_key(b64_value: str) -> Ed25519PrivateKey:
    """Decode a base64-encoded raw Ed25519 private key (e.g. from Settings)."""
    raw = base64.b64decode(b64_value)
    return Ed25519PrivateKey.from_private_bytes(raw)


def decode_public_key(b64_value: str) -> Ed25519PublicKey:
    """Decode a base64-encoded raw Ed25519 public key (e.g. from Settings)."""
    raw = base64.b64decode(b64_value)
    return Ed25519PublicKey.from_public_bytes(raw)
