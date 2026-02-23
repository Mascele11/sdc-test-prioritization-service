import importlib.metadata
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from pymongo import MongoClient
from psycopg_pool import ConnectionPool

from dotenv import load_dotenv

import sdc_prioritizer  # triggers logging setup
from sdc_prioritizer.config import configuration
from sdc_prioritizer.domain.test_suite_service import TestSuiteService
from sdc_prioritizer.persistence.mongo_repository import MongoTestCaseRepository
from sdc_prioritizer.persistence.postgres_repository import PostgresTestSuiteRepository
from sdc_prioritizer.routers import test_suite_router, history_router

from fastapi.exceptions import RequestValidationError
from sdc_prioritizer.utils.error_handlers import validation_exception_handler

# ======================================================================================================================
#   Global Variables
# ======================================================================================================================
# setup logging
logger = logging.getLogger(Path(__file__).stem)
load_dotenv()

# =============================================================================
#   Lifespan – open and close DB connections around the app's lifetime
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open DB connections on startup; close them on shutdown."""

    mongo_url   = os.environ["MONGODB_URI"]
    postgres_uri = os.environ["POSTGRESQL_URI"]

    if not mongo_url:
        raise RuntimeError("MONGODB_URI environment variable is not set")

    logger.info("Connecting to MongoDB at %s", mongo_url)
    mongo_client = MongoClient(mongo_url) # TCP mongo handshake

    logger.info("Connecting to PostgreSQL (pool).")
    pg_pool = ConnectionPool(
        conninfo=postgres_uri,
        min_size=configuration.postgresql.pool_min_size,
        max_size=configuration.postgresql.pool_max_size,
        open=True,
    )

    # Wire up repositories and service, attach to app state
    mongo_repo   = MongoTestCaseRepository(
        client=mongo_client,
        database=configuration.mongodb.database,
        collection=configuration.mongodb.collection_test_cases,
    )
    postgres_repo = PostgresTestSuiteRepository(pool=pg_pool)

    app.state.test_suite_service = TestSuiteService(
        mongo_repo=mongo_repo,
        postgres_repo=postgres_repo,
    )

    logger.info("Application startup complete.")
    yield

    # Teardown
    logger.info("Shutting down – closing DB connections.")
    mongo_client.close()
    pg_pool.close()
    logger.info("Application shutdown complete.")


# =============================================================================
#   REST API app - SDC Test Prioritization Service
# =============================================================================
app = FastAPI(
    debug=False,
    title="SDC Test Prioritizer",
    description="REST API for uploading, prioritizing, and evaluating SDC test suites.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(test_suite_router)
app.include_router(history_router)

app.add_exception_handler(RequestValidationError, validation_exception_handler)


# =============================================================================
#   Root
# =============================================================================
@app.get("/", tags=["health"])
async def root() -> dict:
    """Health-check root endpoint."""
    return {"message": "SDC Test Prioritizer REST API is up and running."}


# =============================================================================
#   Entry point
# =============================================================================
def main() -> None:
    uvicorn.run(
        "main:app",
        host=configuration.server.host,
        port=configuration.server.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
