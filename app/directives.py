"""
directives.py — GridWise Developer 2

Translates validated canonical directives into effective per-hour
mathematical constraints consumed by the optimizer.

Supported directive types (only these):
    solar_reduction
    minimum_battery_reserve
    no_charge_window
    no_discharge_window
    max_grid_window
    no_op
"""

from __future__ import annotations

from dataclasses import dataclass, field
from app.math_utils import effective_solar_array, active_minimum_reserve


@dataclass
class EffectiveConstraints:
    """
    All per-hour constraint data derived from directives and base parameters.

    Consumed by optimizer.optimize_energy().
    """

    # Effective solar available per hour (after solar_reduction).
    effective_solar: list[float]  # length 24

    # Minimum battery energy after each hour (after minimum_battery_reserve).
    active_min_reserve: list[float]  # length 24

    # Set of hours where charging is forbidden.
    no_charge_hours: set[int]

    # Set of hours where discharging is forbidden.
    no_discharge_hours: set[int]

    # Per-hour grid cap; None means uncapped.
    max_grid_per_hour: list[float | None]  # length 24


def apply_directives(
    hours: list[dict],
    battery: dict,
    directives: list[dict],
) -> EffectiveConstraints:
    """
    Apply all validated directives and return an EffectiveConstraints object.

    Parameters
    ----------
    hours:
        24-element list of hour dicts (hour, demand_kwh, solar_kwh,
        tariff_bdt_per_kwh).
    battery:
        Battery parameter dict (capacity_kwh, initial_energy_kwh,
        minimum_energy_kwh, max_charge_kwh_per_hour,
        max_discharge_kwh_per_hour).
    directives:
        Canonical validated directive list produced by the guardrail module.
        Only entries with applies=True have mathematical effect.

    Returns
    -------
    EffectiveConstraints
    """
    # ---- Solar -------------------------------------------------------
    eff_solar = effective_solar_array(hours, directives)

    # ---- Minimum reserve per hour ------------------------------------
    min_reserve = [
        active_minimum_reserve(h, battery, directives) for h in range(24)
    ]

    # ---- Window restrictions -----------------------------------------
    no_charge: set[int] = set()
    no_discharge: set[int] = set()
    max_grid: list[float | None] = [None] * 24

    for d in directives:
        if not d.get("applies", False):
            continue

        dtype = d.get("directive_type")
        sa = d.get("structured_adjustment") or {}

        if dtype == "no_charge_window":
            for h in sa.get("hours", []):
                if 0 <= h <= 23:
                    no_charge.add(h)

        elif dtype == "no_discharge_window":
            for h in sa.get("hours", []):
                if 0 <= h <= 23:
                    no_discharge.add(h)

        elif dtype == "max_grid_window":
            cap = sa.get("max_grid_kwh")
            if cap is not None:
                for h in sa.get("hours", []):
                    if 0 <= h <= 23:
                        # Most restrictive cap wins when multiple rules overlap.
                        if max_grid[h] is None:
                            max_grid[h] = cap
                        else:
                            max_grid[h] = min(max_grid[h], cap)

        elif dtype in ("solar_reduction", "minimum_battery_reserve", "no_op"):
            # Already handled above or no-op.
            pass

    return EffectiveConstraints(
        effective_solar=eff_solar,
        active_min_reserve=min_reserve,
        no_charge_hours=no_charge,
        no_discharge_hours=no_discharge,
        max_grid_per_hour=max_grid,
    )
