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
        """
        Fetches test cases associated with a specific suite from the database.

        This method retrieves test case documents from the MongoDB collection based
        on the provided suite ID. It processes the documents to extract relevant
        data and constructs a list of `TestCaseData` objects, each of which
        contains the test ID and sorted road points for the test case.

        Args:
            suite_id (str): The unique identifier of the test suite for which
            test cases are to be retrieved.

        Returns:
            List[TestCaseData]: A list of `TestCaseData` objects containing test
            case details, including test ID and road points sorted by sequence
            number.

        Raises:
            PersistenceError: Raised when there is an issue fetching test cases
            from the database.
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
        """
        Inserts a batch of test cases into the database for a specified test suite.

        Before inserting the test cases, the method ensures that the specified test
        suite does not already exist. Each test case is processed to extract relevant
        data, including road points and creation timestamp.

        Args:
            suite_id: The unique identifier for the test suite.
            test_cases: A list of TestCase objects to be inserted into the database.

        Raises:
            TestSuiteAlreadyExistsError: If a test suite with the given suite_id
                has already been uploaded or contains test cases that already exist.
            PersistenceError: If there is an issue persisting test cases to the database.
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


