"""
tests/test_directives.py — GridWise Developer 2

Unit tests for app/directives.py (apply_directives).
"""
import pytest
from app.directives import apply_directives, EffectiveConstraints


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_hours(solar=10.0, demand=8.0, tariff=5.0):
    """Return 24 uniform hour dicts."""
    return [
        {
            "hour": h,
            "demand_kwh": demand,
            "solar_kwh": solar,
            "tariff_bdt_per_kwh": tariff,
        }
        for h in range(24)
    ]


def make_battery(
    capacity=100.0,
    initial=50.0,
    minimum=10.0,
    max_charge=20.0,
    max_discharge=20.0,
):
    return {
        "capacity_kwh": capacity,
        "initial_energy_kwh": initial,
        "minimum_energy_kwh": minimum,
        "max_charge_kwh_per_hour": max_charge,
        "max_discharge_kwh_per_hour": max_discharge,
    }


def directive(dtype, sa, applies=True, idx=0):
    return {
        "note_index": idx,
        "applies": applies,
        "directive_type": dtype,
        "structured_adjustment": sa,
        "explanation": "test",
    }


def no_op(idx=0):
    return {
        "note_index": idx,
        "applies": False,
        "directive_type": "no_op",
        "structured_adjustment": None,
        "explanation": "no-op",
    }


# ---------------------------------------------------------------------------
# Tests — no directives
# ---------------------------------------------------------------------------

def test_no_directives_solar_unchanged():
    hours = make_hours(solar=12.0)
    battery = make_battery()
    result = apply_directives(hours, battery, [])
    assert result.effective_solar == [12.0] * 24


def test_no_directives_min_reserve_is_base():
    battery = make_battery(minimum=10.0)
    result = apply_directives(make_hours(), battery, [])
    assert all(r == 10.0 for r in result.active_min_reserve)


def test_no_directives_no_restrictions():
    result = apply_directives(make_hours(), make_battery(), [])
    assert result.no_charge_hours == set()
    assert result.no_discharge_hours == set()
    assert all(v is None for v in result.max_grid_per_hour)


# ---------------------------------------------------------------------------
# Tests — solar_reduction
# ---------------------------------------------------------------------------

def test_solar_reduction_affected_hours():
    hours = make_hours(solar=100.0)
    d = directive("solar_reduction", {"hours": [10, 11, 12], "factor": 0.25})
    result = apply_directives(hours, make_battery(), [d])
    for h in [10, 11, 12]:
        assert abs(result.effective_solar[h] - 25.0) < 1e-9
    for h in range(24):
        if h not in [10, 11, 12]:
            assert abs(result.effective_solar[h] - 100.0) < 1e-9


def test_solar_reduction_to_zero():
    hours = make_hours(solar=50.0)
    d = directive("solar_reduction", {"hours": [6], "factor": 0.0})
    result = apply_directives(hours, make_battery(), [d])
    assert result.effective_solar[6] == 0.0


def test_solar_reduction_factor_is_remaining():
    hours = make_hours(solar=200.0)
    d = directive("solar_reduction", {"hours": [8], "factor": 0.20})
    result = apply_directives(hours, make_battery(), [d])
    assert abs(result.effective_solar[8] - 40.0) < 1e-9  # 200 * 0.20


def test_solar_reduction_multiple_rules_same_hour():
    """Overlapping solar reduction factors are multiplied."""
    hours = make_hours(solar=100.0)
    d1 = directive("solar_reduction", {"hours": [5], "factor": 0.5}, idx=0)
    d2 = directive("solar_reduction", {"hours": [5], "factor": 0.5}, idx=1)
    result = apply_directives(hours, make_battery(), [d1, d2])
    # 100 * 0.5 * 0.5 = 25
    assert abs(result.effective_solar[5] - 25.0) < 1e-9


# ---------------------------------------------------------------------------
# Tests — minimum_battery_reserve
# ---------------------------------------------------------------------------

def test_minimum_reserve_raised_for_affected_hours():
    battery = make_battery(minimum=10.0)
    d = directive("minimum_battery_reserve", {"hours": [20, 21, 22], "minimum_energy_kwh": 30.0})
    result = apply_directives(make_hours(), battery, [d])
    for h in [20, 21, 22]:
        assert result.active_min_reserve[h] == 30.0
    for h in range(24):
        if h not in [20, 21, 22]:
            assert result.active_min_reserve[h] == 10.0


def test_minimum_reserve_does_not_go_below_base():
    battery = make_battery(minimum=15.0)
    d = directive("minimum_battery_reserve", {"hours": [5], "minimum_energy_kwh": 5.0})
    result = apply_directives(make_hours(), battery, [d])
    # Directive value (5) < base (15) → base wins
    assert result.active_min_reserve[5] == 15.0


def test_minimum_reserve_multiple_directives_max_wins():
    battery = make_battery(minimum=5.0)
    d1 = directive("minimum_battery_reserve", {"hours": [3], "minimum_energy_kwh": 20.0}, idx=0)
    d2 = directive("minimum_battery_reserve", {"hours": [3], "minimum_energy_kwh": 35.0}, idx=1)
    result = apply_directives(make_hours(), battery, [d1, d2])
    assert result.active_min_reserve[3] == 35.0


# ---------------------------------------------------------------------------
# Tests — no_charge_window
# ---------------------------------------------------------------------------

def test_no_charge_window():
    d = directive("no_charge_window", {"hours": [13, 14, 15]})
    result = apply_directives(make_hours(), make_battery(), [d])
    assert {13, 14, 15}.issubset(result.no_charge_hours)


def test_no_charge_window_multiple():
    d1 = directive("no_charge_window", {"hours": [0, 1]}, idx=0)
    d2 = directive("no_charge_window", {"hours": [22, 23]}, idx=1)
    result = apply_directives(make_hours(), make_battery(), [d1, d2])
    assert result.no_charge_hours == {0, 1, 22, 23}


# ---------------------------------------------------------------------------
# Tests — no_discharge_window
# ---------------------------------------------------------------------------

def test_no_discharge_window():
    d = directive("no_discharge_window", {"hours": [8, 9, 10]})
    result = apply_directives(make_hours(), make_battery(), [d])
    assert {8, 9, 10}.issubset(result.no_discharge_hours)


# ---------------------------------------------------------------------------
# Tests — max_grid_window
# ---------------------------------------------------------------------------

def test_max_grid_window():
    d = directive("max_grid_window", {"hours": [18, 19], "max_grid_kwh": 5.0})
    result = apply_directives(make_hours(), make_battery(), [d])
    assert result.max_grid_per_hour[18] == 5.0
    assert result.max_grid_per_hour[19] == 5.0
    assert result.max_grid_per_hour[17] is None


def test_max_grid_window_most_restrictive_wins():
    d1 = directive("max_grid_window", {"hours": [10], "max_grid_kwh": 10.0}, idx=0)
    d2 = directive("max_grid_window", {"hours": [10], "max_grid_kwh": 6.0}, idx=1)
    result = apply_directives(make_hours(), make_battery(), [d1, d2])
    assert result.max_grid_window_effective_at_10 if False else result.max_grid_per_hour[10] == 6.0


# ---------------------------------------------------------------------------
# Tests — no_op
# ---------------------------------------------------------------------------

def test_no_op_changes_nothing():
    hours = make_hours(solar=50.0)
    battery = make_battery(minimum=8.0)
    result = apply_directives(hours, battery, [no_op()])
    assert result.effective_solar == [50.0] * 24
    assert all(r == 8.0 for r in result.active_min_reserve)
    assert result.no_charge_hours == set()
    assert result.no_discharge_hours == set()
    assert all(v is None for v in result.max_grid_per_hour)


def test_applies_false_ignored():
    hours = make_hours(solar=100.0)
    d = directive("solar_reduction", {"hours": [0], "factor": 0.1}, applies=False)
    result = apply_directives(hours, make_battery(), [d])
    # applies=False → no change
    assert abs(result.effective_solar[0] - 100.0) < 1e-9


# ---------------------------------------------------------------------------
# Tests — return type
# ---------------------------------------------------------------------------

def test_returns_effective_constraints_type():
    result = apply_directives(make_hours(), make_battery(), [])
    assert isinstance(result, EffectiveConstraints)
    assert len(result.effective_solar) == 24
    assert len(result.active_min_reserve) == 24
    assert len(result.max_grid_per_hour) == 24
