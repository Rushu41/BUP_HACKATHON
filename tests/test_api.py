"""API route and integration tests for GridWise."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.exceptions import (
    GuardrailValidationError,
    InterpretationError,
    OptimizationError,
    PlanValidationError,
    ProviderError,
)
from app.main import app
from app.schemas import DirectiveType
from tests.test_request_validation import make_valid_request

client = TestClient(app)


def test_health_endpoint_status_and_body():
    """Verify GET /health returns 200 and body {'status': 'ok'}."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_optimize_energy_full_mocked_pipeline():
    """Verify POST /optimize-energy pipeline coordinates all 4 stages in exact order."""
    call_order = []

    mock_interpretations = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": DirectiveType.SOLAR_REDUCTION.value,
            "structured_adjustment": {"hours": [13, 14], "factor": 0.25},
            "explanation": "Solar drops by 75%",
        }
    ]

    mock_plan = [
        {
            "hour": h,
            "grid_kwh": 50.0,
            "solar_used_kwh": 20.0,
            "battery_action": "idle",
            "battery_kwh": 0.0,
            "battery_energy_after_kwh": 80.0,
        }
        for h in range(24)
    ]

    mock_totals = {
        "total_grid_kwh": 1200.0,
        "total_cost_bdt": 9600.0,
        "peak_grid_kwh": 50.0,
    }

    async def fake_interpret(operator_notes, battery, hours):
        call_order.append("interpret_operator_notes")
        return mock_interpretations

    def fake_validate_interpretations(interpretations, operator_notes, battery):
        call_order.append("validate_interpretations")
        return interpretations

    def fake_optimize(hours, battery, directives):
        call_order.append("optimize_energy")
        return mock_plan

    def fake_validate_plan(hours, battery, directives, hourly_plan):
        call_order.append("validate_hourly_plan")
        return mock_totals

    with patch("app.orchestrator.interpret_operator_notes", side_effect=fake_interpret), \
         patch("app.orchestrator.validate_interpretations", side_effect=fake_validate_interpretations), \
         patch("app.orchestrator.optimize_energy", side_effect=fake_optimize), \
         patch("app.orchestrator.validate_hourly_plan", side_effect=fake_validate_plan):

        request_payload = make_valid_request(scenario_id="BUP-CAMPUS-01")
        response = client.post("/optimize-energy", json=request_payload)

        assert response.status_code == 200
        data = response.json()

        # Check call order
        assert call_order == [
            "interpret_operator_notes",
            "validate_interpretations",
            "optimize_energy",
            "validate_hourly_plan",
        ]

        # Check response structure
        assert data["scenario_id"] == "BUP-CAMPUS-01"
        assert len(data["directive_interpretation"]) == 1
        assert data["directive_interpretation"][0]["directive_type"] == "solar_reduction"
        assert len(data["hourly_plan"]) == 24
        assert data["total_grid_kwh"] == 1200.0
        assert data["total_cost_bdt"] == 9600.0
        assert data["peak_grid_kwh"] == 50.0
        assert "Applied 1 operating directive" in data["plan_summary"]


def test_optimize_energy_invalid_request_returns_400():
    """Verify that malformed or invalid request payloads return HTTP 400."""
    # Invalid: 0 notes
    payload = make_valid_request(operator_notes=[])
    response = client.post("/optimize-energy", json=payload)
    assert response.status_code == 400
    assert response.json()["error"] == "REQUEST_VALIDATION_ERROR"

    # Invalid: malformed body
    response = client.post(
        "/optimize-energy",
        content="not valid json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 400


def test_optimize_energy_interpretation_error_handling():
    """Verify controlled error response when LLM interpreter raises InterpretationError."""
    with patch(
        "app.orchestrator.interpret_operator_notes",
        AsyncMock(side_effect=InterpretationError("Failed to interpret notes")),
    ):
        response = client.post("/optimize-energy", json=make_valid_request())
        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "INTERPRETATION_ERROR"
        assert "Failed to interpret notes" in data["detail"]


def test_optimize_energy_provider_error_handling():
    """Verify controlled error response when LLM provider raises ProviderError."""
    with patch(
        "app.orchestrator.interpret_operator_notes",
        AsyncMock(side_effect=ProviderError("LLM API timed out after 20s")),
    ):
        response = client.post("/optimize-energy", json=make_valid_request())
        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "PROVIDER_ERROR"
        assert "timed out" in data["detail"]


def test_optimize_energy_guardrail_validation_error_handling():
    """Verify controlled error response when guardrails raise GuardrailValidationError."""
    with patch(
        "app.orchestrator.interpret_operator_notes",
        AsyncMock(return_value=[]),
    ), patch(
        "app.orchestrator.validate_interpretations",
        MagicMock(side_effect=GuardrailValidationError("Invalid directive shape")),
    ):
        response = client.post("/optimize-energy", json=make_valid_request())
        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "GUARDRAIL_VALIDATION_ERROR"
        assert "Invalid directive shape" in data["detail"]


def test_optimize_energy_optimization_error_handling():
    """Verify controlled error response when optimizer raises OptimizationError."""
    with patch(
        "app.orchestrator.interpret_operator_notes",
        AsyncMock(return_value=[]),
    ), patch(
        "app.orchestrator.validate_interpretations",
        MagicMock(return_value=[]),
    ), patch(
        "app.orchestrator.optimize_energy",
        MagicMock(side_effect=OptimizationError("Infeasible MILP problem")),
    ):
        response = client.post("/optimize-energy", json=make_valid_request())
        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "OPTIMIZATION_ERROR"
        assert "Infeasible" in data["detail"]


def test_optimize_energy_plan_validation_error_handling():
    """Verify controlled error response when validator raises PlanValidationError."""
    with patch(
        "app.orchestrator.interpret_operator_notes",
        AsyncMock(return_value=[]),
    ), patch(
        "app.orchestrator.validate_interpretations",
        MagicMock(return_value=[]),
    ), patch(
        "app.orchestrator.optimize_energy",
        MagicMock(return_value=[]),
    ), patch(
        "app.orchestrator.validate_hourly_plan",
        MagicMock(side_effect=PlanValidationError("Battery energy balance violated at hour 14")),
    ):
        response = client.post("/optimize-energy", json=make_valid_request())
        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "PLAN_VALIDATION_ERROR"
        assert "Battery energy balance violated" in data["detail"]


def test_unhandled_exception_does_not_leak_secrets_or_stacktrace():
    """Verify that unexpected internal errors do not leak stack traces or secret strings."""
    secret_value = "SUPER_SECRET_KEY_12345"

    with patch(
        "app.orchestrator.interpret_operator_notes",
        AsyncMock(side_effect=RuntimeError(f"Internal crash with secret={secret_value}")),
    ):
        response = client.post("/optimize-energy", json=make_valid_request())
        assert response.status_code == 500
        data = response.json()
        assert data["error"] == "INTERNAL_SERVER_ERROR"
        # Must NOT leak secret or internal exception message
        assert secret_value not in response.text
        assert "Traceback" not in response.text
