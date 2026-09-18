"""Domain exception hierarchy for GridWise energy optimization service."""


class GridWiseError(Exception):
    """Base domain exception for all GridWise application errors."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: str = "GRIDWISE_ERROR",
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code


class RequestValidationError(GridWiseError):
    """Raised when an incoming scenario request fails semantic or business validation."""

    def __init__(self, message: str):
        super().__init__(message, status_code=400, error_code="REQUEST_VALIDATION_ERROR")


class InterpretationError(GridWiseError):
    """Raised when the LLM module fails to produce a valid interpretation of operator notes."""

    def __init__(self, message: str):
        super().__init__(message, status_code=500, error_code="INTERPRETATION_ERROR")


class GuardrailValidationError(GridWiseError):
    """Raised when structured LLM output violates deterministic guardrail constraints."""

    def __init__(self, message: str):
        super().__init__(message, status_code=500, error_code="GUARDRAIL_VALIDATION_ERROR")


class OptimizationError(GridWiseError):
    """Raised when mathematical optimizer fails to find a feasible schedule or crashes."""

    def __init__(self, message: str):
        super().__init__(message, status_code=500, error_code="OPTIMIZATION_ERROR")


class PlanValidationError(GridWiseError):
    """Raised when the independent schedule validator rejects the optimizer's hourly plan."""

    def __init__(self, message: str):
        super().__init__(message, status_code=500, error_code="PLAN_VALIDATION_ERROR")


class ProviderError(GridWiseError):
    """Raised when external LLM provider calls time out, encounter connection failure, or fail."""

    def __init__(self, message: str):
        super().__init__(message, status_code=500, error_code="PROVIDER_ERROR")
