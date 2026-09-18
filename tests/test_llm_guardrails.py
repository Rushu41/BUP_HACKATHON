import pytest
from app.guardrails import validate_interpretations, GuardrailValidationError

def test_guardrail_wrong_note_count():
    notes = ["note 1", "note 2"]
    battery = {"capacity_kwh": 100}
    interpretations = [
        {"note_index": 0, "applies": False, "directive_type": "no_op", "structured_adjustment": None, "explanation": "x"}
    ]
    with pytest.raises(GuardrailValidationError, match="Expected 2 interpretations, got 1"):
        validate_interpretations(interpretations, notes, battery)

def test_guardrail_duplicate_note_index():
    notes = ["note 1", "note 2"]
    battery = {"capacity_kwh": 100}
    interpretations = [
        {"note_index": 0, "applies": False, "directive_type": "no_op", "structured_adjustment": None, "explanation": "x"},
        {"note_index": 0, "applies": False, "directive_type": "no_op", "structured_adjustment": None, "explanation": "x"}
    ]
    with pytest.raises(GuardrailValidationError, match="Invalid note_index sequence"):
        validate_interpretations(interpretations, notes, battery)

def test_guardrail_missing_note_index():
    notes = ["note 1"]
    battery = {"capacity_kwh": 100}
    interpretations = [
        {"applies": False, "directive_type": "no_op", "structured_adjustment": None, "explanation": "x"}
    ]
    with pytest.raises(GuardrailValidationError, match="All notes must have an integer note_index"):
        validate_interpretations(interpretations, notes, battery)

def test_guardrail_unsupported_directive():
    notes = ["note 1"]
    battery = {"capacity_kwh": 100}
    interpretations = [
        {"note_index": 0, "applies": True, "directive_type": "demand_reduction", "structured_adjustment": {"hours": [1]}, "explanation": "x"}
    ]
    with pytest.raises(GuardrailValidationError, match="Unsupported directive type"):
        validate_interpretations(interpretations, notes, battery)

def test_guardrail_factor_out_of_bounds():
    notes = ["note 1"]
    battery = {"capacity_kwh": 100}
    # factor 1.5
    with pytest.raises(GuardrailValidationError, match="factor must be between 0 and 1"):
        validate_interpretations([{"note_index": 0, "applies": True, "directive_type": "solar_reduction", "structured_adjustment": {"hours": [1], "factor": 1.5}, "explanation": "x"}], notes, battery)
    # factor -0.2
    with pytest.raises(GuardrailValidationError, match="factor must be between 0 and 1"):
        validate_interpretations([{"note_index": 0, "applies": True, "directive_type": "solar_reduction", "structured_adjustment": {"hours": [1], "factor": -0.2}, "explanation": "x"}], notes, battery)

def test_guardrail_invalid_hours():
    notes = ["note 1"]
    battery = {"capacity_kwh": 100}
    # hour 24
    with pytest.raises(GuardrailValidationError, match="all hours must be between 0 and 23"):
        validate_interpretations([{"note_index": 0, "applies": True, "directive_type": "no_charge_window", "structured_adjustment": {"hours": [24]}, "explanation": "x"}], notes, battery)
    # hour -1
    with pytest.raises(GuardrailValidationError, match="all hours must be between 0 and 23"):
        validate_interpretations([{"note_index": 0, "applies": True, "directive_type": "no_charge_window", "structured_adjustment": {"hours": [-1]}, "explanation": "x"}], notes, battery)
    # duplicate hours
    with pytest.raises(GuardrailValidationError, match="duplicate hours are not allowed"):
        validate_interpretations([{"note_index": 0, "applies": True, "directive_type": "no_charge_window", "structured_adjustment": {"hours": [1, 1]}, "explanation": "x"}], notes, battery)

def test_guardrail_reserve_gt_capacity():
    notes = ["note 1"]
    battery = {"capacity_kwh": 100}
    with pytest.raises(GuardrailValidationError, match="minimum_energy_kwh must be >= 0 and <= 100"):
        validate_interpretations([{"note_index": 0, "applies": True, "directive_type": "minimum_battery_reserve", "structured_adjustment": {"hours": [1], "minimum_energy_kwh": 150}, "explanation": "x"}], notes, battery)

def test_guardrail_negative_grid_cap():
    notes = ["note 1"]
    battery = {"capacity_kwh": 100}
    with pytest.raises(GuardrailValidationError, match="max_grid_kwh must be >= 0"):
        validate_interpretations([{"note_index": 0, "applies": True, "directive_type": "max_grid_window", "structured_adjustment": {"hours": [1], "max_grid_kwh": -5}, "explanation": "x"}], notes, battery)

def test_guardrail_noop_applies_true():
    notes = ["note 1"]
    battery = {"capacity_kwh": 100}
    with pytest.raises(GuardrailValidationError, match="no_op must have applies = false"):
        validate_interpretations([{"note_index": 0, "applies": True, "directive_type": "no_op", "structured_adjustment": None, "explanation": "x"}], notes, battery)

def test_guardrail_noop_non_null_adj():
    notes = ["note 1"]
    battery = {"capacity_kwh": 100}
    with pytest.raises(GuardrailValidationError, match="no_op must have structured_adjustment = null"):
        validate_interpretations([{"note_index": 0, "applies": False, "directive_type": "no_op", "structured_adjustment": {}, "explanation": "x"}], notes, battery)

def test_guardrail_real_directive_applies_false():
    notes = ["note 1"]
    battery = {"capacity_kwh": 100}
    with pytest.raises(GuardrailValidationError, match="no_charge_window must have applies = true"):
        validate_interpretations([{"note_index": 0, "applies": False, "directive_type": "no_charge_window", "structured_adjustment": {"hours": [1]}, "explanation": "x"}], notes, battery)

def test_guardrail_real_directive_null_adj():
    notes = ["note 1"]
    battery = {"capacity_kwh": 100}
    with pytest.raises(GuardrailValidationError, match="no_charge_window must have a non-null structured_adjustment object"):
        validate_interpretations([{"note_index": 0, "applies": True, "directive_type": "no_charge_window", "structured_adjustment": None, "explanation": "x"}], notes, battery)
