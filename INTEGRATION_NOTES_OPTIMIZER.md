# INTEGRATION_NOTES_OPTIMIZER.md
# GridWise — Developer 2 (Optimizer)

## Required Dependency

```
pulp>=2.8.0
```

**Reason**: MILP optimization via PuLP + CBC solver.  
`pulp` bundles the CBC binary; no separate CBC installation needed on most platforms.

**Docker note**: CBC availability verified locally (Windows). If CBC is unavailable in the container, `pulp` will raise a solver error — install the `coinor-cbc` system package inside the Dockerfile:

```dockerfile
RUN apt-get install -y coinor-cbc
```

---

## Integration Function Signatures

### `app/optimizer.py`

```python
def optimize_energy(
    hours: list[dict],
    battery: dict,
    directives: list[dict],
) -> list[dict]:
    ...
```

**Input `hours`** — 24 elements, each:
```json
{
  "hour": 0,
  "demand_kwh": 10.0,
  "solar_kwh": 5.0,
  "tariff_bdt_per_kwh": 4.5
}
```

**Input `battery`**:
```json
{
  "capacity_kwh": 100.0,
  "initial_energy_kwh": 30.0,
  "minimum_energy_kwh": 5.0,
  "max_charge_kwh_per_hour": 20.0,
  "max_discharge_kwh_per_hour": 20.0
}
```

**Input `directives`** — canonical validated list from guardrails (Developer 3):
```json
[
  {
    "note_index": 0,
    "applies": true,
    "directive_type": "solar_reduction",
    "structured_adjustment": {"hours": [10, 11, 12], "factor": 0.3},
    "explanation": "..."
  }
]
```

**Output** — 24 entries:
```json
[
  {
    "hour": 0,
    "grid_kwh": 4.2,
    "solar_used_kwh": 3.1,
    "battery_action": "charge",
    "battery_kwh": 2.7,
    "battery_energy_after_kwh": 32.7
  }
]
```

**Raises**: `OptimizerError` on infeasibility or solver failure (controlled failure, no raw trace exposed).

---

### `app/validator.py`

```python
def validate_hourly_plan(
    hours: list[dict],
    battery: dict,
    directives: list[dict],
    hourly_plan: list[dict],
) -> dict:
    ...
```

**Output**:
```json
{
  "total_grid_kwh": 123.45,
  "total_cost_bdt": 678.90,
  "peak_grid_kwh": 12.3
}
```

**Raises**: `PlanValidationError` on any constraint violation.

---

### `app/directives.py`

```python
def apply_directives(
    hours: list[dict],
    battery: dict,
    directives: list[dict],
) -> EffectiveConstraints:
    ...
```

Returns an `EffectiveConstraints` dataclass consumed internally by the optimizer. Developer 1 and Developer 3 do not need to call this directly.

---

## Orchestration Call Order (for Developer 1)

```python
# 1. LLM interpretation (Dev 3)
raw_interpretations = await interpret_operator_notes(operator_notes, battery, hours)

# 2. Guardrail validation (Dev 3)
directives = validate_interpretations(raw_interpretations, operator_notes, battery)

# 3. MILP optimization (Dev 2)
hourly_plan = optimize_energy(hours, battery, directives)

# 4. Independent schedule validation (Dev 2)
totals = validate_hourly_plan(hours, battery, directives, hourly_plan)

# 5. Build API response (Dev 1)
```

---

## Known Limitations

- **No grid export**: `grid[h]` is always ≥ 0. Excess solar is curtailed (not exported).
- **Battery efficiency**: 100% round-trip efficiency assumed (no explicit charge/discharge efficiency losses). If efficiency < 1.0 is added later, both optimizer and validator must be updated together.
- **Infeasible scenarios**: If directives are mutually contradictory (e.g., very high minimum reserve + no-charge-window blocking the only feasible charge hours), the optimizer raises `OptimizerError`. The orchestrator (Dev 1) should return a controlled HTTP 500 with a safe error message.
- **Solver time limit**: Not set by default. For very large or constrained problems this could block. A time limit can be added to `PULP_CBC_CMD` if needed.
