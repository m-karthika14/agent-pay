"""
Purpose: Gemini-specific exceptions used to implement fail-closed behavior
(plan.md Rule 2 / Section 2 Rule 2: "If intent classification is unavailable
... BLOCK -> escalate").

Any caller of app.ai.gemini_client that needs fail-closed semantics (the
Merchant Revenue Agent in Phase 6, the Intent Gate in Phase 7) catches
GeminiUnavailableError and treats it as "the model could not be consulted"
rather than letting a raw network/API exception propagate.
"""


class GeminiError(Exception):
    """Base class for all Gemini-layer errors."""


class GeminiUnavailableError(GeminiError):
    """
    Raised when the Gemini API could not be reached or returned a server/
    auth/rate-limit error. Callers must fail closed on this, never assume
    the model would have said "allow" (plan.md Rule 2).
    """


class GeminiResponseError(GeminiError):
    """
    Raised when Gemini returned a response that could not be parsed into
    the requested structured schema (e.g. empty or malformed output).
    Treated the same as unavailable -- fail closed.
    """
