"""
tests/test_validator.py — GridWise Developer 2

Unit tests for app/validator.py (validate_hourly_plan).
Tests cover valid plans and all categories of violations.
"""
import math
import pytest
from app.validator import validate_hourly_plan, PlanValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_hours(demand=5.0, solar=3.0, tariff=5.0):
    return [
        {"hour": h, "demand_kwh": demand, "solar_kwh": solar,
         "tariff_bdt_per_kwh": tariff}
        for h in range(24)
    ]


def make_battery(
    capacity=50.0, initial=20.0, minimum=5.0,
    max_charge=10.0, max_discharge=10.0
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


def make_valid_plan(battery, hours, directives=None):
    """Build a trivially valid plan: grid covers demand, no battery action."""
    from app.optimizer import optimize_energy
    return optimize_energy(hours, battery, directives or [])


def build_simple_idle_plan(demand=5.0, solar=3.0, tariff=5.0, initial=20.0):
    """
    Build a hand-crafted valid plan: grid = demand - solar, battery idle,
    battery stays at initial throughout.
    """
    grid = max(demand - solar, 0.0)
    sol = min(solar, demand)
    plan = []
    for h in range(24):
        plan.append({
            "hour": h,
            "grid_kwh": grid,
            "solar_used_kwh": sol,
            "battery_action": "idle",
            "battery_kwh": 0.0,
            "battery_energy_after_kwh": initial,
        })
    return plan


# ---------------------------------------------------------------------------
# Tests — valid plans
# ---------------------------------------------------------------------------

class TestValidPlan:
    def test_valid_plan_returns_totals(self):
        hours = make_hours(demand=5.0, solar=3.0, tariff=4.0)
        battery = make_battery(initial=20.0)
        plan = build_simple_idle_plan(demand=5.0, solar=3.0, tariff=4.0, initial=20.0)
        result = validate_hourly_plan(hours, battery, [], plan)
        assert "total_grid_kwh" in result
        assert "total_cost_bdt" in result
        assert "peak_grid_kwh" in result

    def test_totals_computed_correctly(self):
        hours = make_hours(demand=5.0, solar=3.0, tariff=4.0)
        battery = make_battery(initial=20.0)
        plan = build_simple_idle_plan(demand=5.0, solar=3.0, tariff=4.0, initial=20.0)
        result = validate_hourly_plan(hours, battery, [], plan)
        # grid = 2.0 * 24 hours
        assert abs(result["total_grid_kwh"] - 48.0) < 0.01
        assert abs(result["total_cost_bdt"] - 48.0 * 4.0) < 0.01
        assert abs(result["peak_grid_kwh"] - 2.0) < 0.01

    def test_optimizer_output_is_valid(self):
        hours = make_hours(demand=8.0, solar=4.0, tariff=5.0)
        battery = make_battery(initial=25.0)
        from app.optimizer import optimize_energy
        plan = optimize_energy(hours, battery, [])
        result = validate_hourly_plan(hours, battery, [], plan)
        assert result["total_grid_kwh"] >= 0.0
        assert result["total_cost_bdt"] >= 0.0

    def test_optimizer_output_with_directives_is_valid(self):
        hours = make_hours(demand=8.0, solar=5.0, tariff=5.0)
        battery = make_battery(initial=25.0)
        directives = [
            directive("no_charge_window", {"hours": [0, 1, 2]}, idx=0),
            directive("solar_reduction", {"hours": [10, 11], "factor": 0.5}, idx=1),
        ]
        from app.optimizer import optimize_energy
        plan = optimize_energy(hours, battery, directives)
        result = validate_hourly_plan(hours, battery, directives, plan)
        assert result["total_grid_kwh"] >= 0.0


# ---------------------------------------------------------------------------
# Tests — structural violations
# ---------------------------------------------------------------------------

class TestStructuralViolations:
    def test_wrong_number_of_entries(self):
        hours = make_hours()
        battery = make_battery()
        plan = build_simple_idle_plan()[:23]  # only 23
        with pytest.raises(PlanValidationError, match="24"):
            validate_hourly_plan(hours, battery, [], plan)

    def test_duplicate_hour(self):
        hours = make_hours()
        battery = make_battery()
        plan = build_simple_idle_plan()
        plan[5]["hour"] = plan[6]["hour"]  # make hour 6 appear twice
        with pytest.raises(PlanValidationError, match="[Dd]uplicate"):
            validate_hourly_plan(hours, battery, [], plan)

    def test_missing_hour(self):
        hours = make_hours()
        battery = make_battery()
        plan = build_simple_idle_plan()
        plan[10]["hour"] = 99  # invalid hour
        with pytest.raises(PlanValidationError):
            validate_hourly_plan(hours, battery, [], plan)

    def test_invalid_battery_action(self):
        hours = make_hours()
        battery = make_battery()
        plan = build_simple_idle_plan()
        plan[0]["battery_action"] = "explode"
        with pytest.raises(PlanValidationError, match="[Vv]alid|action"):
            validate_hourly_plan(hours, battery, [], plan)

    def test_negative_grid(self):
        hours = make_hours()
        battery = make_battery()
        plan = build_simple_idle_plan()
        plan[0]["grid_kwh"] = -1.0
        with pytest.raises(PlanValidationError, match="[Nn]egative"):
            validate_hourly_plan(hours, battery, [], plan)

    def test_idle_with_nonzero_battery_kwh(self):
        hours = make_hours()
        battery = make_battery()
        plan = build_simple_idle_plan()
        plan[5]["battery_action"] = "idle"
        plan[5]["battery_kwh"] = 3.0  # should be 0 for idle
        with pytest.raises(PlanValidationError):
            validate_hourly_plan(hours, battery, [], plan)

    def test_non_finite_grid(self):
        hours = make_hours()
        battery = make_battery()
        plan = build_simple_idle_plan()
        plan[0]["grid_kwh"] = float("nan")
        with pytest.raises(PlanValidationError, match="[Ff]inite|nan"):
            validate_hourly_plan(hours, battery, [], plan)


# ---------------------------------------------------------------------------
# Tests — battery physics violations
# ---------------------------------------------------------------------------

class TestBatteryPhysicsViolations:
    def test_wrong_battery_transition(self):
        hours = make_hours()
        battery = make_battery(initial=20.0)
        plan = build_simple_idle_plan(initial=20.0)
        # Force a wrong battery_energy_after at hour 5
        plan[5]["battery_energy_after_kwh"] = 999.0
        with pytest.raises(PlanValidationError, match="[Bb]attery|mismatch|transition"):
            validate_hourly_plan(hours, battery, [], plan)

    def test_battery_over_capacity(self):
        hours = make_hours()
        battery = make_battery(initial=20.0, capacity=50.0)
        plan = build_simple_idle_plan(initial=20.0)
        # Manually set all battery energies to exceed capacity
        for e in plan:
            e["battery_energy_after_kwh"] = 55.0
        with pytest.raises(PlanValidationError, match="[Cc]apacity"):
            validate_hourly_plan(hours, battery, [], plan)

    def test_battery_under_minimum_reserve(self):
        hours = make_hours()
        battery = make_battery(initial=20.0, minimum=10.0)
        plan = build_simple_idle_plan(initial=5.0)  # 5 < minimum=10
        with pytest.raises(PlanValidationError, match="[Mm]inimum|reserve"):
            validate_hourly_plan(hours, battery, [], plan)

    def test_charge_above_rate(self):
        hours = make_hours()
        battery = make_battery(max_charge=5.0, initial=20.0)
        plan = build_simple_idle_plan(initial=20.0)
        # Inject a charge that exceeds max rate
        plan[3]["battery_action"] = "charge"
        plan[3]["battery_kwh"] = 8.0  # > max_charge=5
        plan[3]["battery_energy_after_kwh"] = 28.0
        # Fix all subsequent energies
        for i in range(4, 24):
            plan[i]["battery_energy_after_kwh"] = 28.0
        with pytest.raises(PlanValidationError, match="[Cc]harge|rate"):
            validate_hourly_plan(hours, battery, [], plan)

    def test_discharge_above_rate(self):
        hours = make_hours()
        battery = make_battery(max_discharge=5.0, initial=20.0)
        plan = build_simple_idle_plan(initial=20.0)
        plan[3]["battery_action"] = "discharge"
        plan[3]["battery_kwh"] = 9.0  # > max_discharge=5
        plan[3]["battery_energy_after_kwh"] = 11.0
        for i in range(4, 24):
            plan[i]["battery_energy_after_kwh"] = 11.0
        with pytest.raises(PlanValidationError, match="[Dd]ischarge|rate"):
            validate_hourly_plan(hours, battery, [], plan)

    def test_wrong_final_battery(self):
        hours = make_hours()
        battery = make_battery(initial=20.0)
        plan = build_simple_idle_plan(initial=20.0)
        plan[23]["battery_energy_after_kwh"] = 35.0  # not equal to initial
        with pytest.raises(PlanValidationError, match="[Nn]eutral|final"):
            validate_hourly_plan(hours, battery, [], plan)


# ---------------------------------------------------------------------------
# Tests — directive violations
# ---------------------------------------------------------------------------

class TestDirectiveViolations:
    def test_solar_overuse_detected(self):
        hours = make_hours(demand=5.0, solar=3.0)
        battery = make_battery(initial=20.0)
        d = directive("solar_reduction", {"hours": [10], "factor": 0.5})
        plan = build_simple_idle_plan(demand=5.0, solar=3.0, initial=20.0)
        # At hour 10 effective solar = 1.5, but plan says solar_used = 3.0
        plan[10]["solar_used_kwh"] = 3.0
        # Re-balance grid so energy balance is satisfied
        plan[10]["grid_kwh"] = max(5.0 - 3.0, 0.0)
        with pytest.raises(PlanValidationError, match="[Ss]olar"):
            validate_hourly_plan(hours, battery, [d], plan)

    def test_charge_during_no_charge_window(self):
        hours = make_hours(demand=5.0, solar=0.0)
        battery = make_battery(initial=20.0)
        d = directive("no_charge_window", {"hours": [5]})
        plan = build_simple_idle_plan(demand=5.0, solar=0.0, initial=20.0)
        plan[5]["battery_action"] = "charge"
        plan[5]["battery_kwh"] = 2.0
        plan[5]["battery_energy_after_kwh"] = 22.0
        # Adjust supply to balance
        plan[5]["grid_kwh"] = 7.0  # demand(5) + charge(2)
        for i in range(6, 24):
            plan[i]["battery_energy_after_kwh"] = 22.0
        with pytest.raises(PlanValidationError, match="[Cc]harge|no_charge"):
            validate_hourly_plan(hours, battery, [d], plan)

    def test_discharge_during_no_discharge_window(self):
        hours = make_hours(demand=5.0, solar=0.0)
        battery = make_battery(initial=20.0)
        d = directive("no_discharge_window", {"hours": [15]})
        plan = build_simple_idle_plan(demand=5.0, solar=0.0, initial=20.0)
        plan[15]["battery_action"] = "discharge"
        plan[15]["battery_kwh"] = 2.0
        plan[15]["battery_energy_after_kwh"] = 18.0
        plan[15]["grid_kwh"] = 3.0  # demand(5) - discharge(2)
        for i in range(16, 24):
            plan[i]["battery_energy_after_kwh"] = 18.0
        with pytest.raises(PlanValidationError, match="[Dd]ischarge|no_discharge"):
            validate_hourly_plan(hours, battery, [d], plan)

    def test_grid_above_cap(self):
        hours = make_hours(demand=10.0, solar=0.0)
        battery = make_battery(initial=20.0)
        d = directive("max_grid_window", {"hours": [20], "max_grid_kwh": 5.0})
        plan = build_simple_idle_plan(demand=10.0, solar=0.0, initial=20.0)
        # plan already has grid=10 at hour 20 > cap=5
        with pytest.raises(PlanValidationError, match="[Gg]rid|cap"):
            validate_hourly_plan(hours, battery, [d], plan)


# ---------------------------------------------------------------------------
# Tests — energy balance violation
# ---------------------------------------------------------------------------

class TestEnergyBalanceViolation:
    def test_wrong_energy_balance(self):
        hours = make_hours(demand=5.0, solar=3.0)
        battery = make_battery(initial=20.0)
        plan = build_simple_idle_plan(demand=5.0, solar=3.0, initial=20.0)
        # Corrupt hour 7: set grid to wrong value
        plan[7]["grid_kwh"] = 99.0
        with pytest.raises(PlanValidationError, match="[Bb]alance|supply"):
            validate_hourly_plan(hours, battery, [], plan)
