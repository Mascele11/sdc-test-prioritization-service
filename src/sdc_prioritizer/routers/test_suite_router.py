import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sdc_prioritizer.data_models import (
    ErrorResponse,
    UploadTestSuiteRequest,
    UploadTestSuiteResponse,
    PrioritizeResponse,
    EvaluateRequest,
    EvaluateResponse
)
from sdc_prioritizer.domain.test_suite_service import TestSuiteService # API Layer knows about Services
from sdc_prioritizer.domain.strategies import available_strategies
from sdc_prioritizer.utils.exceptions import (
    PersistenceError,
    StrategyNotFoundError,
    TestSuiteAlreadyExistsError,
    TestSuiteNotFoundError,
)

# =============================================================================
#   Logger
# =============================================================================
logger = logging.getLogger(Path(__file__).stem)

# =============================================================================
#   Endpoint 1 - upload-test-suites
# =============================================================================
router = APIRouter(prefix="/v1/test-suite", tags=["test-suite"]) #kebab-case


# =============================================================================
#   Dependency
# =============================================================================
def get_test_suite_service(request: Request) -> TestSuiteService:
    """FastAPI dependency that resolves the TestSuiteService from app state.
    Verify that the service has been initialized correctly in main"""
    return request.app.state.test_suite_service


# =============================================================================
#   Endpoint 1 - upload-test-suite
# =============================================================================
@router.post(
    "/", #RESTful server
    summary="Test suites upload endpoint.",
    description=(
        "Accepts a test suite in JSON format. "
        "Validates the input structure, then stores road points in MongoDB "
        "and suite metadata in PostgreSQL. "
        "Returns a conflict error if the testSuiteId already exists."
    ),
    response_model=UploadTestSuiteResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
async def upload_test_suite(
    body: UploadTestSuiteRequest,
    service: TestSuiteService = Depends(get_test_suite_service),
) -> JSONResponse:
    """Upload test suite endpoint handler.

    Args:
        body: Validated request payload, validated pydantic model class defined in api_models.py
        service: Injected TestSuiteService.

    Returns:
        201 with suite confirmation, or an appropriate error response.
    """
    logger.debug("POST /test-suite/upload – suiteId='%s'", body.testSuiteId)

    try:
        response = service.upload_test_suite(body)
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(mode="json"),
        )

    except TestSuiteAlreadyExistsError as exc:
        logger.warning("Duplicate upload attempt for suite '%s'.", body.testSuiteId)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=ErrorResponse(message=str(exc)).model_dump(),
        )

    except PersistenceError as exc:
        logger.exception("Persistence failure for suite '%s'.", body.testSuiteId)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(message=str(exc)).model_dump(),
        )

    except Exception as exc: # non predicted
        logger.exception("Unexpected error for suite '%s'.", body.testSuiteId)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(message=str(exc)).model_dump(),
        )


# =============================================================================
#   Endpoint 2 — Prioritize test suite (GET — stateless computation)
# =============================================================================
@router.get(
    "/prioritization",
    summary="Prioritize a test suite.",
    description=("Applies a named prioritization strategy to an existing test suite. "
        "Returns the ordered list of test IDs. "
        "Stateless — no data is stored. "
        f"Available strategies: {', '.join(available_strategies())}."
    ),
    response_model=PrioritizeResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
async def prioritize_test_suite(
    testSuiteId: str = Query(pattern=r"^suite_\d{2}$", description="Suite ID in format suite_XX"),
    strategy: str = Query(min_length=1, description="Prioritization strategy name."),
    service: TestSuiteService = Depends(get_test_suite_service),
) -> JSONResponse:
    """
    Prioritize a test suite using the specified strategy.


    Args:
        testSuiteId (str): Suite ID in the format 'suite_XX'. Must match the specified pattern.
        strategy (str): The name of the prioritization strategy. Must have a minimum length of 1.
        service (TestSuiteService): Dependency-injected service used to process the test suite.

    Returns:
        JSONResponse: Contains the response with an ordered list of test IDs or an error message.

    Raises:
        TestSuiteNotFoundError: If the specified test suite does not exist.
        StrategyNotFoundError: If the requested prioritization strategy is not found.
        PersistenceError: If there is a failure related to persistence.
        Exception: If any unexpected error occurs during execution.
    """
    logger.debug(
        "GET /v1/test-suite/prioritization – suiteId='%s', strategy='%s'",
        testSuiteId, strategy,
    )

    try:
        response = service.prioritize_test_suite(testSuiteId, strategy)
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=response.model_dump(mode="json"),
        )

    except TestSuiteNotFoundError as exc:
        logger.warning("Suite not found: '%s'.", testSuiteId)
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(message=str(exc)).model_dump(),
        )

    except StrategyNotFoundError as exc:
        logger.warning("Unknown strategy: '%s'.", strategy)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(message=str(exc)).model_dump(),
        )

    except PersistenceError as exc:
        logger.exception("Persistence failure for suite '%s'.", testSuiteId)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(message=str(exc)).model_dump(),
        )

    except Exception as exc:
        logger.exception("Unexpected error during prioritization of suite '%s'.", testSuiteId)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(message=str(exc)).model_dump(),
        )


# =============================================================================
#   Endpoint 3 — Evaluate test suite (POST — creates evaluation report)
# =============================================================================
@router.post(
    "/evaluation",
    summary="Evaluate a test suite.",
    description=(
        "Prioritizes test cases using the given strategy, simulates"
        "with a deterministic mock failure function and budget mode. "
        "Computes APFD score and stores the evaluation report. "
        f"Available strategies: {', '.join(available_strategies())}."
    ),
    response_model=EvaluateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_404_NOT_FOUND: {"model": ErrorResponse},
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
async def evaluate_test_suite(
    body: EvaluateRequest,
    service: TestSuiteService = Depends(get_test_suite_service),
) -> JSONResponse:
    """
    Evaluates a test suite by prioritizing test cases using a specified strategy
    and evaluation mode (budget and no budget).

    Args:
        body (EvaluateRequest): The request body containing the test suite ID,
            the prioritization strategy and the evaluation mode.
        service (TestSuiteService): A dependency-injected service responsible for
            managing and evaluating test suites.

    Returns:
        JSONResponse: The HTTP response indicating the evaluation outcome or
        describing the encountered error.

    Raises:
        TestSuiteNotFoundError: Raised if the test suite with the given ID is
            not found.
        StrategyNotFoundError: Raised if the provided strategy is unrecognized.
        PersistenceError: Raised if there is an error during the persistence
            operation.
        Exception: Catches and logs unexpected errors, returning an internal
            server error response.
    """
    logger.debug(
        "POST /v1/test-suite/evaluation – suiteId='%s', strategy='%s'",
        body.testSuiteId, body.strategy,
    )

    try:
        response = service.evaluate_test_suite(body)
        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content=response.model_dump(mode="json"),
        )

    except TestSuiteNotFoundError as exc:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=ErrorResponse(message=str(exc)).model_dump(),
        )

    except StrategyNotFoundError as exc:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(message=str(exc)).model_dump(),
        )

    except PersistenceError as exc:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(message=str(exc)).model_dump(),
        )

    except Exception as exc:
        logger.exception("Unexpected error during evaluation of suite '%s'.", body.testSuiteId)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(message=str(exc)).model_dump(),
        )