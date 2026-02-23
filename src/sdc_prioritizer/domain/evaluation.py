"""Evaluation logic for simulated test execution.

Contains the mock failure function and metric computations.
Decoupled from strategies and transport — in the competition,
the evaluator handles this externally via gRPC.
"""

import math
import logging
from pathlib import Path
from typing import Dict, List

from sdc_prioritizer.domain.strategies import TestCaseData

# =============================================================================
#   Logger
# =============================================================================
logger = logging.getLogger(Path(__file__).stem)


# =============================================================================
#   Mock Failure Function
# =============================================================================
def mock_has_failed(tc: TestCaseData, max_points: int | None = None) -> (bool, int):
    """
    Deterministic mock failure based on max angle change.
    A test is stopped when the test fails, return condition satisfied.
    A test fails if the maximum angle change between consecutive
    road segments exceeds max angle — simulating OOB on sharp turns.
    max_angle custom value defined to have a baseline of failure on competition
    test dataset:
         max angles range from 1.36° to 6.66° @ sdc-test-data.json
    """
    if len(tc.road_points) < 3:
        # Assumption: at least 3 points per test are evaluated to perform mock
        return False, len(tc.road_points)

    max_angle = math.pi / 45 # 4 gradi
    pts = tc.road_points

    # Budget caps how many points we can evaluate:
    limit = len(pts) if max_points is None else min(len(pts), max_points)

    # For till happens failure, or reach the limits exit means limit or False
    for i in range(1, limit - 1):
        # Vectors computation of two consecutive displacements:
        dx1 = pts[i][0] - pts[i - 1][0]
        dy1 = pts[i][1] - pts[i - 1][1]
        dx2 = pts[i + 1][0] - pts[i][0]
        dy2 = pts[i + 1][1] - pts[i][1]

        # Vectors modules:
        len1 = math.sqrt(dx1 * dx1 + dy1 * dy1)
        len2 = math.sqrt(dx2 * dx2 + dy2 * dy2)

        # No displacement occurs:
        if len1 == 0 or len2 == 0:
            continue

        cross_product = dx1 * dx2 + dy1 * dy2
        cos_angle = cross_product / (len1 * len2)

        # Boundaries for acos compatibility:
        cos_angle = max(-1.0, min(1.0, cos_angle))
        angle = math.acos(cos_angle)

        # OBB return without computing all points
        if angle > max_angle:
            # returned true, stopping point + x0
            return True, i+1

    return False, limit



# =============================================================================
#   APFD Metric
# =============================================================================
def compute_apfd(
    ordered_ids: List[str],
    failure_map: Dict[str, bool],
) -> float:
    """
    APFD definition retrieved in paper (ref: https://doi.org/10.48550/arXiv.2504.10313)
        APFD = 1 - (sum of fault positions) / (n * m) + 1 / (2n)

    Score has to be maximized: earlier scores have fewer ration values.
    """
    n = len(ordered_ids)
    fault_positions = []

    # Append in order all the index of Faulty tests
    for i, test_id in enumerate(ordered_ids):
        if failure_map.get(test_id, False):
            fault_positions.append(i + 1)

    m = len(fault_positions)

    if n == 0 or m == 0:
        return 1.0

    return 1 - (sum(fault_positions) / (n * m)) + 1 / (2 * n)