"""Core orchestration module coordinating LLM, guardrails, optimizer, and validator."""

from typing import Any

from app.exceptions import (
    GridWiseError,
    GuardrailValidationError,
    InterpretationError,
    OptimizationError,
    PlanValidationError,
    ProviderError,
)
from app.guardrails import validate_interpretations
from app.llm_interpreter import interpret_operator_notes
from app.optimizer import optimize_energy
from app.schemas import (
    DirectiveInterpretation,
    DirectiveType,
    HourlyPlanEntry,
    OptimizeEnergyRequest,
    OptimizeEnergyResponse,
)
from app.validator import validate_hourly_plan


def generate_plan_summary(directives: list[Any]) -> str:
    """Deterministically generates a concise human-readable summary of the optimization plan."""
    active_count = 0
    directive_descriptions = []

    for d in directives:
        if isinstance(d, dict):
            applies = d.get("applies", False)
            dtype = d.get("directive_type", "no_op")
        else:
            applies = getattr(d, "applies", False)
            dtype = getattr(d, "directive_type", "no_op")

        if applies and dtype != "no_op":
            active_count += 1
            if dtype == DirectiveType.SOLAR_REDUCTION.value or dtype == DirectiveType.SOLAR_REDUCTION:
                directive_descriptions.append("solar reduction")
            elif dtype == DirectiveType.MINIMUM_BATTERY_RESERVE.value or dtype == DirectiveType.MINIMUM_BATTERY_RESERVE:
                directive_descriptions.append("battery reserve")
            elif dtype == DirectiveType.NO_CHARGE_WINDOW.value or dtype == DirectiveType.NO_CHARGE_WINDOW:
                directive_descriptions.append("charge restriction")
            elif dtype == DirectiveType.NO_DISCHARGE_WINDOW.value or dtype == DirectiveType.NO_DISCHARGE_WINDOW:
                directive_descriptions.append("discharge restriction")
            elif dtype == DirectiveType.MAX_GRID_WINDOW.value or dtype == DirectiveType.MAX_GRID_WINDOW:
                directive_descriptions.append("grid import cap")

    if active_count == 0:
        return (
            "No active operating directives applied. Optimized grid use across the "
            "24-hour horizon and restored battery to its initial energy level."
        )
    elif active_count == 1:
        desc = directive_descriptions[0] if directive_descriptions else "operating"
        return (
            f"Applied 1 operating directive ({desc}), optimized grid use across the "
            "24-hour horizon, and restored battery to its initial energy level."
        )
    else:
        desc = ", ".join(directive_descriptions)
        return (
            f"Applied {active_count} operating directives ({desc}), optimized grid use across the "
            "24-hour horizon, and restored battery to its initial energy level."
        )


async def process_scenario(request: OptimizeEnergyRequest) -> OptimizeEnergyResponse:
    """Executes the end-to-end energy optimization pipeline for a single scenario."""
    # Step 1: Interpret operator notes using language model
    raw_interpretations = await interpret_operator_notes(
        operator_notes=request.operator_notes,
        battery=request.battery,
        hours=request.hours,
    )

    # Step 2: Validate LLM interpretation through deterministic guardrails
    directives = validate_interpretations(
        interpretations=raw_interpretations,
        operator_notes=request.operator_notes,
        battery=request.battery,
    )

    # Step 3: Compute optimal 24-hour energy dispatch schedule
    hourly_plan = optimize_energy(
        hours=request.hours,
        battery=request.battery,
        directives=directives,
    )

    # Step 4: Independently verify schedule validity and calculate totals
    totals = validate_hourly_plan(
        hours=request.hours,
        battery=request.battery,
        directives=directives,
        hourly_plan=hourly_plan,
    )

    # Step 5: Deterministically summarize the plan
    plan_summary = generate_plan_summary(directives)

    # Step 6: Construct and return final validated response
    return OptimizeEnergyResponse(
        scenario_id=request.scenario_id,
        directive_interpretation=directives,
        hourly_plan=hourly_plan,
        total_grid_kwh=float(totals["total_grid_kwh"]),
        total_cost_bdt=float(totals["total_cost_bdt"]),
        peak_grid_kwh=float(totals["peak_grid_kwh"]),
        plan_summary=plan_summary,
    )
