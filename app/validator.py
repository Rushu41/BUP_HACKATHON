"""
validator.py — GridWise Developer 2

Independent schedule validator.

Public interface (matches team contract):

    def validate_hourly_plan(
        hours: list[dict],
        battery: dict,
        directives: list[dict],
        hourly_plan: list[dict],
    ) -> dict

Treats hourly_plan as if it came from a completely different team.
Replays the schedule from scratch and verifies every constraint.

Returns:
    {
        "total_grid_kwh": float,
        "total_cost_bdt": float,
        "peak_grid_kwh": float,
    }

Raises:
    PlanValidationError  — on any constraint violation.
"""

from __future__ import annotations

import math

from app.math_utils import (
    NUMERIC_TOLERANCE,
    within_tolerance,
    active_minimum_reserve,
    effective_solar_array,
)
from app.exceptions import PlanValidationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_ACTIONS = {"charge", "discharge", "idle"}


def _check_finite(val: float, label: str) -> None:
    if not math.isfinite(val):
        raise PlanValidationError(f"{label} is not finite: {val!r}")


def _check_nonneg(val: float, label: str) -> None:
    if val < -NUMERIC_TOLERANCE:
        raise PlanValidationError(f"{label} is negative: {val!r}")


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------


def validate_hourly_plan(
    hours: list[dict],
    battery: dict,
    directives: list[dict],
    hourly_plan: list[dict],
) -> dict:
    """
    Independently verify a 24-hour energy dispatch schedule.

    Parameters
    ----------
    hours:
        24-element list of hour dicts (hour, demand_kwh, solar_kwh,
        tariff_bdt_per_kwh).
    battery:
        Battery parameter dict.
    directives:
        Canonical validated directives (applies=True entries are enforced).
    hourly_plan:
        Candidate schedule to validate.

    Returns
    -------
    dict
        {total_grid_kwh, total_cost_bdt, peak_grid_kwh}

    Raises
    ------
    PlanValidationError
        On any structural or constraint violation.
    """
    TOL = NUMERIC_TOLERANCE

    # ------------------------------------------------------------------ #
    # STEP 20 — Structural checks                                          #
    # ------------------------------------------------------------------ #
    if len(hourly_plan) != 24:
        raise PlanValidationError(
            f"Expected 24 hourly entries, got {len(hourly_plan)}."
        )

    seen_hours: set[int] = set()
    for entry in hourly_plan:
        h = entry.get("hour")
        if not isinstance(h, int) or h < 0 or h > 23:
            raise PlanValidationError(
                f"Invalid hour value: {h!r}. Must be int 0..23."
            )
        if h in seen_hours:
            raise PlanValidationError(f"Duplicate hour {h} in plan.")
        seen_hours.add(h)

    if seen_hours != set(range(24)):
        missing = set(range(24)) - seen_hours
        raise PlanValidationError(f"Missing hours in plan: {sorted(missing)}")

    # Sort plan and hours by hour for aligned iteration.
    plan = sorted(hourly_plan, key=lambda x: x["hour"])
    sorted_hours = sorted(hours, key=lambda x: x["hour"])
    tariff = {h["hour"]: h["tariff_bdt_per_kwh"] for h in sorted_hours}
    demand = {h["hour"]: h["demand_kwh"] for h in sorted_hours}

    for entry in plan:
        h = entry["hour"]
        grid_v = entry.get("grid_kwh", 0.0)
        solar_v = entry.get("solar_used_kwh", 0.0)
        batt_kwh_v = entry.get("battery_kwh", 0.0)
        ea_v = entry.get("battery_energy_after_kwh")
        action = entry.get("battery_action")

        _check_finite(grid_v, f"hour {h} grid_kwh")
        _check_finite(solar_v, f"hour {h} solar_used_kwh")
        _check_finite(batt_kwh_v, f"hour {h} battery_kwh")
        if ea_v is None or not math.isfinite(ea_v):
            raise PlanValidationError(
                f"hour {h} battery_energy_after_kwh is not finite: {ea_v!r}"
            )

        _check_nonneg(grid_v, f"hour {h} grid_kwh")
        _check_nonneg(solar_v, f"hour {h} solar_used_kwh")
        _check_nonneg(batt_kwh_v, f"hour {h} battery_kwh")

        if action not in _VALID_ACTIONS:
            raise PlanValidationError(
                f"hour {h} battery_action={action!r} is not valid. "
                f"Must be one of {_VALID_ACTIONS}."
            )

        if action == "idle" and batt_kwh_v > TOL:
            raise PlanValidationError(
                f"hour {h} battery_action=idle but battery_kwh={batt_kwh_v} > tolerance."
            )

    # ------------------------------------------------------------------ #
    # STEP 21 — Reconstruct charge/discharge arrays                        #
    # ------------------------------------------------------------------ #
    charge_arr = []
    discharge_arr = []
    for entry in plan:
        action = entry["battery_action"]
        bkwh = entry["battery_kwh"]
        if action == "charge":
            charge_arr.append(bkwh)
            discharge_arr.append(0.0)
        elif action == "discharge":
            charge_arr.append(0.0)
            discharge_arr.append(bkwh)
        else:
            charge_arr.append(0.0)
            discharge_arr.append(0.0)

    # ------------------------------------------------------------------ #
    # STEP 23 — Battery bounds (checked BEFORE transition replay so that  #
    # over-capacity / under-reserve mutations are caught with correct msg) #
    # ------------------------------------------------------------------ #
    capacity = battery["capacity_kwh"]

    for i, entry in enumerate(plan):
        h = entry["hour"]
        ea = entry["battery_energy_after_kwh"]
        if ea > capacity + TOL:
            raise PlanValidationError(
                f"hour {h} battery_energy_after_kwh={ea} exceeds capacity {capacity}."
            )
        active_min = active_minimum_reserve(h, battery, directives)
        if ea < active_min - TOL:
            raise PlanValidationError(
                f"hour {h} battery_energy_after_kwh={ea} is below "
                f"active minimum reserve {active_min}."
            )

    # ------------------------------------------------------------------ #
    # STEP 24 — Rate limits (before replay so rate violations fire first)  #
    # ------------------------------------------------------------------ #
    max_c = battery["max_charge_kwh_per_hour"]
    max_d = battery["max_discharge_kwh_per_hour"]

    for i, entry in enumerate(plan):
        h = entry["hour"]
        if charge_arr[i] > max_c + TOL:
            raise PlanValidationError(
                f"hour {h} charge {charge_arr[i]} exceeds max_charge_rate {max_c}."
            )
        if discharge_arr[i] > max_d + TOL:
            raise PlanValidationError(
                f"hour {h} discharge {discharge_arr[i]} exceeds max_discharge_rate {max_d}."
            )

    # ------------------------------------------------------------------ #
    # STEP 25 — Directive constraint checks (before replay so directive   #
    # violations fire before neutrality / transition errors)              #
    # ------------------------------------------------------------------ #
    eff_solar = effective_solar_array(sorted_hours, directives)

    # Build directive constraint sets
    no_charge_h: set[int] = set()
    no_discharge_h: set[int] = set()
    max_grid_h: dict[int, float] = {}

    for d in directives:
        if not d.get("applies", False):
            continue
        dtype = d.get("directive_type")
        sa = d.get("structured_adjustment") or {}

        if dtype == "no_charge_window":
            for hh in sa.get("hours", []):
                no_charge_h.add(hh)
        elif dtype == "no_discharge_window":
            for hh in sa.get("hours", []):
                no_discharge_h.add(hh)
        elif dtype == "max_grid_window":
            cap = sa.get("max_grid_kwh")
            if cap is not None:
                for hh in sa.get("hours", []):
                    if hh not in max_grid_h:
                        max_grid_h[hh] = cap
                    else:
                        max_grid_h[hh] = min(max_grid_h[hh], cap)

    for i, entry in enumerate(plan):
        h = entry["hour"]
        solar_v = entry["solar_used_kwh"]
        grid_v = entry["grid_kwh"]
        action = entry["battery_action"]

        # solar_reduction
        if solar_v > eff_solar[h] + TOL:
            raise PlanValidationError(
                f"hour {h} solar_used_kwh={solar_v} exceeds "
                f"effective solar {eff_solar[h]:.6f}."
            )

        # no_charge_window
        if h in no_charge_h and action == "charge":
            raise PlanValidationError(
                f"hour {h} charging is forbidden by no_charge_window directive."
            )

        # no_discharge_window
        if h in no_discharge_h and action == "discharge":
            raise PlanValidationError(
                f"hour {h} discharging is forbidden by no_discharge_window directive."
            )

        # max_grid_window
        if h in max_grid_h and grid_v > max_grid_h[h] + TOL:
            raise PlanValidationError(
                f"hour {h} grid_kwh={grid_v} exceeds max_grid_kwh cap {max_grid_h[h]}."
            )

    # ------------------------------------------------------------------ #
    # STEP 27 (pre-check) — End-of-day neutrality                         #
    # After directive/rate checks so those violations fire first.          #
    # ------------------------------------------------------------------ #
    initial = battery["initial_energy_kwh"]
    final_reported = plan[23]["battery_energy_after_kwh"]
    if not within_tolerance(final_reported, initial, TOL):
        raise PlanValidationError(
            f"End-of-day neutral constraint violated: "
            f"final energy={final_reported:.6f} != initial={initial} (neutrality required)."
        )

    # ------------------------------------------------------------------ #
    # STEP 22 — Replay battery state                                       #
    # ------------------------------------------------------------------ #
    expected_energy = initial

    for i, entry in enumerate(plan):
        h = entry["hour"]
        expected_energy += charge_arr[i] - discharge_arr[i]
        reported = entry["battery_energy_after_kwh"]
        if not within_tolerance(reported, expected_energy, TOL):
            raise PlanValidationError(
                f"hour {h} battery_energy_after_kwh mismatch: "
                f"reported={reported}, replayed={expected_energy:.6f}."
            )

    # ------------------------------------------------------------------ #
    # STEP 26 — Energy balance per hour                                    #
    # ------------------------------------------------------------------ #
    for i, entry in enumerate(plan):
        h = entry["hour"]
        lhs = entry["grid_kwh"] + entry["solar_used_kwh"] + discharge_arr[i]
        rhs = demand[h] + charge_arr[i]
        if not within_tolerance(lhs, rhs, TOL):
            raise PlanValidationError(
                f"hour {h} energy balance violated: "
                f"supply={lhs:.6f} != demand+charge={rhs:.6f}."
            )

    # ------------------------------------------------------------------ #
    # STEP 28 — Calculate totals independently                             #
    # ------------------------------------------------------------------ #
    total_grid_kwh = sum(e["grid_kwh"] for e in plan)
    total_cost_bdt = sum(
        e["grid_kwh"] * tariff[e["hour"]] for e in plan
    )
    peak_grid_kwh = max(e["grid_kwh"] for e in plan)

    return {
        "total_grid_kwh": total_grid_kwh,
        "total_cost_bdt": total_cost_bdt,
        "peak_grid_kwh": peak_grid_kwh,
    }
