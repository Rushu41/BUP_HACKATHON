"""Pydantic schemas and contract definitions for GridWise energy optimization."""

from enum import Enum
import math
from typing import Any, Union
from typing_extensions import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class DirectiveType(str, Enum):
    """The six canonical directive types supported by GridWise."""

    SOLAR_REDUCTION = "solar_reduction"
    MINIMUM_BATTERY_RESERVE = "minimum_battery_reserve"
    NO_CHARGE_WINDOW = "no_charge_window"
    NO_DISCHARGE_WINDOW = "no_discharge_window"
    MAX_GRID_WINDOW = "max_grid_window"
    NO_OP = "no_op"


class BatteryAction(str, Enum):
    """Possible battery operations during a single hour."""

    CHARGE = "charge"
    DISCHARGE = "discharge"
    IDLE = "idle"


def _validate_hour_list(hours: list[int]) -> list[int]:
    """Validates that hours is a non-empty list of unique integers in range 0..23, sorted."""
    if not isinstance(hours, list):
        raise ValueError("hours must be an array of integers")
    if len(hours) == 0:
        raise ValueError("hours array cannot be empty for an active directive window")
    for h in hours:
        if not isinstance(h, int) or isinstance(h, bool):
            raise ValueError(f"hour {h} must be an integer")
        if h < 0 or h > 23:
            raise ValueError(f"hour {h} must be between 0 and 23")
    if len(hours) != len(set(hours)):
        raise ValueError("hours array must not contain duplicate hours")
    return sorted(hours)


class SolarReductionAdjustment(BaseModel):
    """Structured adjustment for solar_reduction directive."""

    model_config = ConfigDict(extra="forbid")

    hours: list[int]
    factor: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)

    @field_validator("hours")
    @classmethod
    def check_hours(cls, v: list[int]) -> list[int]:
        return _validate_hour_list(v)


class MinimumBatteryReserveAdjustment(BaseModel):
    """Structured adjustment for minimum_battery_reserve directive."""

    model_config = ConfigDict(extra="forbid")

    hours: list[int]
    minimum_energy_kwh: float = Field(ge=0.0, allow_inf_nan=False)

    @field_validator("hours")
    @classmethod
    def check_hours(cls, v: list[int]) -> list[int]:
        return _validate_hour_list(v)


class WindowAdjustment(BaseModel):
    """Structured adjustment for no_charge_window and no_discharge_window directives."""

    model_config = ConfigDict(extra="forbid")

    hours: list[int]

    @field_validator("hours")
    @classmethod
    def check_hours(cls, v: list[int]) -> list[int]:
        return _validate_hour_list(v)


class MaxGridWindowAdjustment(BaseModel):
    """Structured adjustment for max_grid_window directive."""

    model_config = ConfigDict(extra="forbid")

    hours: list[int]
    max_grid_kwh: float = Field(ge=0.0, allow_inf_nan=False)

    @field_validator("hours")
    @classmethod
    def check_hours(cls, v: list[int]) -> list[int]:
        return _validate_hour_list(v)


StructuredAdjustmentType = Union[
    SolarReductionAdjustment,
    MinimumBatteryReserveAdjustment,
    WindowAdjustment,
    MaxGridWindowAdjustment,
    dict[str, Any],
    None,
]


class DirectiveInterpretation(BaseModel):
    """Canonical representation of an interpreted operator note."""

    model_config = ConfigDict(extra="forbid")

    note_index: int = Field(ge=0)
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: StructuredAdjustmentType = None
    explanation: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_directive_integrity(self) -> Self:
        if self.directive_type == DirectiveType.NO_OP:
            if self.applies is not False:
                raise ValueError("no_op directive must have applies=False")
            if self.structured_adjustment is not None:
                raise ValueError("no_op directive must have structured_adjustment=None")
        else:
            if self.applies is not True:
                raise ValueError(f"{self.directive_type.value} directive must have applies=True")
            if self.structured_adjustment is None:
                raise ValueError(f"{self.directive_type.value} directive requires structured_adjustment")

            # Validate adjustment content according to directive type
            adj = self.structured_adjustment
            if isinstance(adj, dict):
                hours = adj.get("hours")
                if hours is None:
                    raise ValueError(f"{self.directive_type.value} structured_adjustment must contain 'hours'")
                _validate_hour_list(hours)

                if self.directive_type == DirectiveType.SOLAR_REDUCTION:
                    factor = adj.get("factor")
                    if factor is None or not isinstance(factor, (int, float)) or isinstance(factor, bool):
                        raise ValueError("solar_reduction requires numeric 'factor'")
                    if not math.isfinite(factor) or factor < 0.0 or factor > 1.0:
                        raise ValueError("solar_reduction factor must be a finite float between 0.0 and 1.0")
                elif self.directive_type == DirectiveType.MINIMUM_BATTERY_RESERVE:
                    val = adj.get("minimum_energy_kwh")
                    if val is None or not isinstance(val, (int, float)) or isinstance(val, bool):
                        raise ValueError("minimum_battery_reserve requires numeric 'minimum_energy_kwh'")
                    if not math.isfinite(val) or val < 0.0:
                        raise ValueError("minimum_battery_reserve must be a finite non-negative float")
                elif self.directive_type == DirectiveType.MAX_GRID_WINDOW:
                    val = adj.get("max_grid_kwh")
                    if val is None or not isinstance(val, (int, float)) or isinstance(val, bool):
                        raise ValueError("max_grid_window requires numeric 'max_grid_kwh'")
                    if not math.isfinite(val) or val < 0.0:
                        raise ValueError("max_grid_kwh must be a finite non-negative float")
        return self


class HourInput(BaseModel):
    """Input parameters for a single hour of the 24-hour planning horizon."""

    model_config = ConfigDict(extra="forbid")

    hour: int = Field(ge=0, le=23, description="Hour index (0-23)")
    demand_kwh: float = Field(ge=0.0, allow_inf_nan=False, description="Energy demand in kWh")
    solar_kwh: float = Field(ge=0.0, allow_inf_nan=False, description="Solar PV forecast in kWh")
    tariff_bdt_per_kwh: float = Field(ge=0.0, allow_inf_nan=False, description="Grid tariff rate in BDT/kWh")

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class BatteryInput(BaseModel):
    """Battery physical constraints and initial state."""

    model_config = ConfigDict(extra="forbid")

    capacity_kwh: float = Field(ge=0.0, allow_inf_nan=False, description="Total battery capacity in kWh")
    initial_energy_kwh: float = Field(ge=0.0, allow_inf_nan=False, description="Starting energy level in kWh")
    minimum_energy_kwh: float = Field(ge=0.0, allow_inf_nan=False, description="Base minimum energy reserve in kWh")
    max_charge_kwh_per_hour: float = Field(ge=0.0, allow_inf_nan=False, description="Max charge rate in kWh/hour")
    max_discharge_kwh_per_hour: float = Field(ge=0.0, allow_inf_nan=False, description="Max discharge rate in kWh/hour")

    @model_validator(mode="after")
    def check_battery_constraints(self) -> Self:
        if self.initial_energy_kwh > self.capacity_kwh:
            raise ValueError("initial_energy_kwh cannot exceed battery capacity_kwh")
        if self.minimum_energy_kwh > self.capacity_kwh:
            raise ValueError("minimum_energy_kwh cannot exceed battery capacity_kwh")
        if self.initial_energy_kwh < self.minimum_energy_kwh:
            raise ValueError("initial_energy_kwh cannot be below minimum_energy_kwh")
        return self

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class OptimizeEnergyRequest(BaseModel):
    """Complete input payload for /optimize-energy endpoint."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str = Field(min_length=1)
    operator_notes: list[str] = Field(min_length=1, max_length=3)
    hours: list[HourInput]
    battery: BatteryInput

    @field_validator("scenario_id")
    @classmethod
    def validate_scenario_id(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("scenario_id must not be empty or whitespace only")
        return stripped

    @field_validator("operator_notes")
    @classmethod
    def validate_operator_notes(cls, v: list[str]) -> list[str]:
        if len(v) < 1 or len(v) > 3:
            raise ValueError("operator_notes must contain between 1 and 3 items")
        cleaned_notes = []
        for i, note in enumerate(v):
            if not isinstance(note, str):
                raise ValueError(f"Note at index {i} must be a string")
            stripped = note.strip()
            if not stripped:
                raise ValueError(f"Note at index {i} must not be blank or whitespace only")
            cleaned_notes.append(stripped)
        return cleaned_notes

    @field_validator("hours")
    @classmethod
    def validate_hours(cls, v: list[HourInput]) -> list[HourInput]:
        if len(v) != 24:
            raise ValueError(f"hours must contain exactly 24 entries, received {len(v)}")
        seen_hours = set()
        for entry in v:
            if entry.hour in seen_hours:
                raise ValueError(f"duplicate hour {entry.hour} found in hours list")
            seen_hours.add(entry.hour)
        expected_hours = set(range(24))
        if seen_hours != expected_hours:
            missing_hours = sorted(expected_hours - seen_hours)
            raise ValueError(f"missing hours from complete 0-23 horizon: {missing_hours}")
        # Normalize to ascending order (0..23)
        return sorted(v, key=lambda x: x.hour)


class HourlyPlanEntry(BaseModel):
    """Scheduled energy flow for a single hour."""

    model_config = ConfigDict(extra="forbid")

    hour: int = Field(ge=0, le=23)
    grid_kwh: float = Field(ge=0.0, allow_inf_nan=False)
    solar_used_kwh: float = Field(ge=0.0, allow_inf_nan=False)
    battery_action: BatteryAction
    battery_kwh: float = Field(ge=0.0, allow_inf_nan=False)
    battery_energy_after_kwh: float = Field(ge=0.0, allow_inf_nan=False)

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class OptimizeEnergyResponse(BaseModel):
    """Final API response payload returned by POST /optimize-energy."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    directive_interpretation: list[DirectiveInterpretation]
    hourly_plan: list[HourlyPlanEntry]
    total_grid_kwh: float = Field(ge=0.0, allow_inf_nan=False)
    total_cost_bdt: float = Field(ge=0.0, allow_inf_nan=False)
    peak_grid_kwh: float = Field(ge=0.0, allow_inf_nan=False)
    plan_summary: str = Field(min_length=1)
