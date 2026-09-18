# Integration Notes (Developer 3 - LLM)

## Required Dependencies
Please add the following to the central `requirements.txt`:
```txt
google-genai>=2.24.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
```

## Environment Variables
The application now strictly requires the following environment variable to communicate with the Gemini API:
- `GEMINI_API_KEY`: A valid Google AI Studio API key.

Ensure this key is **NOT** logged, committed, or hard-coded anywhere.

## Docker Additions
The `Dockerfile` has been prepared. It expects the FastAPI entrypoint to be `app.main:app` running on port `8000`. If Developer 1 changes the primary entrypoint name, please update the `CMD` instruction in the `Dockerfile`.

## Testing
We have created extensive semantic and deterministic testing for the LLM output.
- Run `pytest tests/test_llm_semantics.py` to ensure mock outputs function (no API key required).
- Run `pytest tests/test_public_cases.py` to test full parsing integrations. Note that `tests/test_public_cases.py` uses a mock to avoid eating tokens, but it tests the logic of interpreting multiple notes.

## Error Handling
If `app.llm_interpreter.interpret_operator_notes` fails (even after its 1-time automated recovery), it will raise a `app.guardrails.GuardrailValidationError`. 
Developer 1 (API) should ensure this exception is caught and returned cleanly (e.g., HTTP 422 Unprocessable Entity) without exposing stack traces.
