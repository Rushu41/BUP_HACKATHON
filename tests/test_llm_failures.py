import pytest
import json
from unittest.mock import patch
from app.llm_interpreter import interpret_operator_notes
from app.guardrails import GuardrailValidationError

@pytest.mark.asyncio
@patch("app.llm_interpreter.call_llm")
async def test_interpret_operator_notes_recovery_failure(mock_call_llm):
    notes = ["solar falls to 20% from 1 PM to 3 PM"]
    battery = {"capacity_kwh": 100}
    hours = []
    
    # Both calls return invalid JSON
    mock_call_llm.side_effect = ["{invalid json}", "{still invalid json}"]
    
    with pytest.raises(GuardrailValidationError, match="LLM produced invalid JSON on recovery:"):
        await interpret_operator_notes(notes, battery, hours)
    
    assert mock_call_llm.call_count == 2

@pytest.mark.asyncio
@patch("app.llm_interpreter.call_llm")
async def test_interpret_operator_notes_recovery_guardrail_failure(mock_call_llm):
    notes = ["solar falls to 20% from 1 PM to 3 PM"]
    battery = {"capacity_kwh": 100}
    hours = []
    
    # Both calls return invalid guardrail values
    invalid_response = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "solar_reduction",
            "structured_adjustment": {
                "hours": [13, 14],
                "factor": 1.2
            },
            "explanation": "Solar is reduced."
        }
    ]
    
    mock_call_llm.side_effect = [json.dumps(invalid_response), json.dumps(invalid_response)]
    
    with pytest.raises(GuardrailValidationError, match="LLM failed recovery attempt"):
        await interpret_operator_notes(notes, battery, hours)
    
    assert mock_call_llm.call_count == 2
