"""LLM operator-note interpreter using configured GenAI model with structured output."""

import asyncio
import json
from typing import Any, Dict, List

from google import genai
from google.genai import types

from app.config import settings
from app.exceptions import (
    GuardrailValidationError,
    InterpretationError,
    ProviderError,
)
from app.guardrails import validate_interpretations
from app.llm_prompts import SYSTEM_PROMPT


def _to_serializable(obj: Any) -> Any:
    """Recursively converts Pydantic models or objects with model_dump to JSON-serializable dicts."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, list):
        return [_to_serializable(item) for item in obj]
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    return obj


def _sync_generate_content(prompt: str) -> str:
    """Executes synchronous GenAI generate_content with structured schema."""
    api_key = settings.LLM_API_KEY
    if not api_key:
        raise ProviderError("LLM API key is not configured. Set LLM_API_KEY or GEMINI_API_KEY.")

    client = genai.Client(api_key=api_key)
    model_id = settings.LLM_MODEL

    response_schema = {
        "type": "ARRAY",
        "items": {
            "type": "OBJECT",
            "properties": {
                "note_index": {"type": "INTEGER"},
                "applies": {"type": "BOOLEAN"},
                "directive_type": {"type": "STRING"},
                "structured_adjustment": {
                    "type": "OBJECT",
                    "nullable": True,
                    "properties": {
                        "hours": {
                            "type": "ARRAY",
                            "items": {"type": "INTEGER"},
                        },
                        "factor": {"type": "NUMBER"},
                        "minimum_energy_kwh": {"type": "NUMBER"},
                        "max_grid_kwh": {"type": "NUMBER"},
                    },
                },
                "explanation": {"type": "STRING"},
            },
            "required": ["note_index", "applies", "directive_type", "explanation"],
        },
    }

    try:
        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=0.0,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        if not response or not response.text:
            raise InterpretationError("Empty response returned from LLM provider.")
        return response.text
    except Exception as e:
        err_msg = str(e)
        if "timed out" in err_msg.lower() or "timeout" in err_msg.lower():
            raise ProviderError(f"LLM provider timeout: {err_msg}") from e
        if isinstance(e, (InterpretationError, ProviderError, GuardrailValidationError)):
            raise
        raise ProviderError(f"LLM provider error: {err_msg}") from e


async def call_llm(
    operator_notes: List[str],
    battery: Any,
    hours: Any,
    error_message: str | None = None,
) -> str:
    """Asynchronously calls the LLM with serialized battery/hours context and strict timeout enforcement."""
    prompt = "Operator Notes to interpret:\n"
    for i, note in enumerate(operator_notes):
        prompt += f"Note {i}: {note}\n"

    battery_payload = _to_serializable(battery)
    prompt += f"\nBattery Context:\n{json.dumps(battery_payload, indent=2)}\n"

    if error_message:
        prompt += f"\nPREVIOUS OUTPUT FAILED VALIDATION:\n{error_message}\nPlease correct the output to strictly follow the rules."

    timeout = settings.LLM_TIMEOUT_SECONDS
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_sync_generate_content, prompt),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise ProviderError(f"LLM API request timed out after {timeout} seconds")


async def interpret_operator_notes(
    operator_notes: List[str],
    battery: Any,
    hours: Any,
) -> List[Dict[str, Any]]:
    """Interprets operator notes into a structured list of directives.

    Includes a 1-time automated recovery mechanism if the first LLM generation fails.
    """
    error_msg = None
    try:
        raw_response = await call_llm(operator_notes, battery, hours)
        interpretations = json.loads(raw_response)
        validated = validate_interpretations(interpretations, operator_notes, battery)
        return validated
    except GuardrailValidationError as e:
        error_msg = str(e)
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON format: {str(e)}"
    except ProviderError:
        raise
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"

    # Second attempt (1-time recovery retry)
    try:
        raw_response_retry = await call_llm(operator_notes, battery, hours, error_message=error_msg)
        interpretations_retry = json.loads(raw_response_retry)
        validated_retry = validate_interpretations(interpretations_retry, operator_notes, battery)
        return validated_retry
    except GuardrailValidationError as e:
        raise GuardrailValidationError(f"LLM failed recovery attempt. Final error: {str(e)}") from e
    except json.JSONDecodeError as e:
        raise GuardrailValidationError(f"LLM produced invalid JSON on recovery: {str(e)}") from e
