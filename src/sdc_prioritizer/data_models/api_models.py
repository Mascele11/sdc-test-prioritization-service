from datetime import datetime
from typing import List

from pydantic import BaseModel, Field, field_validator


# =============================================================================
#   Primitives
# =============================================================================
class RoadPoint(BaseModel):
    """A single point along a simulated road."""

    sequenceNumber: int = Field(ge=0, description="0-based position in the road sequence.")
    x: float
    y: float

class TestCase(BaseModel):
    """A single SDC test case as provided by the caller."""

    testId: str = Field(pattern=r"^TC_\d{3}$", # Pattern specified in pdf: TC_XXX
                        description="Test ID in format TC_XXX")
    roadPoints: List[RoadPoint] = Field(min_length=1, description="Ordered road points.")

    @field_validator("roadPoints")
    def road_points_must_be_ordered(cls, v: List[RoadPoint]) -> List[RoadPoint]:
        """Ensure sequence numbers are contiguous and start at 0."""
        for expected, rp in enumerate(v):
            if rp.sequenceNumber != expected:
                raise ValueError(
                    f"Road points must be ordered starting at 0. "
                    f"Expected sequenceNumber={expected}, got {rp.sequenceNumber}."
                )
        return v


# =============================================================================
#   Request - Endpoint 1 Upload
# =============================================================================
class UploadTestSuiteRequest(BaseModel):
    """
    Represents a request to upload a test suite.

    This class is used to encapsulate the necessary details required to upload
    a test suite. It ensures that a caller-assigned unique identifier for the
    suite is provided and at least one test case is included in the suite.
    The integrity of the suite is validated to ensure all test case IDs within
    the suite are unique.

    Attributes:
        testSuiteId (str): Caller-assigned suite identifier.
        tests (List[TestCase]): A list of test cases, with at least one test case
            required. At least one test case is required in the body of requests.
    """

    testSuiteId: str = Field(pattern=r"^suite_\d{2}$", # Pattern specified in pdf: suite_XX
                             description="Suite ID in format suite_XX")
    tests: List[TestCase] = Field(min_length=1, description="At least one test case required.")

    @field_validator("tests")
    def test_ids_must_be_unique(cls, v: List[TestCase]) -> List[TestCase]:
        ids = [tc.testId for tc in v]
        if len(ids) != len(set(ids)):
            duplicates = {i for i in ids if ids.count(i) > 1}
            # check for duplicate before calling persistance layer
            raise ValueError(f"Duplicate testIds found within the suite: {duplicates}")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [{
              "testSuiteId": "suite_01",
              "tests": [
                {
                  "testId": "TC_001",
                  "roadPoints": [
                    {"sequenceNumber": 0, "x": 0.0, "y": 0.0},
                    {"sequenceNumber": 1, "x": 5.0, "y": 1.0},
                    {"sequenceNumber": 2, "x": 10.0, "y": 3.0},
                    {"sequenceNumber": 3, "x": 15.0, "y": 6.0},
                    {"sequenceNumber": 4, "x": 20.0, "y": 10.0}
                  ]
                },
                {
                  "testId": "TC_002",
                  "roadPoints": [
                    {"sequenceNumber": 0, "x": 0.0, "y": 0.0},
                    {"sequenceNumber": 1, "x": 3.0, "y": 2.0}
                  ]
                },
                {
                  "testId": "TC_003",
                  "roadPoints": [
                    {"sequenceNumber": 0, "x": 0.0, "y": 0.0},
                    {"sequenceNumber": 1, "x": 2.0, "y": 1.0},
                    {"sequenceNumber": 2, "x": 4.0, "y": 3.0},
                    {"sequenceNumber": 3, "x": 6.0, "y": 6.0},
                    {"sequenceNumber": 4, "x": 8.0, "y": 10.0}
                  ]
                },
                {
                  "testId": "TC_004",
                  "roadPoints": [
                    {"sequenceNumber": 0, "x": 0.0, "y": 0.0},
                    {"sequenceNumber": 1, "x": 10.0, "y": 0.0},
                    {"sequenceNumber": 2, "x": 10.0, "y": 10.0},
                    {"sequenceNumber": 3, "x": 15.0, "y": 12.0}
                  ]
                },
                {
                  "testId": "TC_005",
                  "roadPoints": [
                    {"sequenceNumber": 0, "x": 0.0, "y": 0.0},
                    {"sequenceNumber": 1, "x": 3.0, "y": 0.0},
                    {"sequenceNumber": 2, "x": 6.0, "y": 0.0},
                    {"sequenceNumber": 3, "x": 9.0, "y": 0.0}
                  ]
                },
                {
                  "testId": "TC_006",
                  "roadPoints": [
                    {"sequenceNumber": 0, "x": 0.0, "y": 0.0},
                    {"sequenceNumber": 1, "x": 5.0, "y": 0.0},
                    {"sequenceNumber": 2, "x": 8.0, "y": 3.0}
                  ]
                },
                {
                  "testId": "TC_007",
                  "roadPoints": [
                    {"sequenceNumber": 0, "x": 0.0, "y": 0.0},
                    {"sequenceNumber": 1, "x": 5.0, "y": 0.0},
                    {"sequenceNumber": 2, "x": 5.0, "y": 5.0},
                    {"sequenceNumber": 3, "x": 5.0, "y": 10.0},
                    {"sequenceNumber": 4, "x": 10.0, "y": 10.0}
                  ]
                },
                {
                  "testId": "TC_008",
                  "roadPoints": [
                    {"sequenceNumber": 0, "x": 0.0, "y": 0.0},
                    {"sequenceNumber": 1, "x": 3.0, "y": 1.0},
                    {"sequenceNumber": 2, "x": 6.0, "y": 2.0},
                    {"sequenceNumber": 3, "x": 9.0, "y": 2.0},
                    {"sequenceNumber": 4, "x": 12.0, "y": 1.0},
                    {"sequenceNumber": 5, "x": 15.0, "y": 0.0}
                  ]
                },
                {
                  "testId": "TC_009",
                  "roadPoints": [
                    {"sequenceNumber": 0, "x": 0.0, "y": 0.0},
                    {"sequenceNumber": 1, "x": 5.0, "y": 0.0},
                    {"sequenceNumber": 2, "x": 3.0, "y": 4.0},
                    {"sequenceNumber": 3, "x": 8.0, "y": 4.0}
                  ]
                },
                {
                  "testId": "TC_010",
                  "roadPoints": [
                    {"sequenceNumber": 0, "x": 0.0, "y": 0.0},
                    {"sequenceNumber": 1, "x": 4.0, "y": 1.0},
                    {"sequenceNumber": 2, "x": 8.0, "y": 3.0}
                  ]
                }
              ]
            }]
        }
    }


# =============================================================================
#   Response - Endpoint 1 Upload
# =============================================================================
class UploadTestSuiteResponse(BaseModel):
    """Response body for a successful upload."""

    testSuiteId: str
    testCount: int
    createdAt: datetime
    message: str = "Test suite uploaded successfully."

# =============================================================================
#   Response - Endpoint 2 Prioritize (GET — no request body needed)
# =============================================================================
class PrioritizeResponse(BaseModel):
    """Response body matching the assignment specification."""

    testSuiteId: str
    strategy: str
    orderedTests: List[str]


# =============================================================================
#   Request - Endpoint 3 Evaluate (POST — creates evaluation report)
# =============================================================================
class EvaluateRequest(BaseModel):
    """Request body for the evaluate endpoint.

    Supports two evaluation modes:
    - Base mode:   omit budget — all tests execute fully (unless OOB).
    - Budget mode: provide budget — execution stops when budget is exhausted
        by the number of road points executed (requested by assignment).
    """

    testSuiteId: str = Field(
        pattern=r"^suite_\d{2}$",
        description="Suite ID in format suite_XX",
    )
    strategy: str = Field(
        min_length=1,
        description="Prioritization strategy name.",
    )
    budget: int | None = Field(
        default=None,
        gt=0,
        description="Max road points to execute. Non needed for base mode.",
    )


# =============================================================================
#   Response - Endpoint 3 Evaluate
# =============================================================================
class EvaluateResponse(BaseModel):
    """Evaluation report field as assigned by design requirements;
        Added evaluationID for completeness."""

    evaluationId: int
    testSuiteId: str
    strategy: str
    failuresDetected: int
    executionCost: int
    score: float
