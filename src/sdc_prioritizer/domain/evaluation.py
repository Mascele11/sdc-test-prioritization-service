"""
Evaluation logic for simulated test execution.

Contains the mock failure function and metric computations.
Decoupled from strategies and transport. Designed to
be compliant with the competition gRPC evaluator.
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
    Determines if a test case has failed based on the angular displacement between consecutive road points.

    This function evaluates a series of road points in a test case to check for excessive angular deviations
    that may indicate a failure. The analysis stops as soon as a failure is detected or when the evaluation
    reaches the predefined maximum point limit (as requested by assignment).

    Args:
        tc (TestCaseData): A test case containing a list of road points to analyze. Each point is represented
            as a tuple containing x and y coordinates (e.g., (x, y)).
        max_points (int | None, optional): The maximum number of points to evaluate. If None, all points in
            the test case are analyzed. Defaults to None.

    Returns:
        tuple[bool, int]: A tuple where the first element indicates whether a failure was detected (True if
        failure occurred, False otherwise) and the second element contains the number of points evaluated
        before the function returned.
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
#   APFD Metric - Metric for evaluating Prioritizers
# =============================================================================
def compute_apfd(
    ordered_ids: List[str],
    failure_map: Dict[str, bool],
) -> float:
    """
    Computes the Average Percentage of Faults Detected (APFD) for an ordered list of test
    cases and a failure mapping.

    APFD definition retrieved in paper (ref: https://doi.org/10.48550/arXiv.2504.10313)
        APFD = 1 - (sum of fault positions) / (n * m) + 1 / (2n)

    The score has to be maximized (earlier scores have fewer ration values).

    Args:
        ordered_ids (List[str]): A list of test case identifiers in the order of execution.
        failure_map (Dict[str, bool]): A dictionary mapping each test case identifier to
            a boolean value indicating if the test case detects a fault (True for fault-detecting,
            False otherwise).

    Returns:
        float: The computed APFD value. It ranges from 0 to 1, where higher values indicate
            better fault detection performance.
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