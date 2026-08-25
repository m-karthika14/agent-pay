"""
Purpose: Centralize all access to the Gemini API (plan.md Section 12).

Responsibilities:
- Construct a single Gemini client from Settings (never build one ad hoc
  elsewhere in the codebase -- this is the only place GEMINI_API_KEY is read).
- Centralize model selection via Settings.gemini_model (GEMINI_MODEL env
  var) so no model name is ever hardcoded in a calling module.
- Expose two simple application methods: classify_with_schema() for
  Pydantic-structured output (used by the Intent Gate in Phase 7, and by
  the Merchant Revenue Agent's candidate-generation step), and
  complete_text() for plain free-text completion.
- Convert the SDK's own exceptions into app.ai.errors.GeminiUnavailableError
  / GeminiResponseError, so every caller can implement fail-closed behavior
  uniformly (plan.md Rule 2) without depending on google-genai's exception
  types directly.

Uses the official `google-genai` Python SDK (plan.md Section 12), not a
legacy Gemini library.
"""
from functools import lru_cache

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

from app.ai.errors import GeminiResponseError, GeminiUnavailableError
from app.core.config import get_settings


@lru_cache
def get_gemini_client() -> genai.Client:
    """
    Return the process-wide Gemini client, built from Settings.gemini_api_key.

    Returns:
        A genai.Client. Cached so the same client instance is reused.

    Raises:
        GeminiUnavailableError: If GEMINI_API_KEY is not configured. The SDK
            itself raises a bare ValueError for this, which callers should
            never need to know about specifically -- everything that means
            "Gemini cannot be reached right now" surfaces as this one type,
            so fail-closed handling (plan.md Rule 2) has a single case to
            catch regardless of *why* Gemini was unavailable.
    """
    settings = get_settings()
    if not settings.gemini_api_key:
        raise GeminiUnavailableError("GEMINI_API_KEY is not configured.")
    try:
        return genai.Client(api_key=settings.gemini_api_key)
    except ValueError as exc:
        raise GeminiUnavailableError(f"Could not construct Gemini client: {exc}") from exc


def get_configured_model() -> str:
    """
    Return the currently configured Gemini model name.

    Returns:
        Settings.gemini_model (GEMINI_MODEL env var).

    Raises:
        GeminiUnavailableError: If no model has been configured -- an
            unconfigured model must never silently fall back to some
            hardcoded default (plan.md Section 12 "Never hardcode model
            name"; treated as unavailable, so callers fail closed).
    """
    model = get_settings().gemini_model
    if not model:
        raise GeminiUnavailableError("GEMINI_MODEL is not configured.")
    return model


async def classify_with_schema(
    prompt: str, schema: type[BaseModel], *, system_instruction: str | None = None
) -> BaseModel:
    """
    Call Gemini and parse its response into a Pydantic schema.

    Args:
        prompt: The user-turn content to send.
        schema: A Pydantic BaseModel subclass describing the exact shape
            Gemini must return. Google's structured-output support
            constrains generation to this schema and pre-parses the result.
        system_instruction: Optional system prompt (who the model is acting
            as, what it may/may not do -- plan.md Section 5.5).

    Returns:
        An instance of `schema`, already validated by Pydantic.

    Raises:
        GeminiUnavailableError: If the API call itself fails (network,
            auth, rate limit, server error) or the model is unconfigured.
        GeminiResponseError: If Gemini responded but the output could not
            be parsed into `schema`.
    """
    client = get_gemini_client()
    model = get_configured_model()
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        system_instruction=system_instruction,
    )
    try:
        response = await client.aio.models.generate_content(model=model, contents=prompt, config=config)
    except genai_errors.APIError as exc:
        raise GeminiUnavailableError(f"Gemini API call failed: {exc}") from exc

    if response.parsed is None:
        raise GeminiResponseError("Gemini response could not be parsed into the requested schema.")
    return response.parsed


async def complete_text(prompt: str, *, system_instruction: str | None = None) -> str:
    """
    Call Gemini for a plain free-text completion (no structured schema).

    Args:
        prompt: The user-turn content to send.
        system_instruction: Optional system prompt.

    Returns:
        The model's text response.

    Raises:
        GeminiUnavailableError: If the API call fails or the model is
            unconfigured.
    """
    client = get_gemini_client()
    model = get_configured_model()
    config = types.GenerateContentConfig(system_instruction=system_instruction) if system_instruction else None
    try:
        response = await client.aio.models.generate_content(model=model, contents=prompt, config=config)
    except genai_errors.APIError as exc:
        raise GeminiUnavailableError(f"Gemini API call failed: {exc}") from exc
    return response.text
