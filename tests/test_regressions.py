"""Regression tests verifying fixes for integration defects and edge cases."""

import asyncio
import inspect
import json
import os
import time
from unittest.mock import patch
import pytest
from pydantic import ValidationError

from app.config import settings
from app.exceptions import (
    GridWiseError,
    GuardrailValidationError,
    InterpretationError,
    OptimizationError,
    PlanValidationError,
    ProviderError,
    RequestValidationError,
)
from app.guardrails import validate_interpretations
from app.llm_interpreter import _to_serializable, call_llm
from app.math_utils import effective_solar_array
import app.orchestrator as orchestrator
from app.schemas import (
    BatteryInput,
    HourInput,
    MaxGridWindowAdjustment,
    MinimumBatteryReserveAdjustment,
    SolarReductionAdjustment,
)


def test_centralized_exception_hierarchy():
    """Verify all domain exceptions inherit from GridWiseError."""
    assert issubclass(RequestValidationError, GridWiseError)
    assert issubclass(InterpretationError, GridWiseError)
    assert issubclass(GuardrailValidationError, GridWiseError)
    assert issubclass(OptimizationError, GridWiseError)
    assert issubclass(PlanValidationError, GridWiseError)
    assert issubclass(ProviderError, GridWiseError)


def test_pydantic_battery_serialization():
    """Verify that BatteryInput and HourInput Pydantic models serialize cleanly to dict."""
    battery = BatteryInput(
        capacity_kwh=100.0,
        initial_energy_kwh=50.0,
        minimum_energy_kwh=10.0,
        max_charge_kwh_per_hour=20.0,
        max_discharge_kwh_per_hour=20.0,
    )
    serialized = _to_serializable(battery)
    assert isinstance(serialized, dict)
    # Ensure json.dumps does not raise TypeError
    json_str = json.dumps(serialized)
    assert "100.0" in json_str or "100" in json_str


def test_configured_llm_settings():
    """Verify configuration settings are properly defined on settings object."""
    assert hasattr(settings, "LLM_API_KEY")
    assert hasattr(settings, "LLM_MODEL")
    assert hasattr(settings, "LLM_BASE_URL")
    assert hasattr(settings, "LLM_TIMEOUT_SECONDS")
    assert hasattr(settings, "PORT")
    assert hasattr(settings, "LOG_LEVEL")


@pytest.mark.asyncio
async def test_llm_timeout_enforcement():
    """Verify that call_llm raises ProviderError when LLM provider exceeds timeout."""
    def slow_call(prompt):
        time.sleep(0.5)
        return "[]"

    with patch("app.llm_interpreter._sync_generate_content", side_effect=slow_call), \
         patch.object(settings, "LLM_TIMEOUT_SECONDS", 0.05):
        with pytest.raises(ProviderError, match="timed out"):
            await call_llm(["note 1"], {"capacity_kwh": 100}, [])


def test_bool_rejected_as_hour_in_guardrails():
    """Verify that boolean True/False is rejected as hour in deterministic guardrails."""
    notes = ["note 1"]
    battery = {"capacity_kwh": 100}
    with pytest.raises(GuardrailValidationError, match="booleans not allowed"):
        validate_interpretations(
            [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "no_charge_window",
                    "structured_adjustment": {"hours": [True]},
                    "explanation": "test",
                }
            ],
            notes,
            battery,
        )


def test_bool_rejected_as_factor_in_guardrails():
    """Verify that boolean True/False is rejected as solar factor in guardrails."""
    notes = ["note 1"]
    battery = {"capacity_kwh": 100}
    with pytest.raises(GuardrailValidationError, match="factor must be between 0 and 1"):
        validate_interpretations(
            [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "solar_reduction",
                    "structured_adjustment": {"hours": [12], "factor": True},
                    "explanation": "test",
                }
            ],
            notes,
            battery,
        )


def test_bool_rejected_as_reserve_in_guardrails():
    """Verify that boolean True/False is rejected as minimum reserve in guardrails."""
    notes = ["note 1"]
    battery = {"capacity_kwh": 100}
    with pytest.raises(GuardrailValidationError, match="minimum_energy_kwh"):
        validate_interpretations(
            [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "minimum_battery_reserve",
                    "structured_adjustment": {"hours": [18], "minimum_energy_kwh": False},
                    "explanation": "test",
                }
            ],
            notes,
            battery,
        )


def test_bool_rejected_as_grid_cap_in_guardrails():
    """Verify that boolean True/False is rejected as grid cap in guardrails."""
    notes = ["note 1"]
    battery = {"capacity_kwh": 100}
    with pytest.raises(GuardrailValidationError, match="max_grid_kwh"):
        validate_interpretations(
            [
                {
                    "note_index": 0,
                    "applies": True,
                    "directive_type": "max_grid_window",
                    "structured_adjustment": {"hours": [18], "max_grid_kwh": True},
                    "explanation": "test",
                }
            ],
            notes,
            battery,
        )


def test_bool_rejected_in_pydantic_schemas():
    """Verify Pydantic schemas explicitly reject booleans for numeric fields."""
    with pytest.raises(ValidationError):
        SolarReductionAdjustment(hours=[1], factor=True)

    with pytest.raises(ValidationError):
        MinimumBatteryReserveAdjustment(hours=[1], minimum_energy_kwh=False)

    with pytest.raises(ValidationError):
        MaxGridWindowAdjustment(hours=[1], max_grid_kwh=True)

    with pytest.raises(ValidationError):
        HourInput(hour=True, demand_kwh=10.0, solar_kwh=0.0, tariff_bdt_per_kwh=5.0)


def test_no_notimplemented_fallbacks_in_orchestrator():
    """Verify orchestrator contains no temporary NotImplementedError fallback stubs."""
    source = inspect.getsource(orchestrator)
    assert "NotImplementedError" not in source
    assert "has not been merged yet" not in source


def test_overlapping_solar_reduction_min_rule():
    """Verify multiple solar_reduction rules on the same hour take the minimum factor."""
    hours = [{"hour": h, "solar_kwh": 100.0} for h in range(24)]
    directives = [
        {
            "applies": True,
            "directive_type": "solar_reduction",
            "structured_adjustment": {"hours": [12], "factor": 0.6},
        },
        {
            "applies": True,
            "directive_type": "solar_reduction",
            "structured_adjustment": {"hours": [12], "factor": 0.25},
        },
    ]
    eff_solar = effective_solar_array(hours, directives)
    # min(0.6, 0.25) * 100.0 = 25.0
    assert abs(eff_solar[12] - 25.0) < 1e-9


def test_env_example_matches_config():
    """Verify .env.example declares all unified settings."""
    env_example_path = os.path.join(os.path.dirname(__file__), "..", ".env.example")
    with open(env_example_path, "r", encoding="utf-8") as f:
        content = f.read()

    expected_vars = [
        "LLM_API_KEY",
        "LLM_MODEL",
        "LLM_BASE_URL",
        "LLM_TIMEOUT_SECONDS",
        "PORT",
        "LOG_LEVEL",
    ]
    for var in expected_vars:
        assert var in content, f"{var} is missing from .env.example"
