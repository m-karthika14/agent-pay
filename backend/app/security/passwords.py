"""
Purpose: Password hashing and verification for the storefront login page.

Uses stdlib hashlib.pbkdf2_hmac (SHA-256, 200,000 iterations, a random
16-byte salt per password) rather than adding a new dependency -- this is
demo-scope authentication (plan.md's storefront has no real session/token
infra), not a production auth system, so the stdlib's built-in KDF is
sufficient without pulling in bcrypt/argon2/passlib.

Encoded format: "{salt_hex}${hash_hex}" -- stored as User.password_hash.
"""
import hashlib
import hmac
import secrets

_ITERATIONS = 200_000
_ALGORITHM = "sha256"


def hash_password(password: str) -> str:
    """Hash a plaintext password with a fresh random salt."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(_ALGORITHM, password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """
    Verify a plaintext password against a stored hash from hash_password().

    Uses hmac.compare_digest for constant-time comparison, so a failed
    check can't leak timing information about how much of the hash matched.
    """
    try:
        salt, expected_hex = password_hash.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac(_ALGORITHM, password.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS)
    return hmac.compare_digest(digest.hex(), expected_hex)
