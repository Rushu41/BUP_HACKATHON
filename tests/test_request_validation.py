"""Tests for request payload validation rules in GridWise."""

import math
import pytest
from pydantic import ValidationError

from app.schemas import BatteryInput, HourInput, OptimizeEnergyRequest


def make_valid_hours(count: int = 24) -> list[dict]:
    """Generates a list of valid hour dictionary entries."""
    return [
        {
            "hour": h,
            "demand_kwh": 50.0 + h * 2.0,
            "solar_kwh": 30.0 if 8 <= h <= 17 else 0.0,
            "tariff_bdt_per_kwh": 6.5 if h < 17 else 10.5,
        }
        for h in range(count)
    ]


def make_valid_battery() -> dict:
    """Generates a valid battery parameter dictionary."""
    return {
        "capacity_kwh": 200.0,
        "initial_energy_kwh": 80.0,
        "minimum_energy_kwh": 40.0,
        "max_charge_kwh_per_hour": 50.0,
        "max_discharge_kwh_per_hour": 50.0,
    }


def make_valid_request(
    scenario_id: str = "SCENARIO-TEST-01",
    operator_notes: list[str] | None = None,
    hours: list[dict] | None = None,
    battery: dict | None = None,
) -> dict:
    """Helper to construct a complete valid request dict."""
    return {
        "scenario_id": scenario_id,
        "operator_notes": operator_notes if operator_notes is not None else ["Reduce solar by 20% between 1 PM and 3 PM."],
        "hours": hours if hours is not None else make_valid_hours(),
        "battery": battery if battery is not None else make_valid_battery(),
    }


def test_valid_request_accepted():
    """Verify that a standard valid request is accepted."""
    data = make_valid_request()
    req = OptimizeEnergyRequest(**data)
    assert req.scenario_id == "SCENARIO-TEST-01"
    assert len(req.operator_notes) == 1
    assert len(req.hours) == 24
    assert req.battery.capacity_kwh == 200.0


def test_scenario_id_empty_or_whitespace_rejected():
    """Verify that empty or whitespace-only scenario_id is rejected."""
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(scenario_id=""))

    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(scenario_id="   "))


def test_scenario_id_trimmed():
    """Verify that scenario_id is whitespace-trimmed."""
    data = make_valid_request(scenario_id="  SCENARIO-99  ")
    req = OptimizeEnergyRequest(**data)
    assert req.scenario_id == "SCENARIO-99"


def test_1_note_accepted():
    """Verify that 1 operator note is accepted."""
    data = make_valid_request(operator_notes=["Note 1"])
    req = OptimizeEnergyRequest(**data)
    assert len(req.operator_notes) == 1


def test_2_notes_accepted():
    """Verify that 2 operator notes are accepted."""
    data = make_valid_request(operator_notes=["Note 1", "Note 2"])
    req = OptimizeEnergyRequest(**data)
    assert len(req.operator_notes) == 2


def test_3_notes_accepted():
    """Verify that 3 operator notes are accepted."""
    data = make_valid_request(operator_notes=["Note 1", "Note 2", "Note 3"])
    req = OptimizeEnergyRequest(**data)
    assert len(req.operator_notes) == 3


def test_0_notes_rejected():
    """Verify that 0 operator notes is rejected."""
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(operator_notes=[]))


def test_4_notes_rejected():
    """Verify that 4 operator notes is rejected."""
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(operator_notes=["N1", "N2", "N3", "N4"]))


@pytest.mark.parametrize(
    "blank_note",
    ["", "   ", "\t\n"],
)
def test_blank_note_rejected(blank_note):
    """Verify that blank or whitespace-only notes are rejected."""
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(operator_notes=[blank_note]))

    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(operator_notes=["Valid note", blank_note]))


def test_23_hours_rejected():
    """Verify that 23 hours entries is rejected."""
    hours = make_valid_hours(23)
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(hours=hours))


def test_25_hours_rejected():
    """Verify that 25 hours entries is rejected."""
    hours = make_valid_hours(24)
    hours.append(
        {
            "hour": 23,
            "demand_kwh": 50.0,
            "solar_kwh": 0.0,
            "tariff_bdt_per_kwh": 10.0,
        }
    )
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(hours=hours))


def test_duplicate_hour_rejected():
    """Verify that duplicate hours in hours list are rejected."""
    hours = make_valid_hours(24)
    # Replace hour 23 with duplicate hour 0
    hours[23]["hour"] = 0
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(hours=hours))


def test_missing_hour_rejected():
    """Verify that missing an intermediate hour is rejected."""
    hours = make_valid_hours(24)
    # Change hour 12 to 24 (so 12 is missing)
    hours[12]["hour"] = 24
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(hours=hours))


def test_unsorted_hours_normalized():
    """Verify that unsorted hours (e.g. reversed 23..0) are accepted and normalized to 0..23."""
    hours = make_valid_hours(24)
    reversed_hours = list(reversed(hours))
    req = OptimizeEnergyRequest(**make_valid_request(hours=reversed_hours))
    assert len(req.hours) == 24
    for idx, h_entry in enumerate(req.hours):
        assert h_entry.hour == idx


def test_negative_demand_rejected():
    """Verify that negative demand_kwh is rejected."""
    hours = make_valid_hours(24)
    hours[5]["demand_kwh"] = -10.0
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(hours=hours))


def test_negative_solar_rejected():
    """Verify that negative solar_kwh is rejected."""
    hours = make_valid_hours(24)
    hours[12]["solar_kwh"] = -5.0
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(hours=hours))


def test_negative_tariff_rejected():
    """Verify that negative tariff_bdt_per_kwh is rejected."""
    hours = make_valid_hours(24)
    hours[3]["tariff_bdt_per_kwh"] = -1.0
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(hours=hours))


def test_invalid_battery_capacity_rejected():
    """Verify that negative battery capacity is rejected."""
    bat = make_valid_battery()
    bat["capacity_kwh"] = -50.0
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(battery=bat))


def test_battery_initial_greater_than_capacity_rejected():
    """Verify that initial_energy_kwh > capacity_kwh is rejected."""
    bat = make_valid_battery()
    bat["capacity_kwh"] = 100.0
    bat["initial_energy_kwh"] = 150.0
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(battery=bat))


def test_battery_minimum_greater_than_capacity_rejected():
    """Verify that minimum_energy_kwh > capacity_kwh is rejected."""
    bat = make_valid_battery()
    bat["capacity_kwh"] = 100.0
    bat["minimum_energy_kwh"] = 120.0
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(battery=bat))


def test_battery_initial_less_than_minimum_rejected():
    """Verify that initial_energy_kwh < minimum_energy_kwh is rejected."""
    bat = make_valid_battery()
    bat["initial_energy_kwh"] = 30.0
    bat["minimum_energy_kwh"] = 50.0
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(battery=bat))


def test_negative_rate_limits_rejected():
    """Verify that negative max charge/discharge rates are rejected."""
    bat = make_valid_battery()
    bat["max_charge_kwh_per_hour"] = -10.0
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(battery=bat))

    bat = make_valid_battery()
    bat["max_discharge_kwh_per_hour"] = -10.0
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(battery=bat))


def test_nan_infinity_rejected():
    """Verify that NaN and Infinity in hour values are rejected."""
    hours = make_valid_hours(24)
    hours[0]["demand_kwh"] = float("nan")
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(hours=hours))

    hours = make_valid_hours(24)
    hours[0]["demand_kwh"] = float("inf")
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(**make_valid_request(hours=hours))
