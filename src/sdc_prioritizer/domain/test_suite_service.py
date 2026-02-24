import logging
from datetime import datetime
from pathlib import Path
import time
import csv
import io
from sdc_prioritizer.data_models.api_models import (
    UploadTestSuiteRequest,
    UploadTestSuiteResponse,
    PrioritizeResponse,
    EvaluateRequest,
    EvaluateResponse,
)
from sdc_prioritizer.domain.strategies import get_strategy
from sdc_prioritizer.domain.evaluation import mock_has_failed, compute_apfd
from sdc_prioritizer.persistence.mongo_repository import MongoTestCaseRepository
from sdc_prioritizer.persistence.postgres_repository import PostgresTestSuiteRepository
from sdc_prioritizer.utils.exceptions import TestSuiteAlreadyExistsError, TestSuiteNotFoundError

# =============================================================================
#   Logger
# =============================================================================
logger = logging.getLogger(Path(__file__).stem)


# =============================================================================
#   TestSuiteService
# =============================================================================
class TestSuiteService:
    """Orchestrates the methodology for
        uploading,
        prioritizing,
        and evaluating test suites.

    Responsibility split:
    - PostgreSQL  → test suites metadata, evaluation history
    - MongoDB     → full test case documents with all road points

    The check for duplicate suite_id is done first in PostgreSQL (the
    authoritative metadata store). If that passes, road points are written
    to MongoDB.
    """

    def __init__(
        self,
        mongo_repo: MongoTestCaseRepository,
        postgres_repo: PostgresTestSuiteRepository,
    ) -> None:
        self._mongo = mongo_repo
        self._postgres = postgres_repo

    # -------------------------------------------------------------------------
    def upload_test_suite(self, request: UploadTestSuiteRequest) -> UploadTestSuiteResponse:
        """Validate, store, and confirm a test suite upload.

        Args:
            request: Validated upload request.

        Returns:
            Response with suite metadata.

        Raises:
            TestSuiteAlreadyExistsError: If the suite_id was already uploaded.
            PersistenceError: On database failure. Coming from postegres_repository.py
        """
        suite_id = request.testSuiteId
        test_cases = request.tests

        logger.info(
            "Uploading test suite '%s' with %d test cases.", suite_id, len(test_cases)
        )

        # 1. Guard: check for duplicates before touching any DB
        if self._postgres.suite_exists(suite_id):
            raise TestSuiteAlreadyExistsError(
                f"Test suite '{suite_id}' has already been uploaded."
            )

        # 2. Write road points to MongoDB
        self._mongo.insert_test_cases(suite_id=suite_id, test_cases=test_cases)
        logger.debug("MongoDB write complete for suite '%s'.", suite_id)

        # 3. Write metadata + precomputed geometry to PostgreSQL
        created_at: datetime = self._postgres.insert_suite(
            suite_id=suite_id, test_count=len(test_cases)
        )
        logger.debug("PostgreSQL write complete for suite '%s'.", suite_id)

        logger.info("Test suite '%s' uploaded successfully.", suite_id)

        return UploadTestSuiteResponse(
            testSuiteId=suite_id,
            testCount=len(test_cases),
            createdAt=created_at,
        )

    # -------------------------------------------------------------------------
    def prioritize_test_suite(self, suite_id: str, strategy_name: str) -> PrioritizeResponse:
        """
        Prioritizes a test suite by applying a specified prioritization strategy.

        This method ensures that the test suite exists, determines the correct strategy
        to apply, fetches the necessary test cases from the database, performs the prioritization,
        and returns an ordered list of test case IDs.

        Args:
            suite_id (str): Identifier of the test suite to prioritize.
            strategy_name (str): Name of the prioritization strategy to apply.

        Returns:
            PrioritizeResponse: Response containing the prioritized test suite details.

        Raises:
            TestSuiteNotFoundError: If the specified test suite does not exist in the system.
            StrategyNotFoundError: If the specified prioritization strategy is not available.
        """
        suite_id = suite_id
        strategy_name = strategy_name

        logger.info(
            "Prioritizing suite '%s' with strategy '%s'.",
            suite_id, strategy_name,
        )

        # 1. Guard: check suite exists (fast check in PostgreSQL)
        if not self._postgres.suite_exists(suite_id):
            raise TestSuiteNotFoundError(f"Test suite '{suite_id}' not found.")

        # 2. Resolve strategy (raises StrategyNotFoundError if invalid)
        strategy = get_strategy(strategy_name)

        # 3. Fetch raw road points from MongoDB
        test_cases = self._mongo.get_test_cases_for_suite(suite_id)

        # 4. Strategy computes its own metrics and sorts
        ordered_ids = strategy.prioritize(test_cases)

        logger.info(
            "Suite '%s' prioritized: %d tests ordered by '%s'.",
            suite_id, len(ordered_ids), strategy_name,
        )

        return PrioritizeResponse(
            testSuiteId=suite_id,
            strategy=strategy_name,
            orderedTests=ordered_ids,
        )

    # -------------------------------------------------------------------------
    def evaluate_test_suite(self, request: EvaluateRequest) -> EvaluateResponse:
        """
        Evaluates a test suite using a specified prioritization strategy and computes
        metrics such as failure counts, execution costs, and APFD score. It
        also saves the evaluation report to PostgreSQL for future persistance.

        Args:
            request (EvaluateRequest): A request object containing the test suite ID,
                the prioritization strategy to apply, and other optional parameters
                like budget for execution.

        Returns:
            EvaluateResponse: An object containing the results of the evaluation,
                including evaluation ID, test suite ID, selected strategy, number of
                failures detected, execution cost, and APFD score.

        Raises:
            TestSuiteNotFoundError: If the specified test suite does not exist in the
                PostgreSQL database.
        """
        suite_id = request.testSuiteId
        strategy_name = request.strategy

        logger.info(
            "Evaluating suite '%s' with strategy '%s'.", suite_id, strategy_name,
        )

        start_time = time.time() # Measures execution time

        # 1. Guard: check suite exists
        if not self._postgres.suite_exists(suite_id):
            raise TestSuiteNotFoundError(f"Test suite '{suite_id}' not found in PostgreSQL - Please upload test suite.")

        # 2. Fetch strategy
        strategy = get_strategy(strategy_name)

        # 3. Fetch road points from MongoDB
        test_cases = self._mongo.get_test_cases_for_suite(suite_id)

        # 4. Prioritize
        ordered_ids = strategy.prioritize(test_cases)

        # 5. Simulate execution in prioritized order
        tc_map = {tc.test_id: tc for tc in test_cases}
        failure_map = {}
        failures = 0
        execution_cost = 0
        remaining = None

        for test_id in ordered_ids:
            tc = tc_map[test_id]

            # Budget mode: stop if budget would be exceeded
            if request.budget is not None and execution_cost >= request.budget:
                break

            # Budget mode: compute used points a set limit to test simulation
            if request.budget is not None:
                remaining = request.budget - execution_cost

            # Get failed test and road points executed or limit:
            failed, test_execution_cost = mock_has_failed(tc, max_points=remaining)

            failure_map[test_id] = failed
            execution_cost += test_execution_cost

            if failed:
                failures += 1

        # 6. Compute APFD score
        score = compute_apfd(ordered_ids, failure_map)

        # 7. Compute duration
        duration_ms = int((time.time() - start_time) * 1000)

        # 8. Store evaluation report in PostgreSQL
        evaluation_id = self._postgres.save_evaluation(
            suite_id=suite_id,
            strategy=strategy_name,
            test_count=len(test_cases),
            failures_detected=failures,
            execution_cost=execution_cost,
            score=round(score, 4),
            duration_ms=duration_ms,
        )

        logger.info(
            "Evaluation #%d complete: %d failures, cost=%d, score=%.3f, duration=%dms",
            evaluation_id, failures, execution_cost, score, duration_ms,
        )

        # Evaluation ID added for completeness
        return EvaluateResponse(
            evaluationId=evaluation_id,
            testSuiteId=suite_id,
            strategy=strategy_name,
            failuresDetected=failures,
            executionCost=execution_cost,
            score=round(score, 4),
        )

    # -------------------------------------------------------------------------
    def export_history_csv(self) -> str:
        """Export all evaluation sessions as a CSV string.

        Returns:
            CSV-formatted string ready for download.
        """
        logger.info("Exporting evaluation history as CSV.")

        rows = self._postgres.get_evaluation_history()

        output = io.StringIO()
        writer = csv.writer(output)

        # Header matching PDF spec
        writer.writerow([
            "session_id", "timestamp", "strategy", "num_tests",
            "num_failures", "execution_cost", "score", "duration_ms",
        ])

        for row in rows:
            writer.writerow([
                row[0],  # evaluation_id → session_id
                row[8],  # created_at → timestamp
                row[2],  # strategy
                row[3],  # test_count → num_tests
                row[4],  # failures_detected → num_failures
                row[5],  # execution_cost
                row[6],  # score
                row[7],  # duration_ms
            ])

        logger.info("Exported %d evaluation records.", len(rows))
        return output.getvalue()