import pytest
import json
from unittest.mock import patch
from app.llm_interpreter import interpret_operator_notes
from app.guardrails import GuardrailValidationError

@pytest.mark.asyncio
@patch("app.llm_interpreter.call_llm")
async def test_interpret_operator_notes_success(mock_call_llm):
    notes = ["solar falls to 20% from 1 PM to 3 PM"]
    battery = {"capacity_kwh": 100}
    hours = []
    
    mock_response = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "solar_reduction",
            "structured_adjustment": {
                "hours": [13, 14],
                "factor": 0.2
            },
            "explanation": "Solar is reduced to 20% between 1 PM and 3 PM."
        }
    ]
    mock_call_llm.return_value = json.dumps(mock_response)
    
    result = await interpret_operator_notes(notes, battery, hours)
    assert len(result) == 1
    assert result[0]["directive_type"] == "solar_reduction"
    assert result[0]["structured_adjustment"]["hours"] == [13, 14]
    assert result[0]["structured_adjustment"]["factor"] == 0.2

@pytest.mark.asyncio
@patch("app.llm_interpreter.call_llm")
async def test_interpret_operator_notes_recovery_success(mock_call_llm):
    notes = ["solar falls to 20% from 1 PM to 3 PM"]
    battery = {"capacity_kwh": 100}
    hours = []
    
    # First call returns invalid (factor > 1)
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
    
    # Second call returns valid
    valid_response = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "solar_reduction",
            "structured_adjustment": {
                "hours": [13, 14],
                "factor": 0.2
            },
            "explanation": "Solar is reduced."
        }
    ]
    
    mock_call_llm.side_effect = [json.dumps(invalid_response), json.dumps(valid_response)]
    
    result = await interpret_operator_notes(notes, battery, hours)
    assert len(result) == 1
    assert result[0]["structured_adjustment"]["factor"] == 0.2
    assert mock_call_llm.call_count == 2
