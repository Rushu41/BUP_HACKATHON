"""Tests verifying that official public sample cases process successfully through the pipeline."""

import json
import os
from unittest.mock import patch
import pytest

from app.orchestrator import process_scenario
from app.schemas import OptimizeEnergyRequest


@pytest.fixture
def public_cases():
    json_path = os.path.join(os.path.dirname(__file__), "..", "public_cases.json")
    if not os.path.exists(json_path):
        sample_path = os.path.join(
            os.path.dirname(__file__), "..", "BUP_CSE_FEST_2026_Preli_Public_Sample_Cases.json"
        )
        with open(sample_path, "r", encoding="utf-8") as f:
            return json.load(f)["cases"]
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data["cases"] if isinstance(data, dict) and "cases" in data else data


@pytest.mark.asyncio
@patch("app.llm_interpreter.call_llm")
async def test_public_cases(mock_call_llm, public_cases):
    """Executes all 10 public cases through the full pipeline with mocked LLM output and validates costs."""
    for case in public_cases:
        case_input = case["input"] if "input" in case else case
        expected_output = case.get("expected_output", {})
        expected_directives = expected_output.get(
            "directive_interpretation", case.get("expected_directives", [])
        )

        mock_response = json.dumps(expected_directives)
        mock_call_llm.return_value = mock_response

        request = OptimizeEnergyRequest(**case_input)
        response = await process_scenario(request)

        assert response.scenario_id == request.scenario_id
        assert len(response.directive_interpretation) == len(expected_directives)

        # Verify directive types match
        for actual, expected in zip(response.directive_interpretation, expected_directives):
            assert actual.directive_type.value == expected["directive_type"]
            assert actual.applies == expected["applies"]

        # Verify plan validity and optimal cost if expected_output is provided
        if "total_cost_bdt" in expected_output:
            exp_cost = expected_output["total_cost_bdt"]
            act_cost = response.total_cost_bdt
            assert abs(exp_cost - act_cost) <= 0.01, (
                f"Cost mismatch in {case.get('id', request.scenario_id)}: "
                f"expected {exp_cost}, got {act_cost}"
            )
