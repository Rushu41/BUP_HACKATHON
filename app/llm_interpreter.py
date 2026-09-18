import json
import os
from typing import Any, Dict, List
from google import genai
from google.genai import types
from .llm_prompts import SYSTEM_PROMPT
from .guardrails import validate_interpretations, GuardrailValidationError

async def call_llm(operator_notes: List[str], battery: Dict[str, Any], hours: List[Dict[str, Any]], error_message: str = None) -> str:
    """
    Calls the LLM with the provided context.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable is not set")
        
    client = genai.Client(api_key=api_key)
    
    # We use gemini-2.5-flash as the fast language model with structured output capabilities.
    model_id = "gemini-2.5-flash"
    
    prompt = f"Operator Notes to interpret:\n"
    for i, note in enumerate(operator_notes):
        prompt += f"Note {i}: {note}\n"
        
    prompt += f"\nBattery Context:\n{json.dumps(battery, indent=2)}\n"
    
    if error_message:
        prompt += f"\nPREVIOUS OUTPUT FAILED VALIDATION:\n{error_message}\nPlease correct the output to strictly follow the rules."
        
    # Define JSON schema for the expected list of dictionaries
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
                            "items": {"type": "INTEGER"}
                        },
                        "factor": {"type": "NUMBER"},
                        "minimum_energy_kwh": {"type": "NUMBER"},
                        "max_grid_kwh": {"type": "NUMBER"}
                    }
                },
                "explanation": {"type": "STRING"}
            },
            "required": ["note_index", "applies", "directive_type", "explanation"]
        }
    }
    
    response = client.models.generate_content(
        model=model_id,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=0.0
        )
    )
    
    return response.text

async def interpret_operator_notes(
    operator_notes: List[str],
    battery: Dict[str, Any],
    hours: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Interprets operator notes into a structured list of directives.
    Includes a 1-time recovery mechanism if the first LLM output fails validation.
    """
    # First attempt
    raw_response = await call_llm(operator_notes, battery, hours)
    
    try:
        interpretations = json.loads(raw_response)
        validated = validate_interpretations(interpretations, operator_notes, battery)
        return validated
    except GuardrailValidationError as e:
        error_msg = str(e)
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON format: {str(e)}"
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        
    # Second attempt (1-time recovery)
    raw_response_retry = await call_llm(operator_notes, battery, hours, error_message=error_msg)
    
    try:
        interpretations_retry = json.loads(raw_response_retry)
        validated_retry = validate_interpretations(interpretations_retry, operator_notes, battery)
        return validated_retry
    except GuardrailValidationError as e:
        # If it fails again, raise a controlled error
        raise GuardrailValidationError(f"LLM failed recovery attempt. Final error: {str(e)}")
    except json.JSONDecodeError as e:
        raise GuardrailValidationError(f"LLM produced invalid JSON on recovery: {str(e)}")
