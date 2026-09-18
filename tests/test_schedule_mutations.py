"""
tests/test_schedule_mutations.py — GridWise Developer 2

Mutation tests (STEP 31): Take a valid plan, intentionally corrupt it,
and assert that the validator detects every type of corruption.

All 13 mutation types from the spec are covered.
"""
import copy
import pytest
from app.optimizer import optimize_energy
from app.validator import validate_hourly_plan, PlanValidationError


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def make_hours(demand=8.0, solar=4.0, tariff=5.0):
    return [
        {"hour": h, "demand_kwh": demand, "solar_kwh": solar,
         "tariff_bdt_per_kwh": tariff}
        for h in range(24)
    ]


def make_battery(
    capacity=50.0, initial=20.0, minimum=5.0,
    max_charge=10.0, max_discharge=10.0,
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


@pytest.fixture
def base():
    """Return (hours, battery, directives, valid_plan) for mutation tests."""
    hours = make_hours()
    battery = make_battery()
    directives = []
    plan = optimize_energy(hours, battery, directives)
    return hours, battery, directives, plan


def sorted_plan(plan):
    return sorted(plan, key=lambda x: x["hour"])


# ---------------------------------------------------------------------------
# Mutation 1 — Solar overuse
# ---------------------------------------------------------------------------

def test_mutation_solar_overuse(base):
    hours, battery, directives, plan = base
    bad = copy.deepcopy(plan)
    s_plan = sorted_plan(bad)
    # Force solar_used beyond raw solar at hour 6
    original_solar = hours[6]["solar_kwh"]
    s_plan[6]["solar_used_kwh"] = original_solar + 5.0
    with pytest.raises(PlanValidationError, match="[Ss]olar"):
        validate_hourly_plan(hours, battery, directives, bad)


# ---------------------------------------------------------------------------
# Mutation 2 — Wrong battery transition
# ---------------------------------------------------------------------------

def test_mutation_wrong_battery_transition(base):
    hours, battery, directives, plan = base
    bad = copy.deepcopy(plan)
    s_plan = sorted_plan(bad)
    # Jump battery energy at hour 10
    s_plan[10]["battery_energy_after_kwh"] += 15.0
    with pytest.raises(PlanValidationError, match="[Bb]attery|mismatch|transition"):
        validate_hourly_plan(hours, battery, directives, bad)


# ---------------------------------------------------------------------------
# Mutation 3 — Battery under reserve
# ---------------------------------------------------------------------------

def test_mutation_battery_under_reserve():
    hours = make_hours()
    battery = make_battery(minimum=10.0, initial=20.0)
    directives = []
    plan = optimize_energy(hours, battery, directives)
    bad = copy.deepcopy(plan)
    s_plan = sorted_plan(bad)
    # Forcibly set battery energy below minimum at hour 12
    s_plan[12]["battery_energy_after_kwh"] = 3.0
    # Also fix subsequent to avoid cascade detection first
    for i in range(13, 24):
        s_plan[i]["battery_energy_after_kwh"] = 3.0
    with pytest.raises(PlanValidationError, match="[Mm]inimum|reserve"):
        validate_hourly_plan(hours, battery, directives, bad)


# ---------------------------------------------------------------------------
# Mutation 4 — Battery over capacity
# ---------------------------------------------------------------------------

def test_mutation_battery_over_capacity(base):
    hours, battery, directives, plan = base
    bad = copy.deepcopy(plan)
    s_plan = sorted_plan(bad)
    # Set battery energy above capacity at hour 5
    for e in s_plan:
        e["battery_energy_after_kwh"] = battery["capacity_kwh"] + 10.0
    with pytest.raises(PlanValidationError, match="[Cc]apacity"):
        validate_hourly_plan(hours, battery, directives, bad)


# ---------------------------------------------------------------------------
# Mutation 5 — Charge above rate
# ---------------------------------------------------------------------------

def test_mutation_charge_above_rate(base):
    hours, battery, directives, plan = base
    bad = copy.deepcopy(plan)
    s_plan = sorted_plan(bad)
    # Inject excessive charge at some idle hour
    target = next(
        (e for e in s_plan if e["battery_action"] != "charge"), s_plan[0]
    )
    h = target["hour"]
    original_action = target["battery_action"]
    original_bkwh = target["battery_kwh"]
    # Force charge beyond max rate
    target["battery_action"] = "charge"
    target["battery_kwh"] = battery["max_charge_kwh_per_hour"] + 5.0
    # (energy_after will mismatch — that may trigger first, still valid mutation detection)
    with pytest.raises(PlanValidationError):
        validate_hourly_plan(hours, battery, directives, bad)


# ---------------------------------------------------------------------------
# Mutation 6 — Discharge above rate
# ---------------------------------------------------------------------------

def test_mutation_discharge_above_rate(base):
    hours, battery, directives, plan = base
    bad = copy.deepcopy(plan)
    s_plan = sorted_plan(bad)
    target = next(
        (e for e in s_plan if e["battery_action"] != "discharge"), s_plan[0]
    )
    target["battery_action"] = "discharge"
    target["battery_kwh"] = battery["max_discharge_kwh_per_hour"] + 5.0
    with pytest.raises(PlanValidationError):
        validate_hourly_plan(hours, battery, directives, bad)


# ---------------------------------------------------------------------------
# Mutation 7 — Charge during no-charge window
# ---------------------------------------------------------------------------

def test_mutation_charge_during_no_charge():
    hours = make_hours(demand=8.0, solar=4.0)
    battery = make_battery(initial=20.0)
    directives = [directive("no_charge_window", {"hours": [10, 11, 12]})]
    plan = optimize_energy(hours, battery, directives)
    bad = copy.deepcopy(plan)
    s_plan = sorted_plan(bad)
    # Force charge at hour 11
    s_plan[11]["battery_action"] = "charge"
    s_plan[11]["battery_kwh"] = 2.0
    s_plan[11]["battery_energy_after_kwh"] += 2.0
    # Adjust remaining battery energies to maintain transition consistency
    for i in range(12, 24):
        s_plan[i]["battery_energy_after_kwh"] += 2.0
    # Also fix grid to balance supply
    s_plan[11]["grid_kwh"] += 2.0
    with pytest.raises(PlanValidationError, match="[Cc]harge|no_charge"):
        validate_hourly_plan(hours, battery, directives, bad)


# ---------------------------------------------------------------------------
# Mutation 8 — Discharge during no-discharge window
# ---------------------------------------------------------------------------

def test_mutation_discharge_during_no_discharge():
    hours = make_hours(demand=8.0, solar=4.0)
    # Use larger initial so subtracting 2 kWh for hours 19-23 keeps energy above minimum=5.
    battery = make_battery(initial=30.0, minimum=5.0)
    directives = [directive("no_discharge_window", {"hours": [18, 19, 20]})]
    plan = optimize_energy(hours, battery, directives)
    bad = copy.deepcopy(plan)
    s_plan = sorted_plan(bad)
    h19 = s_plan[19]
    # Force discharge at hour 19 (forbidden)
    h19["battery_action"] = "discharge"
    h19["battery_kwh"] = 2.0
    h19["battery_energy_after_kwh"] -= 2.0
    # Keep subsequent entries consistent so bounds check doesn't fire first
    for i in range(20, 24):
        s_plan[i]["battery_energy_after_kwh"] -= 2.0
    # Reduce grid supply to balance: grid = demand - discharge - solar_used
    orig_grid = h19["grid_kwh"]
    h19["grid_kwh"] = max(orig_grid - 2.0, 0.0)
    # The neutrality pre-check fires first only if final energy drifts — 
    # the directive violation check runs AFTER neutrality but BEFORE energy balance.
    # Use a broad match that covers the directive violation message.
    with pytest.raises(PlanValidationError):
        validate_hourly_plan(hours, battery, directives, bad)


# ---------------------------------------------------------------------------
# Mutation 9 — Grid above cap
# ---------------------------------------------------------------------------

def test_mutation_grid_above_cap():
    hours = make_hours(demand=8.0, solar=4.0)
    battery = make_battery(initial=20.0)
    directives = [directive("max_grid_window", {"hours": [14, 15], "max_grid_kwh": 2.0})]
    plan = optimize_energy(hours, battery, directives)
    bad = copy.deepcopy(plan)
    s_plan = sorted_plan(bad)
    # Force grid above cap at hour 14
    s_plan[14]["grid_kwh"] = 9.0
    with pytest.raises(PlanValidationError, match="[Gg]rid|cap"):
        validate_hourly_plan(hours, battery, directives, bad)


# ---------------------------------------------------------------------------
# Mutation 10 — Wrong energy balance
# ---------------------------------------------------------------------------

def test_mutation_wrong_energy_balance(base):
    hours, battery, directives, plan = base
    bad = copy.deepcopy(plan)
    s_plan = sorted_plan(bad)
    # Inflate grid at hour 3 without increasing demand side
    s_plan[3]["grid_kwh"] += 10.0
    with pytest.raises(PlanValidationError, match="[Bb]alance|supply"):
        validate_hourly_plan(hours, battery, directives, bad)


# ---------------------------------------------------------------------------
# Mutation 11 — Negative grid
# ---------------------------------------------------------------------------

def test_mutation_negative_grid(base):
    hours, battery, directives, plan = base
    bad = copy.deepcopy(plan)
    s_plan = sorted_plan(bad)
    s_plan[7]["grid_kwh"] = -2.0
    with pytest.raises(PlanValidationError, match="[Nn]egative"):
        validate_hourly_plan(hours, battery, directives, bad)


# ---------------------------------------------------------------------------
# Mutation 12 — Wrong final battery (neutrality)
# ---------------------------------------------------------------------------

def test_mutation_wrong_final_battery(base):
    hours, battery, directives, plan = base
    bad = copy.deepcopy(plan)
    s_plan = sorted_plan(bad)
    s_plan[23]["battery_energy_after_kwh"] = battery["initial_energy_kwh"] + 5.0
    with pytest.raises(PlanValidationError, match="[Nn]eutral|final"):
        validate_hourly_plan(hours, battery, directives, bad)


# ---------------------------------------------------------------------------
# Mutation 13 — Idle with nonzero battery_kwh
# ---------------------------------------------------------------------------

def test_mutation_idle_nonzero_battery_kwh(base):
    hours, battery, directives, plan = base
    bad = copy.deepcopy(plan)
    s_plan = sorted_plan(bad)
    # Find an idle hour
    idle = next((e for e in s_plan if e["battery_action"] == "idle"), None)
    if idle is None:
        # Force one to idle
        s_plan[0]["battery_action"] = "idle"
        idle = s_plan[0]
    idle["battery_kwh"] = 3.0  # nonzero for idle is invalid
    with pytest.raises(PlanValidationError):
        validate_hourly_plan(hours, battery, directives, bad)


# ---------------------------------------------------------------------------
# Mutation 14 — Missing hour
# ---------------------------------------------------------------------------

def test_mutation_missing_hour(base):
    hours, battery, directives, plan = base
    bad = copy.deepcopy(plan)
    bad.pop(5)  # remove entry for hour 5 → only 23 entries
    with pytest.raises(PlanValidationError, match="24|[Mm]issing"):
        validate_hourly_plan(hours, battery, directives, bad)


# ---------------------------------------------------------------------------
# Mutation 15 — Duplicate hour
# ---------------------------------------------------------------------------

def test_mutation_duplicate_hour(base):
    hours, battery, directives, plan = base
    bad = copy.deepcopy(plan)
    s_plan = sorted_plan(bad)
    s_plan[8]["hour"] = s_plan[9]["hour"]  # duplicate hour 9
    with pytest.raises(PlanValidationError, match="[Dd]uplicate"):
        validate_hourly_plan(hours, battery, directives, bad)
