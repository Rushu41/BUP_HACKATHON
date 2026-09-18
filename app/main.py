"""FastAPI application entrypoint for GridWise Energy Optimization API."""

import logging
from typing import Any
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.exceptions import GridWiseError
from app.orchestrator import process_scenario
from app.schemas import OptimizeEnergyRequest, OptimizeEnergyResponse

# Configure logging without sensitive leakage
logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("gridwise")

app = FastAPI(
    title="GridWise Energy Optimization API",
    description="LLM-Assisted Smart Campus Energy Optimization Service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)


def _sanitize_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sanitizes Pydantic error dicts to ensure nested Exception objects in ctx are JSON serializable."""
    sanitized = []
    for err in errors:
        item = dict(err)
        if "ctx" in item and isinstance(item["ctx"], dict):
            item["ctx"] = {
                k: str(v) if isinstance(v, Exception) else v
                for k, v in item["ctx"].items()
            }
        sanitized.append(item)
    return jsonable_encoder(sanitized)


@app.exception_handler(RequestValidationError)
async def handle_request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handles schema and input validation errors, returning controlled HTTP 400."""
    cleaned_errors = _sanitize_validation_errors(exc.errors())
    logger.warning("Request validation failed: %s", cleaned_errors)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "detail": cleaned_errors,
            "error": "REQUEST_VALIDATION_ERROR",
        },
    )


@app.exception_handler(GridWiseError)
async def handle_gridwise_error(request: Request, exc: GridWiseError) -> JSONResponse:
    """Handles controlled domain exceptions cleanly."""
    logger.error("Domain exception [%s]: %s", exc.error_code, exc.message)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.message,
            "error": exc.error_code,
        },
    )


@app.exception_handler(StarletteHTTPException)
async def handle_starlette_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handles standard HTTP errors (e.g. 404, 405)."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "error": f"HTTP_{exc.status_code}",
        },
    )


@app.exception_handler(Exception)
async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """Catches all unexpected internal errors.

    Guarantees no raw stack traces, tokens, or environment secrets leak to clients.
    """
    logger.exception("Unhandled server exception encountered.")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error occurred while processing the energy schedule.",
            "error": "INTERNAL_SERVER_ERROR",
        },
    )


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> dict[str, str]:
    """Lightweight liveness and health probe."""
    return {"status": "ok"}


@app.post(
    "/optimize-energy",
    response_model=OptimizeEnergyResponse,
    status_code=status.HTTP_200_OK,
)
async def optimize_energy(request: OptimizeEnergyRequest) -> OptimizeEnergyResponse:
    """Main optimization endpoint coordinating LLM interpretation, guardrails, optimizer, and validation."""
    try:
        return await process_scenario(request)
    except GridWiseError:
        raise
    except Exception:
        logger.exception("Unhandled error encountered during scenario processing.")
        raise GridWiseError(
            message="Internal server error occurred while processing the energy schedule.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="INTERNAL_SERVER_ERROR",
        ) from None

