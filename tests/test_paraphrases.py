import pytest
import json
from unittest.mock import patch
from app.llm_interpreter import interpret_operator_notes

@pytest.mark.asyncio
@patch("app.llm_interpreter.call_llm")
async def test_paraphrase_solar(mock_call_llm):
    notes = [
        "Solar falls to 20% from 1 PM to 3 PM.",
        "Only one fifth of PV generation will remain.",
        "An 80 percent reduction is expected.",
        "PV reduced by 25%.",
        "PV reduced to 25%."
    ]
    battery = {"capacity_kwh": 100}
    hours = []
    
    # We just mock the LLM for one note to make sure our system passes it through properly
    mock_response = [
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
    mock_call_llm.return_value = json.dumps(mock_response)
    
    result = await interpret_operator_notes([notes[0]], battery, hours)
    assert result[0]["structured_adjustment"]["factor"] == 0.2

@pytest.mark.asyncio
@patch("app.llm_interpreter.call_llm")
async def test_paraphrase_distractors(mock_call_llm):
    notes = [
        "The cafeteria menu changes tomorrow.",
        "150 students registered for a seminar.",
        "The football game begins at 7 PM.",
        "The library closes between 6 PM and 8 PM."
    ]
    battery = {"capacity_kwh": 100}
    hours = []
    
    mock_response = [
        {
            "note_index": 0,
            "applies": False,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "Irrelevant note."
        }
    ]
    mock_call_llm.return_value = json.dumps(mock_response)
    
    result = await interpret_operator_notes([notes[0]], battery, hours)
    assert result[0]["directive_type"] == "no_op"
    assert result[0]["applies"] is False
