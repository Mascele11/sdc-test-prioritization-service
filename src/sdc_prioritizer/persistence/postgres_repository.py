import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from psycopg_pool import ConnectionPool

from sdc_prioritizer.utils.exceptions import PersistenceError, TestSuiteAlreadyExistsError

# =============================================================================
#   Logger
# =============================================================================
logger = logging.getLogger(Path(__file__).stem)


# =============================================================================
#   PostgresTestSuiteRepository
# =============================================================================
class PostgresTestSuiteRepository:
    """Repository for suite metadata and evaluation history in PostgreSQL.
    For configuration see db/init.sql

    Stores (Tables):
    - test_suites  → one row per uploaded suite
    - evaluation_history → one row per evaluation run
    """

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    # -------------------------------------------------------------------------
    def suite_exists(self, suite_id: str) -> bool:
        """Return True if the suite_id is already registered."""
        with self._pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM test_suites WHERE suite_id = %s LIMIT 1",
                    (suite_id,),
                )
                return cur.fetchone() is not None

    # -------------------------------------------------------------------------
    def insert_suite(self, suite_id: str, test_count: int) -> datetime:
        """
        Inserts a test suite record into the PostgreSQL database.

        Args:
            suite_id: Unique identifier of the test suite.
            test_count: Number of tests contained in the test suite.

        Returns:
            datetime: The UTC timestamp representing when the suite was created and persisted.

        Raises:
            PersistenceError: If attempting to persist data in PostgreSQL fails due to any exception.
        """
        now = datetime.now(tz=timezone.utc)

        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO test_suites (suite_id, created_at, test_count)
                        VALUES (%s, %s, %s)
                        """,
                        (suite_id, now, test_count),
                    )
                conn.commit()

            logger.info("Persisted suite '%s' in PostgreSQL.", suite_id)
            return now

        except Exception as exc:
            logger.exception("PostgreSQL insert failed for suite '%s'.", suite_id)
            raise PersistenceError(
                "Failed to persist suite metadata in PostgreSQL."
            ) from exc

    # -------------------------------------------------------------------------
    def save_evaluation(
            self,
            suite_id: str,
            strategy: str,
            test_count: int,
            failures_detected: int,
            execution_cost: int,
            score: float,
            duration_ms: int,
    ) -> int:
        """
        Persist an evaluation record in the evaluation history database table and returns
        the generated evaluation ID.

        This function inserts a new row into the `evaluation_history` table with the
        provided evaluation details.

        Args:
            suite_id (str): Suite identifier associated with the evaluation.
            strategy (str): Strategy used during the evaluation.
            test_count (int): Total number of tests executed during the evaluation.
            failures_detected (int): Number of test failures detected during the evaluation.
            execution_cost (int): Cost associated with executing the evaluation.
            score (float): Computed score for the evaluation.
            duration_ms (int): Time taken for the evaluation in milliseconds.

        Returns:
            int: The identifier of the newly created evaluation record.

        Raises:
            PersistenceError: If an error occurs while storing the evaluation in the
            database.
        """
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO evaluation_history
                        (suite_id, strategy, test_count, failures_detected,
                         execution_cost, score, duration_ms)
                        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING evaluation_id
                        """,
                        (suite_id, strategy, test_count, failures_detected,
                         execution_cost, score, duration_ms),
                    )
                    evaluation_id = cur.fetchone()[0]
                conn.commit()

            logger.info(
                "Stored evaluation #%d for suite '%s' strategy '%s'.",
                evaluation_id, suite_id, strategy,
            )
            return evaluation_id

        except Exception as exc:
            logger.exception("Failed to store evaluation for suite '%s'.", suite_id)
            raise PersistenceError(
                "Failed to store evaluation in PostgreSQL."
            ) from exc

    # -------------------------------------------------------------------------
    def get_evaluation_history(self) -> List[tuple]:
        """Fetch all evaluation records for CSV export.

        Returns:
            List of tuples matching evaluation_history columns.

        Raises:
            PersistenceError: On unexpected database failure.
        """
        try:
            with self._pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT evaluation_id,
                               suite_id,
                               strategy,
                               test_count,
                               failures_detected,
                               execution_cost,
                               score,
                               duration_ms,
                               created_at
                        FROM evaluation_history
                        ORDER BY created_at DESC
                        """
                    )
                    return cur.fetchall()

        except Exception as exc:
            logger.exception("Failed to fetch evaluation history.")
            raise PersistenceError(
                "Failed to fetch evaluation history from PostgreSQL."
            ) from exc

    # -------------------------------------------------------------------------