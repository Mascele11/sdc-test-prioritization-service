import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from pymongo import MongoClient, ASCENDING
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError
from sdc_prioritizer.data_models.api_models import TestCase
from sdc_prioritizer.utils.exceptions import PersistenceError, TestSuiteAlreadyExistsError
from sdc_prioritizer.domain.strategies import TestCaseData
# =============================================================================
#   Logger
# =============================================================================
logger = logging.getLogger(Path(__file__).stem)


# =============================================================================
#   MongoTestCaseRepository
# =============================================================================
class MongoTestCaseRepository:
    """Repository responsible for persisting full test case documents
    (including road points) in MongoDB.

    One document per test case, stored in the configured collection.
    A unique compound index on (test_id, suite_id) prevents duplicate uploads.

    Duplicated error raised through DuplicateKeyError:
        example: suite_01, test_010, test_010
    """

    def __init__(self, client: MongoClient, database: str, collection: str) -> None:
        self._collection: Collection = client[database][collection]
        self._ensure_indexes()

    # -------------------------------------------------------------------------
    def _ensure_indexes(self) -> None:
        """Create indexes on first use make unique the values for each test case.
            Unique test case for couples (test_id, suite_id)"""
        self._collection.create_index(
            [("test_id", ASCENDING), ("suite_id", ASCENDING)],
            unique=True,
            name="uq_test_suite",
        )
        self._collection.create_index(
            [("suite_id", ASCENDING)],
            name="idx_suite_id",
        )
        logger.debug("MongoDB indexes ensured on collection '%s'.", self._collection.name)

    # -------------------------------------------------------------------------
    def suite_exists(self, suite_id: str) -> bool:
        """Return True if at least one document for the given suite_id exists."""
        return self._collection.count_documents({"suite_id": suite_id}, limit=1) > 0

    # -------------------------------------------------------------------------
    def get_test_cases_for_suite(self, suite_id: str) -> List[TestCaseData]:
        """Fetch all test cases with road points for a given suite -> endpoint 2.

        Args:
            suite_id: The suite to look up.

        Returns:
            List of TestCaseData domain objects with raw road points.

        Raises:
            PersistenceError: On unexpected database failure.
        """

        try:
            docs = self._collection.find({"suite_id": suite_id})
            results = []
            for doc in docs:
                road_points = [
                    (rp["x"], rp["y"])
                    for rp in sorted(doc["road_points"], key=lambda r: r["sequenceNumber"]) # extract actual points per rows
                ]
                results.append(TestCaseData(
                    test_id=doc["test_id"],
                    road_points=road_points,
                ))
            return results

        except Exception as exc:
            logger.exception("Failed to fetch test cases from MongoDB for suite '%s'.", suite_id)
            raise PersistenceError(
                "Failed to fetch test cases from MongoDB."
            ) from exc

    # -------------------------------------------------------------------------
    def insert_test_cases(self, suite_id: str, test_cases: List[TestCase]) -> None:
        """Bulk-insert test case documents for a given suite.

        Args:
            suite_id: The parent suite identifier.
            test_cases: Validated test case objects.

        Raises:
            TestSuiteAlreadyExistsError: If any document for this suite already exists.
            PersistenceError: On unexpected database failure.
        """
        if self.suite_exists(suite_id):
            raise TestSuiteAlreadyExistsError(
                f"Test suite '{suite_id}' has already been uploaded."
            )

        now = datetime.now(tz=timezone.utc)
        documents = [
            {
                "test_id": tc.testId,
                "suite_id": suite_id,
                "road_points": [
                    {"sequenceNumber": rp.sequenceNumber, "x": rp.x, "y": rp.y}
                    for rp in tc.roadPoints
                ],
                "created_at": now,
            }
            for tc in test_cases
        ] # tests cases extraction from input .json

        try:
            result = self._collection.insert_many(documents, ordered=False)
            logger.info(
                "Inserted %d test case documents for suite '%s'.",
                len(result.inserted_ids),
                suite_id,
            )
        except DuplicateKeyError as exc:
            raise TestSuiteAlreadyExistsError(
                f"Test suite '{suite_id}' contains test cases that already exist."
            ) from exc
        except Exception as exc:
            logger.exception("MongoDB insert_many failed for suite '%s'.", suite_id)
            raise PersistenceError("Failed to persist test cases in MongoDB.") from exc


