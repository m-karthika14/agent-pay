"""
Purpose: Centralize all access to the LLM API (plan.md Section 12).

Originally written for Gemini (`google-genai`); the project now uses Groq,
switched at the user's explicit direction after Gemini's API quota was
persistently exhausted through Phases 6-11 (a real implementation blocker
per plan.md's "do not add another framework... unless an actual
implementation blocker forces a change"). Renamed from gemini_client.py to
this provider-neutral name for the same reason.

Responsibilities:
- Construct a single Groq client from Settings (never build one ad hoc
  elsewhere in the codebase -- this is the only place GROQ_API_KEY is read).
- Centralize model selection via Settings.groq_model (GROQ_MODEL env var)
  so no model name is ever hardcoded in a calling module.
- Expose two simple application methods: classify_with_schema() for
  Pydantic-structured output (used by the Intent Gate, and by the Merchant
  Revenue Agent's candidate-generation step), and complete_text() for plain
  free-text completion.
- Convert the SDK's own exceptions into app.ai.errors.LLMUnavailableError /
  LLMResponseError, so every caller can implement fail-closed behavior
  uniformly (plan.md Rule 2) without depending on groq's exception types
  directly.

Uses the official `groq` Python SDK's OpenAI-compatible chat completions
API. Structured output is implemented via JSON mode
(response_format={"type": "json_object"}) with the target Pydantic
schema's JSON Schema embedded in the system prompt, rather than assuming
every Groq-hosted model supports strict provider-side schema-constrained
decoding -- this keeps GROQ_MODEL freely swappable (plan.md Section 12
"never hardcode model name") without silently breaking structured output
on a model that doesn't support that stricter mode.
"""
from functools import lru_cache

from groq import APIError as GroqAPIError
from groq import AsyncGroq
from pydantic import BaseModel, ValidationError

from app.ai.errors import LLMResponseError, LLMUnavailableError
from app.core.config import get_settings


@lru_cache
def get_llm_client() -> AsyncGroq:
    """
    Return the process-wide Groq client, built from Settings.groq_api_key.

    Returns:
        An AsyncGroq client. Cached so the same client instance is reused.

    Raises:
        LLMUnavailableError: If GROQ_API_KEY is not configured. Unlike some
            SDKs, AsyncGroq does not itself raise on an empty key at
            construction time (auth is only checked on the first real
            request), so this guard is what actually enforces fail-closed
            behavior for a missing key.
    """
    settings = get_settings()
    if not settings.groq_api_key:
        raise LLMUnavailableError("GROQ_API_KEY is not configured.")
    return AsyncGroq(api_key=settings.groq_api_key)


def get_configured_model() -> str:
    """
    Return the currently configured Groq model name.

    Returns:
        Settings.groq_model (GROQ_MODEL env var).

    Raises:
        LLMUnavailableError: If no model has been configured -- an
            unconfigured model must never silently fall back to some
            hardcoded default (plan.md Section 12 "Never hardcode model
            name"; treated as unavailable, so callers fail closed).
    """
    model = get_settings().groq_model
    if not model:
        raise LLMUnavailableError("GROQ_MODEL is not configured.")
    return model


def _schema_instruction(schema: type[BaseModel]) -> str:
    """Render a Pydantic schema into an instruction telling the model exactly what JSON shape to return."""
    return (
        "Respond with ONLY a single JSON object matching this exact JSON "
        "Schema. No prose, no markdown code fences, no extra keys.\n"
        f"{schema.model_json_schema()}"
    )


async def classify_with_schema(
    prompt: str, schema: type[BaseModel], *, system_instruction: str | None = None
) -> BaseModel:
    """
    Call the LLM and parse its response into a Pydantic schema.

    Args:
        prompt: The user-turn content to send.
        schema: A Pydantic BaseModel subclass describing the exact shape
            the model must return. Its JSON Schema is embedded into the
            system prompt (see module docstring), and the raw JSON
            response is validated against it client-side afterward.
        system_instruction: Optional system prompt (who the model is acting
            as, what it may/may not do -- plan.md Section 5.5).

    Returns:
        An instance of `schema`, already validated by Pydantic.

    Raises:
        LLMUnavailableError: If the API call itself fails (network, auth,
            rate limit, server error) or the model is unconfigured.
        LLMResponseError: If the model responded but the output was empty
            or could not be parsed into `schema`.
    """
    client = get_llm_client()
    model = get_configured_model()
    combined_system = (
        f"{system_instruction}\n\n{_schema_instruction(schema)}" if system_instruction else _schema_instruction(schema)
    )

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": combined_system},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
    except GroqAPIError as exc:
        raise LLMUnavailableError(f"Groq API call failed: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        raise LLMResponseError("Groq response was empty.")
    try:
        return schema.model_validate_json(content)
    except ValidationError as exc:
        raise LLMResponseError(f"Groq response could not be parsed into the requested schema: {exc}") from exc


async def complete_text(prompt: str, *, system_instruction: str | None = None) -> str:
    """
    Call the LLM for a plain free-text completion (no structured schema).

    Args:
        prompt: The user-turn content to send.
        system_instruction: Optional system prompt.

    Returns:
        The model's text response.

    Raises:
        LLMUnavailableError: If the API call fails or the model is
            unconfigured.
    """
    client = get_llm_client()
    model = get_configured_model()
    messages: list[dict[str, str]] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    try:
        response = await client.chat.completions.create(model=model, messages=messages)
    except GroqAPIError as exc:
        raise LLMUnavailableError(f"Groq API call failed: {exc}") from exc
    return response.choices[0].message.content or ""
