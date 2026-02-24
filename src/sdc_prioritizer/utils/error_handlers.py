"""Global exception handlers registered on the FastAPI application. """

import logging
from pathlib import Path

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from sdc_prioritizer.data_models.error_responses import ErrorResponse

# =============================================================================
#   Logger
# =============================================================================
logger = logging.getLogger(Path(__file__).stem)


# =============================================================================
#   Validation Error Handler
# =============================================================================
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handles validation exceptions raised when request validation fails.

    Args:
        request (Request): The HTTP request object that triggered the validation error.
        exc (RequestValidationError): The exception object containing details of
            validation failures.

    Returns:
        JSONResponse: A JSON response object with HTTP status code 422, containing
            a message and detailed error information.
    """
    errors = []
    for error in exc.errors():
        field = " → ".join(str(loc) for loc in error["loc"])
        errors.append(f"{field}: {error['msg']}")

    logger.warning("Validation failed for %s %s: %s", request.method, request.url.path, errors)

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            message="Validation failed. Check your request body.",
            details=errors,
        ).model_dump(),
    )