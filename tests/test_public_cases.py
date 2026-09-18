import pytest
import json
import os
from unittest.mock import patch
from app.llm_interpreter import interpret_operator_notes

@pytest.fixture
def public_cases():
    json_path = os.path.join(os.path.dirname(__file__), "..", "public_cases.json")
    if not os.path.exists(json_path):
        pytest.skip(f"{json_path} not found")
    with open(json_path, 'r') as f:
        return json.load(f)

@pytest.mark.asyncio
@patch("app.llm_interpreter.call_llm")
async def test_public_cases(mock_call_llm, public_cases):
    for case in public_cases:
        operator_notes = case.get("operator_notes", [])
        battery = case.get("battery", {})
        hours = case.get("hours", [])
        expected_directives = case.get("expected_directives", [])
        
        mock_response = json.dumps(expected_directives)
        mock_call_llm.return_value = mock_response
        
        interpretations = await interpret_operator_notes(operator_notes, battery, hours)
        
        assert len(interpretations) == len(expected_directives)
        for actual, expected in zip(interpretations, expected_directives):
            assert actual["directive_type"] == expected["directive_type"]
            assert actual["applies"] == expected["applies"]
