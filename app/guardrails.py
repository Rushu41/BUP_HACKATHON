"""Deterministic guardrails validating structured LLM directive interpretations."""

import math
from typing import Any, Dict, List
from app.exceptions import GuardrailValidationError

ALLOWED_DIRECTIVES = {
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
}


def _validate_hours(hours: Any, directive_type: str) -> List[int]:
    """Validates hours list strictly ensuring integer type, no booleans, bounds, and non-empty."""
    if not isinstance(hours, list):
        raise GuardrailValidationError(f"{directive_type}: hours must be a list")

    if len(hours) == 0:
        raise GuardrailValidationError(f"{directive_type}: hours list cannot be empty")

    if not all(isinstance(h, int) and not isinstance(h, bool) for h in hours):
        raise GuardrailValidationError(f"{directive_type}: all hours must be integers (booleans not allowed)")

    if not all(0 <= h <= 23 for h in hours):
        raise GuardrailValidationError(f"{directive_type}: all hours must be between 0 and 23")

    if len(set(hours)) != len(hours):
        raise GuardrailValidationError(f"{directive_type}: duplicate hours are not allowed")

    return sorted(hours)


def _is_finite_number(val: Any) -> bool:
    """Checks that value is a finite number and strictly not a boolean."""
    if isinstance(val, bool):
        return False
    if not isinstance(val, (int, float)):
        return False
    return math.isfinite(val)


def validate_interpretations(
    interpretations: List[Dict[str, Any]],
    operator_notes: List[str],
    battery: Any,
) -> List[Dict[str, Any]]:
    """Deterministically validates structured directive interpretations against official bounds."""
    if not isinstance(interpretations, list):
        raise GuardrailValidationError("Interpretations must be a list")

    if len(interpretations) != len(operator_notes):
        raise GuardrailValidationError(f"Expected {len(operator_notes)} interpretations, got {len(interpretations)}")

    # Check note indices
    for note in interpretations:
        if not isinstance(note, dict):
            raise GuardrailValidationError("Each interpretation must be a dictionary")
        idx = note.get("note_index")
        if idx is None or not isinstance(idx, int) or isinstance(idx, bool):
            raise GuardrailValidationError("All notes must have an integer note_index (booleans not allowed)")

    sorted_interpretations = sorted(interpretations, key=lambda x: x["note_index"])
    sorted_indices = [note["note_index"] for note in sorted_interpretations]
    expected_indices = list(range(len(operator_notes)))

    if sorted_indices != expected_indices:
        raise GuardrailValidationError(f"Invalid note_index sequence: {sorted_indices}, expected: {expected_indices}")

    # Extract battery capacity safely
    if hasattr(battery, "capacity_kwh"):
        capacity = float(battery.capacity_kwh)
    elif isinstance(battery, dict):
        capacity = float(battery.get("capacity_kwh", float("inf")))
    else:
        capacity = float("inf")

    validated_results = []

    for note in sorted_interpretations:
        directive_type = note.get("directive_type")
        if directive_type not in ALLOWED_DIRECTIVES:
            raise GuardrailValidationError(f"Unsupported directive type: {directive_type}")

        applies = note.get("applies")
        if not isinstance(applies, bool):
            raise GuardrailValidationError(f"{directive_type}: applies must be a boolean")

        adj = note.get("structured_adjustment")

        if directive_type == "no_op":
            if applies is not False:
                raise GuardrailValidationError("no_op must have applies = false")
            if adj is not None:
                raise GuardrailValidationError("no_op must have structured_adjustment = null")
        else:
            if applies is not True:
                raise GuardrailValidationError(f"{directive_type} must have applies = true")
            if adj is None or not isinstance(adj, dict):
                raise GuardrailValidationError(f"{directive_type} must have a non-null structured_adjustment object")

            hours = adj.get("hours")
            if hours is None:
                raise GuardrailValidationError(f"{directive_type} missing 'hours'")

            validated_hours = _validate_hours(hours, directive_type)
            adj["hours"] = validated_hours

            # Type specific validation
            if directive_type == "solar_reduction":
                if "factor" not in adj:
                    raise GuardrailValidationError("solar_reduction missing 'factor'")
                factor = adj["factor"]
                if not _is_finite_number(factor) or factor < 0.0 or factor > 1.0:
                    raise GuardrailValidationError(f"solar_reduction factor must be between 0 and 1, got {factor}")
                if len(adj) != 2:
                    raise GuardrailValidationError("solar_reduction must only have 'hours' and 'factor'")

            elif directive_type == "minimum_battery_reserve":
                if "minimum_energy_kwh" not in adj:
                    raise GuardrailValidationError("minimum_battery_reserve missing 'minimum_energy_kwh'")
                min_kwh = adj["minimum_energy_kwh"]
                cap_str = f"{int(capacity)}" if isinstance(capacity, (int, float)) and float(capacity).is_integer() else f"{capacity}"
                if not _is_finite_number(min_kwh) or min_kwh < 0.0 or min_kwh > capacity:
                    raise GuardrailValidationError(f"minimum_energy_kwh must be >= 0 and <= {cap_str}, got {min_kwh}")
                if len(adj) != 2:
                    raise GuardrailValidationError("minimum_battery_reserve must only have 'hours' and 'minimum_energy_kwh'")

            elif directive_type == "max_grid_window":
                if "max_grid_kwh" not in adj:
                    raise GuardrailValidationError("max_grid_window missing 'max_grid_kwh'")
                max_kwh = adj["max_grid_kwh"]
                if not _is_finite_number(max_kwh) or max_kwh < 0.0:
                    raise GuardrailValidationError(f"max_grid_kwh must be >= 0, got {max_kwh}")
                if len(adj) != 2:
                    raise GuardrailValidationError("max_grid_window must only have 'hours' and 'max_grid_kwh'")

            elif directive_type in ["no_charge_window", "no_discharge_window"]:
                if len(adj) != 1:
                    raise GuardrailValidationError(f"{directive_type} must only have 'hours'")

        canonical_note = {
            "note_index": note["note_index"],
            "applies": note["applies"],
            "directive_type": directive_type,
            "structured_adjustment": adj,
            "explanation": str(note.get("explanation", "")),
        }
        validated_results.append(canonical_note)

    return validated_results
