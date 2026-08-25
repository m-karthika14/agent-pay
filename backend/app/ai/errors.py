"""
Purpose: LLM-layer exceptions used to implement fail-closed behavior
(plan.md Rule 2 / Section 2 Rule 2: "If intent classification is unavailable
... BLOCK -> escalate").

Provider-neutral names (renamed from GeminiError/GeminiUnavailableError/
GeminiResponseError when the project switched its LLM provider from Gemini
to Groq -- Gemini's API quota was persistently exhausted through Phases
6-11, a real implementation blocker per plan.md's "do not add another
framework... unless an actual implementation blocker forces a change").

Any caller of app.ai.llm_client that needs fail-closed semantics (the
Merchant Revenue Agent, the Intent Gate) catches LLMUnavailableError and
treats it as "the model could not be consulted" rather than letting a raw
network/API exception propagate.
"""


class LLMError(Exception):
    """Base class for all LLM-layer errors."""


class LLMUnavailableError(LLMError):
    """
    Raised when the LLM API could not be reached or returned a server/
    auth/rate-limit error. Callers must fail closed on this, never assume
    the model would have said "allow" (plan.md Rule 2).
    """


class LLMResponseError(LLMError):
    """
    Raised when the LLM returned a response that could not be parsed into
    the requested structured schema (e.g. empty or malformed output).
    Treated the same as unavailable -- fail closed.
    """
