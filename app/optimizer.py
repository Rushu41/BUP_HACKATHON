"""
optimizer.py — GridWise Developer 2

MILP energy-dispatch optimizer using PuLP + CBC.

Public interface (matches team contract):

    def optimize_energy(
        hours: list[dict],
        battery: dict,
        directives: list[dict],
    ) -> list[dict]

Returns 24 hourly_plan entries in the canonical format.
"""

from __future__ import annotations

import math
import pulp

from app.directives import apply_directives
from app.exceptions import OptimizationError
from app.math_utils import clamp_near_zero, NUMERIC_TOLERANCE

# Alias for backward compatibility
OptimizerError = OptimizationError


def optimize_energy(
    hours: list[dict],
    battery: dict,
    directives: list[dict],
) -> list[dict]:
    """
    Minimize total grid electricity cost subject to energy-balance,
    battery physics, and directive constraints.

    Parameters
    ----------
    hours:
        24-element list of hour dicts sorted by hour (0..23).
        Each: {hour, demand_kwh, solar_kwh, tariff_bdt_per_kwh}
    battery:
        {capacity_kwh, initial_energy_kwh, minimum_energy_kwh,
         max_charge_kwh_per_hour, max_discharge_kwh_per_hour}
    directives:
        Canonical validated directive list from the guardrail module.

    Returns
    -------
    list[dict]
        24 hourly plan entries, each:
        {hour, grid_kwh, solar_used_kwh, battery_action,
         battery_kwh, battery_energy_after_kwh}

    Raises
    ------
    OptimizerError
        If the problem is infeasible or the solver fails.
    """
    # Sort hours defensively.
    sorted_hours = sorted(hours, key=lambda x: x["hour"])
    if len(sorted_hours) != 24:
        raise OptimizerError(
            f"Expected exactly 24 hours, got {len(sorted_hours)}."
        )

    # ---- Unpack battery parameters ------------------------------------
    capacity = battery["capacity_kwh"]
    initial = battery["initial_energy_kwh"]
    max_charge_rate = battery["max_charge_kwh_per_hour"]
    max_discharge_rate = battery["max_discharge_kwh_per_hour"]

    # ---- Apply directives --------------------------------------------
    constraints = apply_directives(sorted_hours, battery, directives)
    eff_solar = constraints.effective_solar
    min_reserve = constraints.active_min_reserve
    no_charge_h = constraints.no_charge_hours
    no_discharge_h = constraints.no_discharge_hours
    max_grid_h = constraints.max_grid_per_hour

    # ---- Build MILP problem ------------------------------------------
    prob = pulp.LpProblem("GridWise_Optimizer", pulp.LpMinimize)

    # Decision variables
    grid = [
        prob.add_variable(f"grid_{h}", lowBound=0.0) for h in range(24)
    ]
    solar_used = [
        prob.add_variable(f"solar_used_{h}", lowBound=0.0) for h in range(24)
    ]
    charge = [
        prob.add_variable(f"charge_{h}", lowBound=0.0) for h in range(24)
    ]
    discharge = [
        prob.add_variable(f"discharge_{h}", lowBound=0.0) for h in range(24)
    ]
    energy_after = [
        prob.add_variable(f"energy_after_{h}", lowBound=0.0) for h in range(24)
    ]
    # Binary mode: 1 → may charge, 0 → may discharge.
    # Only needed when both rates > 0.
    use_binary = max_charge_rate > 0 and max_discharge_rate > 0
    if use_binary:
        mode = [
            prob.add_variable(f"mode_{h}", cat=pulp.LpBinary) for h in range(24)
        ]

    # ---- Objective ---------------------------------------------------
    prob += pulp.lpSum(
        grid[h] * sorted_hours[h]["tariff_bdt_per_kwh"] for h in range(24)
    ), "Minimize_grid_cost"

    # ---- Constraints -------------------------------------------------
    for h in range(24):
        demand = sorted_hours[h]["demand_kwh"]
        tariff = sorted_hours[h]["tariff_bdt_per_kwh"]  # noqa: F841 (kept for clarity)

        # 1. Energy balance
        prob += (
            grid[h] + solar_used[h] + discharge[h]
            == demand + charge[h]
        ), f"energy_balance_{h}"

        # 2. Solar limit
        prob += solar_used[h] <= eff_solar[h], f"solar_limit_{h}"

        # 3. Battery transition
        energy_before = initial if h == 0 else energy_after[h - 1]
        prob += (
            energy_after[h] == energy_before + charge[h] - discharge[h]
        ), f"battery_transition_{h}"

        # 4. Battery bounds
        prob += energy_after[h] >= min_reserve[h], f"battery_min_{h}"
        prob += energy_after[h] <= capacity, f"battery_max_{h}"

        # 5. Charge rate limit
        if h in no_charge_h or max_charge_rate == 0:
            prob += charge[h] == 0, f"no_charge_{h}"
        else:
            prob += charge[h] <= max_charge_rate, f"charge_rate_{h}"

        # 6. Discharge rate limit
        if h in no_discharge_h or max_discharge_rate == 0:
            prob += discharge[h] == 0, f"no_discharge_{h}"
        else:
            prob += discharge[h] <= max_discharge_rate, f"discharge_rate_{h}"

        # 7. Prevent simultaneous charge + discharge (binary mode)
        if use_binary:
            if h not in no_charge_h and max_charge_rate > 0:
                prob += (
                    charge[h] <= max_charge_rate * mode[h]
                ), f"mode_charge_{h}"
            if h not in no_discharge_h and max_discharge_rate > 0:
                prob += (
                    discharge[h] <= max_discharge_rate * (1 - mode[h])
                ), f"mode_discharge_{h}"

        # 8. Grid cap from max_grid_window directive
        if max_grid_h[h] is not None:
            prob += grid[h] <= max_grid_h[h], f"grid_cap_{h}"

    # 9. End-of-day neutrality (mandatory)
    prob += energy_after[23] == initial, "end_of_day_neutrality"

    # ---- Solve -------------------------------------------------------
    solver = pulp.PULP_CBC_CMD(msg=False)  # silent
    status = prob.solve(solver)

    if pulp.LpStatus[status] != "Optimal":
        raise OptimizerError(
            f"Solver returned non-optimal status: {pulp.LpStatus[status]}. "
            "The scenario may be infeasible given the directives and battery constraints."
        )

    # ---- Extract results ---------------------------------------------
    TOL = NUMERIC_TOLERANCE
    plan = []
    for h in range(24):
        g = clamp_near_zero(pulp.value(grid[h]))
        s = clamp_near_zero(pulp.value(solar_used[h]))
        c = clamp_near_zero(pulp.value(charge[h]))
        d = clamp_near_zero(pulp.value(discharge[h]))
        ea = pulp.value(energy_after[h])

        # Determine battery action and magnitude
        if c > TOL:
            action = "charge"
            batt_kwh = c
        elif d > TOL:
            action = "discharge"
            batt_kwh = d
        else:
            action = "idle"
            batt_kwh = 0.0
            c = 0.0
            d = 0.0

        plan.append(
            {
                "hour": h,
                "grid_kwh": round(max(g, 0.0), 6),
                "solar_used_kwh": round(max(s, 0.0), 6),
                "battery_action": action,
                "battery_kwh": round(max(batt_kwh, 0.0), 6),
                "battery_energy_after_kwh": round(ea, 6),
            }
        )

    return plan
