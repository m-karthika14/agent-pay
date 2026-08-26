"""
Purpose: Storefront login (plan.md Section 19 -- buyer identity).

Why this exists: Claude (via MCP) and the human's browser must resolve to
the exact same User row for a cart Claude creates to actually show up in
the browser's own cart page -- before this, the browser silently generated
a random throwaway identity per device (BuyerContext's old behavior), which
could never match whatever user_id a human had separately handed to Claude
in conversation. A real login screen lets a human explicitly say "I am
this user" instead.

login_or_claim() handles both signup and login in one call:
- Unknown email -> creates the user, password becomes their password.
- Known email with no password yet (every user created before this login
  page existed, e.g. via POST /api/users -- still how Claude/MCP resolves
  a user_id, which has no password of its own) -> the password given now
  is claimed as theirs, no separate backfill step needed for old rows.
- Known email with a password already set -> must match, or this rejects.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.schemas.common import AgentPayError
from app.security.passwords import hash_password, verify_password


async def login_or_claim(session: AsyncSession, email: str, password: str, name: str) -> User:
    """
    Log in an existing user, or create/claim one, by email + password.

    Args:
        session: Active AsyncSession.
        email: The buyer's email -- the natural key, same one Claude/MCP's
            get_or_create_user() (app.mandates.service) uses.
        password: Plaintext password to verify or claim.
        name: Display name to use only if a new user row is created.

    Returns:
        The logged-in/claimed User row.

    Raises:
        AgentPayError("INVALID_CREDENTIALS", status_code=401): the email
            exists with a password already set, and it doesn't match.
    """
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(email=email, name=name, password_hash=hash_password(password))
        session.add(user)
        await session.flush()
        return user

    if user.password_hash is None:
        user.password_hash = hash_password(password)
        await session.flush()
        return user

    if not verify_password(password, user.password_hash):
        raise AgentPayError(
            "INVALID_CREDENTIALS", "Incorrect email or password.", status_code=401, terminal=True, retryable=False
        )
    return user
