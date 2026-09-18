"""
math_utils.py — GridWise Developer 2

Small numeric helpers shared by optimizer and validator.
"""

from __future__ import annotations

NUMERIC_TOLERANCE = 0.01  # kWh / BDT


def clamp_near_zero(val: float, tol: float = 1e-6) -> float:
    """
    Suppress solver floating-point noise.

    Values that are negative and within tol of zero are clamped to 0.0.
    Genuine negative values outside tolerance are left untouched so that
    the validator can still detect them as violations.
    """
    if -tol < val < 0.0:
        return 0.0
    return val


def within_tolerance(a: float, b: float, tol: float = NUMERIC_TOLERANCE) -> bool:
    """Return True if |a - b| <= tol."""
    return abs(a - b) <= tol


def active_minimum_reserve(
    h: int,
    battery: dict,
    directives: list[dict],
) -> float:
    """
    Compute the effective minimum battery energy for hour h.

    active_minimum[h] = max(battery.minimum_energy_kwh, max directive reserve for h)
    """
    base = battery["minimum_energy_kwh"]
    extra = base
    for d in directives:
        if d.get("directive_type") == "minimum_battery_reserve" and d.get("applies"):
            sa = d.get("structured_adjustment") or {}
            if h in sa.get("hours", []):
                extra = max(extra, sa.get("minimum_energy_kwh", base))
    return extra


def effective_solar_array(
    hours: list[dict],
    directives: list[dict],
) -> list[float]:
    """
    Return a 24-element list of effective solar values after applying all
    solar_reduction directives.

    When multiple solar_reduction rules affect the same hour the factors
    are multiplied together (most restrictive composition that is
    mathematically consistent with each rule's semantics).
    """
    solar = [h["solar_kwh"] for h in sorted(hours, key=lambda x: x["hour"])]
    # Accumulate factor products per hour; start at 1.0 (no reduction)
    factors = [1.0] * 24
    for d in directives:
        if d.get("directive_type") == "solar_reduction" and d.get("applies"):
            sa = d.get("structured_adjustment") or {}
            factor = sa.get("factor", 1.0)
            for h in sa.get("hours", []):
                if 0 <= h <= 23:
                    factors[h] *= factor
    return [solar[h] * factors[h] for h in range(24)]
