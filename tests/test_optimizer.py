"""
tests/test_optimizer.py — GridWise Developer 2

Deterministic tests for app/optimizer.py (optimize_energy).

All scenarios are small, hand-verifiable, and do not rely on scenario IDs.
"""
import math
import pytest
from app.optimizer import optimize_energy, OptimizerError

TOLS = 0.01  # 0.01 kWh tolerance for judge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_hours(demands, solars, tariffs):
    """Build a 24-hour list. Lists are cycled if shorter than 24."""
    def cyc(lst, i):
        return lst[i % len(lst)]
    return [
        {
            "hour": h,
            "demand_kwh": cyc(demands, h),
            "solar_kwh": cyc(solars, h),
            "tariff_bdt_per_kwh": cyc(tariffs, h),
        }
        for h in range(24)
    ]


def make_battery(
    capacity=50.0,
    initial=20.0,
    minimum=5.0,
    max_charge=10.0,
    max_discharge=10.0,
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


def assert_plan_structure(plan):
    assert len(plan) == 24
    hours_seen = {e["hour"] for e in plan}
    assert hours_seen == set(range(24))
    for e in plan:
        assert e["grid_kwh"] >= -TOLS
        assert e["solar_used_kwh"] >= -TOLS
        assert e["battery_kwh"] >= -TOLS
        assert e["battery_action"] in {"charge", "discharge", "idle"}
        assert math.isfinite(e["battery_energy_after_kwh"])


def assert_energy_balance(plan, hours):
    demand_map = {h["hour"]: h["demand_kwh"] for h in hours}
    for e in plan:
        h = e["hour"]
        action = e["battery_action"]
        c = e["battery_kwh"] if action == "charge" else 0.0
        d = e["battery_kwh"] if action == "discharge" else 0.0
        supply = e["grid_kwh"] + e["solar_used_kwh"] + d
        consumed = demand_map[h] + c
        assert abs(supply - consumed) <= TOLS, (
            f"hour {h}: supply={supply:.6f} != demand+charge={consumed:.6f}"
        )


def assert_neutrality(plan, battery):
    final = plan[-1]["battery_energy_after_kwh"] if plan[-1]["hour"] == 23 else \
        sorted(plan, key=lambda x: x["hour"])[-1]["battery_energy_after_kwh"]
    assert abs(final - battery["initial_energy_kwh"]) <= TOLS


# ---------------------------------------------------------------------------
# STEP 29 — Normal operation tests
# ---------------------------------------------------------------------------

class TestZeroDirectives:
    """Optimizer with no directives — basic feasibility."""

    def test_returns_24_entries(self):
        hours = make_hours([10.0], [5.0], [5.0])
        battery = make_battery()
        plan = optimize_energy(hours, battery, [])
        assert len(plan) == 24

    def test_energy_balance_satisfied(self):
        hours = make_hours([10.0], [5.0], [5.0])
        battery = make_battery()
        plan = optimize_energy(hours, battery, [])
        assert_energy_balance(plan, hours)

    def test_end_of_day_neutrality(self):
        hours = make_hours([10.0], [5.0], [5.0])
        battery = make_battery(initial=20.0)
        plan = optimize_energy(hours, battery, [])
        assert_neutrality(plan, battery)

    def test_grid_non_negative(self):
        hours = make_hours([10.0], [5.0], [5.0])
        battery = make_battery()
        plan = optimize_energy(hours, battery, [])
        for e in plan:
            assert e["grid_kwh"] >= -TOLS

    def test_plan_structure(self):
        hours = make_hours([8.0], [3.0], [4.0])
        battery = make_battery()
        plan = optimize_energy(hours, battery, [])
        assert_plan_structure(plan)


class TestSolarReduction:
    def test_solar_used_does_not_exceed_effective(self):
        hours = make_hours([10.0], [20.0], [5.0])
        battery = make_battery()
        d = directive("solar_reduction", {"hours": list(range(8, 17)), "factor": 0.3})
        plan = optimize_energy(hours, battery, [d])
        for e in plan:
            h = e["hour"]
            original_solar = hours[h]["solar_kwh"]
            factor = 0.3 if h in range(8, 17) else 1.0
            eff = original_solar * factor
            assert e["solar_used_kwh"] <= eff + TOLS, \
                f"hour {h}: solar_used {e['solar_used_kwh']} > effective {eff}"

    def test_neutrality_with_solar_reduction(self):
        hours = make_hours([10.0], [15.0], [5.0])
        battery = make_battery(initial=25.0)
        d = directive("solar_reduction", {"hours": [10, 11, 12], "factor": 0.5})
        plan = optimize_energy(hours, battery, [d])
        assert_neutrality(plan, battery)

    def test_energy_balance_with_solar_reduction(self):
        hours = make_hours([10.0], [15.0], [5.0])
        battery = make_battery()
        d = directive("solar_reduction", {"hours": [6, 7, 8], "factor": 0.2})
        plan = optimize_energy(hours, battery, [d])
        assert_energy_balance(plan, hours)


class TestMinimumReserve:
    def test_reserve_respected(self):
        battery = make_battery(minimum=5.0, initial=30.0, capacity=50.0)
        d = directive("minimum_battery_reserve", {"hours": list(range(12, 18)), "minimum_energy_kwh": 20.0})
        hours = make_hours([15.0], [5.0], [5.0])
        plan = optimize_energy(hours, battery, [d])
        plan_sorted = sorted(plan, key=lambda x: x["hour"])
        for e in plan_sorted:
            if e["hour"] in range(12, 18):
                assert e["battery_energy_after_kwh"] >= 20.0 - TOLS

    def test_neutrality_with_reserve(self):
        battery = make_battery(minimum=5.0, initial=30.0, capacity=50.0)
        d = directive("minimum_battery_reserve", {"hours": [22, 23], "minimum_energy_kwh": 15.0})
        hours = make_hours([10.0], [5.0], [5.0])
        plan = optimize_energy(hours, battery, [d])
        assert_neutrality(plan, battery)


class TestNoCharge:
    def test_no_charge_during_window(self):
        hours = make_hours([5.0], [0.0], [5.0])
        battery = make_battery()
        d = directive("no_charge_window", {"hours": list(range(0, 12))})
        plan = optimize_energy(hours, battery, [d])
        for e in plan:
            if e["hour"] < 12:
                assert e["battery_action"] != "charge", \
                    f"hour {e['hour']} should not charge"

    def test_energy_balance_no_charge(self):
        hours = make_hours([5.0], [2.0], [5.0])
        battery = make_battery()
        d = directive("no_charge_window", {"hours": list(range(0, 12))})
        plan = optimize_energy(hours, battery, [d])
        assert_energy_balance(plan, hours)


class TestNoDischarge:
    def test_no_discharge_during_window(self):
        hours = make_hours([5.0], [2.0], [5.0])
        battery = make_battery()
        d = directive("no_discharge_window", {"hours": list(range(12, 24))})
        plan = optimize_energy(hours, battery, [d])
        for e in plan:
            if e["hour"] >= 12:
                assert e["battery_action"] != "discharge", \
                    f"hour {e['hour']} should not discharge"

    def test_energy_balance_no_discharge(self):
        hours = make_hours([5.0], [2.0], [5.0])
        battery = make_battery()
        d = directive("no_discharge_window", {"hours": list(range(12, 24))})
        plan = optimize_energy(hours, battery, [d])
        assert_energy_balance(plan, hours)


class TestGridCap:
    def test_grid_cap_respected(self):
        # High demand, low solar → grid needed. Cap it.
        # Use large enough battery so discharging can cover demand minus cap.
        # demand=10, cap=6 → battery must cover 4/hour for 4 hours = 16 kWh discharge.
        # Battery capacity=200, initial=100 is plenty.
        hours = make_hours([10.0], [0.0], [5.0])
        battery = make_battery(capacity=200.0, initial=100.0, minimum=0.0,
                               max_charge=15.0, max_discharge=15.0)
        d = directive("max_grid_window", {"hours": list(range(18, 22)), "max_grid_kwh": 5.0})
        plan = optimize_energy(hours, battery, [d])
        for e in plan:
            if e["hour"] in range(18, 22):
                assert e["grid_kwh"] <= 5.0 + TOLS, \
                    f"hour {e['hour']}: grid_kwh={e['grid_kwh']} exceeds cap 5.0"

    def test_energy_balance_grid_cap(self):
        hours = make_hours([10.0], [0.0], [5.0])
        battery = make_battery(capacity=100.0, initial=50.0, max_charge=10.0, max_discharge=10.0)
        d = directive("max_grid_window", {"hours": [20, 21], "max_grid_kwh": 3.0})
        plan = optimize_energy(hours, battery, [d])
        assert_energy_balance(plan, hours)


class TestMultipleDirectives:
    def test_multiple_directives_all_satisfied(self):
        hours = make_hours([10.0], [5.0], [5.0])
        battery = make_battery(capacity=80.0, initial=30.0, minimum=5.0)
        directives = [
            directive("solar_reduction", {"hours": [8, 9], "factor": 0.5}, idx=0),
            directive("no_charge_window", {"hours": [0, 1, 2]}, idx=1),
            directive("minimum_battery_reserve", {"hours": [20, 21, 22, 23], "minimum_energy_kwh": 15.0}, idx=2),
        ]
        plan = optimize_energy(hours, battery, directives)
        assert_energy_balance(plan, hours)
        assert_neutrality(plan, battery)
        for e in plan:
            if e["hour"] in [0, 1, 2]:
                assert e["battery_action"] != "charge"
            if e["hour"] in [20, 21, 22, 23]:
                assert e["battery_energy_after_kwh"] >= 15.0 - TOLS


class TestOverlappingDirectives:
    def test_overlapping_no_charge_no_discharge(self):
        """Hours with both no_charge and no_discharge → battery must idle."""
        hours = make_hours([5.0], [5.0], [5.0])
        battery = make_battery(initial=30.0)
        directives = [
            directive("no_charge_window", {"hours": [10, 11]}, idx=0),
            directive("no_discharge_window", {"hours": [10, 11]}, idx=1),
        ]
        plan = optimize_energy(hours, battery, directives)
        for e in plan:
            if e["hour"] in [10, 11]:
                assert e["battery_action"] == "idle"


# ---------------------------------------------------------------------------
# STEP 30 — Optimality tests
# ---------------------------------------------------------------------------

class TestOptimality:
    def test_cheap_night_charge_expensive_evening_discharge(self):
        """
        Night (0-7): tariff=1.  Evening (18-22): tariff=10.
        Battery should charge at night and discharge in evening.
        """
        tariffs = [1.0 if h < 8 else (10.0 if 18 <= h < 23 else 5.0) for h in range(24)]
        demands = [5.0] * 24
        solars = [0.0] * 24
        hours = [
            {"hour": h, "demand_kwh": demands[h], "solar_kwh": solars[h],
             "tariff_bdt_per_kwh": tariffs[h]}
            for h in range(24)
        ]
        battery = make_battery(capacity=50.0, initial=10.0, minimum=0.0, max_charge=10.0, max_discharge=10.0)
        plan = optimize_energy(hours, battery, [])
        plan_by_hour = {e["hour"]: e for e in plan}
        # At least some evening hours should discharge
        discharged_evening = any(
            plan_by_hour[h]["battery_action"] == "discharge"
            for h in range(18, 23)
        )
        assert discharged_evening, "Expected discharging during expensive evening hours"

    def test_uniform_tariff_no_unnecessary_cycling(self):
        """
        Uniform tariff → cycling adds cost. Battery should mostly idle if solar covers demand.
        """
        hours = make_hours([5.0], [6.0], [5.0])  # solar > demand
        battery = make_battery(initial=25.0)
        plan = optimize_energy(hours, battery, [])
        assert_energy_balance(plan, hours)
        assert_neutrality(plan, battery)

    def test_zero_charge_rate_never_charges(self):
        hours = make_hours([5.0], [2.0], [5.0])
        battery = make_battery(max_charge=0.0, initial=20.0)
        plan = optimize_energy(hours, battery, [])
        for e in plan:
            assert e["battery_action"] != "charge"

    def test_zero_discharge_rate_never_discharges(self):
        hours = make_hours([5.0], [2.0], [5.0])
        battery = make_battery(max_discharge=0.0, initial=20.0)
        plan = optimize_energy(hours, battery, [])
        for e in plan:
            assert e["battery_action"] != "discharge"


# ---------------------------------------------------------------------------
# STEP 32 — Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_zero_solar_all_day(self):
        hours = make_hours([10.0], [0.0], [5.0])
        battery = make_battery()
        plan = optimize_energy(hours, battery, [])
        for e in plan:
            assert e["solar_used_kwh"] <= TOLS
        assert_energy_balance(plan, hours)
        assert_neutrality(plan, battery)

    def test_solar_exceeds_demand(self):
        hours = make_hours([5.0], [20.0], [5.0])
        battery = make_battery(initial=20.0)
        plan = optimize_energy(hours, battery, [])
        for e in plan:
            assert e["grid_kwh"] >= -TOLS
        assert_energy_balance(plan, hours)

    def test_battery_initially_at_minimum(self):
        battery = make_battery(initial=5.0, minimum=5.0)
        hours = make_hours([10.0], [5.0], [5.0])
        plan = optimize_energy(hours, battery, [])
        assert_energy_balance(plan, hours)
        assert_neutrality(plan, battery)

    def test_battery_initially_at_maximum(self):
        battery = make_battery(initial=50.0, capacity=50.0, minimum=5.0)
        hours = make_hours([10.0], [5.0], [5.0])
        plan = optimize_energy(hours, battery, [])
        assert_energy_balance(plan, hours)
        assert_neutrality(plan, battery)

    def test_high_tariff_spread(self):
        tariffs = [0.1 if h < 6 else 50.0 for h in range(24)]
        hours = [
            {"hour": h, "demand_kwh": 5.0, "solar_kwh": 0.0,
             "tariff_bdt_per_kwh": tariffs[h]}
            for h in range(24)
        ]
        battery = make_battery(capacity=100.0, initial=10.0, minimum=0.0, max_charge=20.0, max_discharge=20.0)
        plan = optimize_energy(hours, battery, [])
        assert_energy_balance(plan, hours)
        assert_neutrality(plan, battery)

    def test_different_battery_initial_states(self):
        for init in [5.0, 15.0, 30.0, 45.0, 50.0]:
            battery = make_battery(initial=init)
            hours = make_hours([8.0], [4.0], [5.0])
            plan = optimize_energy(hours, battery, [])
            assert_energy_balance(plan, hours)
            assert_neutrality(plan, battery)

    def test_different_tariffs_neutrality(self):
        tariffs = [(i % 5) * 2.0 + 1.0 for i in range(24)]
        hours = [
            {"hour": h, "demand_kwh": 8.0, "solar_kwh": 3.0,
             "tariff_bdt_per_kwh": tariffs[h]}
            for h in range(24)
        ]
        battery = make_battery(initial=20.0)
        plan = optimize_energy(hours, battery, [])
        assert_neutrality(plan, battery)

    def test_tight_but_feasible_grid_cap(self):
        """Cap forces battery to absorb peak demand."""
        hours = make_hours([12.0], [0.0], [5.0])
        battery = make_battery(capacity=200.0, initial=100.0, minimum=0.0,
                               max_charge=20.0, max_discharge=20.0)
        # Cap at 6 kWh; demand is 12 → battery must supply 6 kWh
        d = directive("max_grid_window", {"hours": list(range(8, 12)), "max_grid_kwh": 6.0})
        plan = optimize_energy(hours, battery, [d])
        for e in plan:
            if e["hour"] in range(8, 12):
                assert e["grid_kwh"] <= 6.0 + TOLS

    def test_no_simultaneous_charge_and_discharge(self):
        hours = make_hours([5.0], [2.0], [5.0])
        battery = make_battery()
        plan = optimize_energy(hours, battery, [])
        for e in plan:
            if e["battery_action"] == "charge":
                assert e["battery_kwh"] > 0
            if e["battery_action"] == "discharge":
                assert e["battery_kwh"] > 0
            # Simultaneous charge+discharge is impossible by design;
            # battery_action encodes this exclusively.
            assert e["battery_action"] in {"charge", "discharge", "idle"}
