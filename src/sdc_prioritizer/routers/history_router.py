import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from sdc_prioritizer.data_models import ErrorResponse
from sdc_prioritizer.domain.test_suite_service import TestSuiteService
from sdc_prioritizer.utils.exceptions import PersistenceError

# =============================================================================
#   Logger
# =============================================================================
logger = logging.getLogger(Path(__file__).stem)

# =============================================================================
#   Router
# =============================================================================
router = APIRouter(prefix="/v1/history", tags=["history"])


# =============================================================================
#   Dependency
# =============================================================================
def get_test_suite_service(request: Request) -> TestSuiteService:
    """FastAPI dependency that resolves the TestSuiteService from app state."""
    return request.app.state.test_suite_service


# =============================================================================
#   Endpoint 4 — Export evaluation history (GET — CSV download)
# =============================================================================
@router.get(
    "/",
    summary="Export evaluation history as CSV.",
    description=(
        "Returns all stored evaluation sessions as a downloadable CSV file. "
        "Columns: session_id, timestamp, strategy, num_tests, "
        "num_failures, execution_cost, score, duration_ms."
    ),
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
async def export_history(
    service: TestSuiteService = Depends(get_test_suite_service),
) -> StreamingResponse:
    """Export evaluation history as CSV."""
    logger.debug("GET /v1/history/")

    try:
        csv_content = service.export_history_csv()
        return StreamingResponse(
            content=iter([csv_content]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=evaluation_history.csv"},
        )

    except PersistenceError as exc:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(message=str(exc)).model_dump(),
        )

    except Exception as exc:
        logger.exception("Unexpected error exporting history.")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(message=str(exc)).model_dump(),
        )