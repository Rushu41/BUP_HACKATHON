"""Unit tests for GridWise Pydantic schemas, enums, and models."""

import math
import pytest
from pydantic import ValidationError

from app.schemas import (
    BatteryAction,
    BatteryInput,
    DirectiveInterpretation,
    DirectiveType,
    HourInput,
    HourlyPlanEntry,
    MaxGridWindowAdjustment,
    MinimumBatteryReserveAdjustment,
    OptimizeEnergyResponse,
    SolarReductionAdjustment,
    WindowAdjustment,
)


def test_valid_hour_input():
    """Test standard valid HourInput model creation and dict access."""
    h = HourInput(
        hour=10,
        demand_kwh=120.5,
        solar_kwh=80.0,
        tariff_bdt_per_kwh=8.75,
    )
    assert h.hour == 10
    assert h.demand_kwh == 120.5
    assert h.solar_kwh == 80.0
    assert h.tariff_bdt_per_kwh == 8.75
    # Test dict subscript access
    assert h["demand_kwh"] == 120.5
    assert h.get("solar_kwh") == 80.0


@pytest.mark.parametrize(
    "demand,solar,tariff,hour",
    [
        (-1.0, 10.0, 5.0, 0),
        (10.0, -0.5, 5.0, 0),
        (10.0, 10.0, -0.1, 0),
        (10.0, 10.0, 5.0, -1),
        (10.0, 10.0, 5.0, 24),
        (float("nan"), 10.0, 5.0, 0),
        (float("inf"), 10.0, 5.0, 0),
        (10.0, float("-inf"), 5.0, 0),
    ],
)
def test_invalid_hour_input_values(demand, solar, tariff, hour):
    """Test that negative, out-of-bounds, NaN, and Inf values in HourInput are rejected."""
    with pytest.raises(ValidationError):
        HourInput(
            hour=hour,
            demand_kwh=demand,
            solar_kwh=solar,
            tariff_bdt_per_kwh=tariff,
        )


def test_valid_battery_input():
    """Test valid BatteryInput creation and dict subscript access."""
    b = BatteryInput(
        capacity_kwh=200.0,
        initial_energy_kwh=100.0,
        minimum_energy_kwh=40.0,
        max_charge_kwh_per_hour=50.0,
        max_discharge_kwh_per_hour=50.0,
    )
    assert b.capacity_kwh == 200.0
    assert b.initial_energy_kwh == 100.0
    assert b.minimum_energy_kwh == 40.0
    assert b["capacity_kwh"] == 200.0
    assert b.get("initial_energy_kwh") == 100.0


def test_battery_initial_exceeds_capacity():
    """Test battery initial energy greater than capacity is rejected."""
    with pytest.raises(ValidationError):
        BatteryInput(
            capacity_kwh=100.0,
            initial_energy_kwh=120.0,
            minimum_energy_kwh=20.0,
            max_charge_kwh_per_hour=25.0,
            max_discharge_kwh_per_hour=25.0,
        )


def test_battery_minimum_exceeds_capacity():
    """Test battery minimum reserve greater than capacity is rejected."""
    with pytest.raises(ValidationError):
        BatteryInput(
            capacity_kwh=100.0,
            initial_energy_kwh=50.0,
            minimum_energy_kwh=110.0,
            max_charge_kwh_per_hour=25.0,
            max_discharge_kwh_per_hour=25.0,
        )


def test_battery_initial_below_minimum():
    """Test battery initial energy below minimum reserve is rejected."""
    with pytest.raises(ValidationError):
        BatteryInput(
            capacity_kwh=100.0,
            initial_energy_kwh=15.0,
            minimum_energy_kwh=20.0,
            max_charge_kwh_per_hour=25.0,
            max_discharge_kwh_per_hour=25.0,
        )


@pytest.mark.parametrize(
    "cap,init,min_e,chg,dis",
    [
        (-10.0, 0.0, 0.0, 10.0, 10.0),
        (100.0, -5.0, 0.0, 10.0, 10.0),
        (100.0, 50.0, -10.0, 10.0, 10.0),
        (100.0, 50.0, 20.0, -5.0, 10.0),
        (100.0, 50.0, 20.0, 10.0, -5.0),
        (float("nan"), 50.0, 20.0, 10.0, 10.0),
        (100.0, float("inf"), 20.0, 10.0, 10.0),
    ],
)
def test_battery_negative_and_nan_values(cap, init, min_e, chg, dis):
    """Test rejection of negative, NaN, and Inf battery values."""
    with pytest.raises(ValidationError):
        BatteryInput(
            capacity_kwh=cap,
            initial_energy_kwh=init,
            minimum_energy_kwh=min_e,
            max_charge_kwh_per_hour=chg,
            max_discharge_kwh_per_hour=dis,
        )


def test_directive_interpretation_no_op():
    """Test valid canonical no_op directive."""
    d = DirectiveInterpretation(
        note_index=0,
        applies=False,
        directive_type=DirectiveType.NO_OP,
        structured_adjustment=None,
        explanation="General notice not affecting 24-hour schedule.",
    )
    assert d.applies is False
    assert d.directive_type == DirectiveType.NO_OP
    assert d.structured_adjustment is None


def test_directive_interpretation_no_op_invalid():
    """Test no_op with applies=True or non-null adjustment is rejected."""
    with pytest.raises(ValidationError):
        DirectiveInterpretation(
            note_index=0,
            applies=True,
            directive_type=DirectiveType.NO_OP,
            structured_adjustment=None,
            explanation="Invalid no_op",
        )

    with pytest.raises(ValidationError):
        DirectiveInterpretation(
            note_index=0,
            applies=False,
            directive_type=DirectiveType.NO_OP,
            structured_adjustment={"hours": [1, 2]},
            explanation="Invalid no_op with adjustment",
        )


def test_directive_interpretation_solar_reduction():
    """Test solar reduction directive with fraction remaining."""
    d = DirectiveInterpretation(
        note_index=1,
        applies=True,
        directive_type=DirectiveType.SOLAR_REDUCTION,
        structured_adjustment={"hours": [13, 14], "factor": 0.20},
        explanation="Solar drops by 80%, 20% remaining.",
    )
    assert d.applies is True
    assert d.directive_type == DirectiveType.SOLAR_REDUCTION


def test_directive_interpretation_minimum_reserve():
    """Test minimum battery reserve directive."""
    d = DirectiveInterpretation(
        note_index=0,
        applies=True,
        directive_type=DirectiveType.MINIMUM_BATTERY_RESERVE,
        structured_adjustment={"hours": [18, 19, 20], "minimum_energy_kwh": 80.0},
        explanation="Maintain minimum 80 kWh reserve during evening peak.",
    )
    assert d.applies is True
    assert d.directive_type == DirectiveType.MINIMUM_BATTERY_RESERVE


def test_directive_interpretation_windows():
    """Test no_charge_window, no_discharge_window, and max_grid_window directives."""
    d_nc = DirectiveInterpretation(
        note_index=0,
        applies=True,
        directive_type=DirectiveType.NO_CHARGE_WINDOW,
        structured_adjustment={"hours": [2, 3, 4]},
        explanation="No charging allowed during maintenance.",
    )
    assert d_nc.directive_type == DirectiveType.NO_CHARGE_WINDOW

    d_nd = DirectiveInterpretation(
        note_index=1,
        applies=True,
        directive_type=DirectiveType.NO_DISCHARGE_WINDOW,
        structured_adjustment={"hours": [12, 13]},
        explanation="No discharging allowed.",
    )
    assert d_nd.directive_type == DirectiveType.NO_DISCHARGE_WINDOW

    d_mg = DirectiveInterpretation(
        note_index=2,
        applies=True,
        directive_type=DirectiveType.MAX_GRID_WINDOW,
        structured_adjustment={"hours": [18, 19], "max_grid_kwh": 150.0},
        explanation="Grid import capped at 150 kWh.",
    )
    assert d_mg.directive_type == DirectiveType.MAX_GRID_WINDOW


def test_directive_interpretation_active_without_adjustment():
    """Test that an active directive missing adjustment is rejected."""
    with pytest.raises(ValidationError):
        DirectiveInterpretation(
            note_index=0,
            applies=True,
            directive_type=DirectiveType.SOLAR_REDUCTION,
            structured_adjustment=None,
            explanation="Missing adjustment",
        )


def test_directive_invalid_hours():
    """Test duplicate, out of range, or empty hours in directive adjustment."""
    with pytest.raises(ValidationError):
        # Empty hours
        SolarReductionAdjustment(hours=[], factor=0.5)

    with pytest.raises(ValidationError):
        # Out of range hour 24
        WindowAdjustment(hours=[23, 24])

    with pytest.raises(ValidationError):
        # Negative hour -1
        WindowAdjustment(hours=[-1, 2])

    with pytest.raises(ValidationError):
        # Duplicate hour
        WindowAdjustment(hours=[5, 5])


def test_valid_hourly_plan_entry():
    """Test HourlyPlanEntry validation."""
    entry = HourlyPlanEntry(
        hour=5,
        grid_kwh=10.0,
        solar_used_kwh=0.0,
        battery_action=BatteryAction.CHARGE,
        battery_kwh=10.0,
        battery_energy_after_kwh=60.0,
    )
    assert entry.hour == 5
    assert entry.battery_action == BatteryAction.CHARGE
    assert entry["battery_kwh"] == 10.0
