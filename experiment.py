"""
Experiment runner for the SDC Test Prioritizer service.

Loads competition test data from JSON, transforms it into the API format,
uploads test suites, evaluates them with all available strategies,
and exports the evaluation history as CSV.

Usage:
    python experiment.py                              # base mode
    python experiment.py --budget 100                  # budget mode
    python experiment.py --data path/to/data.json      # custom data file

Assumes the service is running via docker-compose at http://localhost:8000.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any

import requests

# =============================================================================
#   Configuration
# =============================================================================
BASE_URL = "http://localhost:8000"
DEFAULT_DATA_FILE = "sdc-test-data.json"
TESTS_PER_SUITE = 10
STRATEGIES = ["longest-first", "euclidean-outlier-first", "mahalanobis-outlier-first", "less-safe-first"]

# =============================================================================
#   Logger
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("experiment")


# =============================================================================
#   Data Transformation
# =============================================================================
def transform_to_suites(raw_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Transform competition MongoDB documents into API-format suites.

    Groups test cases into suites of TESTS_PER_SUITE, assigns
    sequential suite_XX and TC_XXX identifiers, and adds
    sequenceNumber to road points.

    Args:
        raw_data: List of competition test case documents.

    Returns:
        List of suite payloads ready for the upload endpoint.
    """
    suites = []
    suite_index = 0
    tests_buffer = []

    for i, doc in enumerate(raw_data):
        # Build road points with sequenceNumber
        road_points = [
            {"sequenceNumber": seq, "x": rp["x"], "y": rp["y"]}
            for seq, rp in enumerate(doc["road_points"])
        ]

        # Assign test ID within current suite
        test_index = len(tests_buffer)
        test_case = {
            "testId": f"TC_{test_index:03d}",
            "roadPoints": road_points,
        }
        tests_buffer.append(test_case)

        # Flush suite when buffer is full or data is exhausted
        if len(tests_buffer) == TESTS_PER_SUITE or i == len(raw_data) - 1:
            suite = {
                "testSuiteId": f"suite_{suite_index:02d}",
                "tests": tests_buffer,
            }
            suites.append(suite)
            tests_buffer = []
            suite_index += 1

    logger.info(
        "Transformed %d test cases into %d suites (%d tests/suite).",
        len(raw_data), len(suites), TESTS_PER_SUITE,
    )
    return suites


# =============================================================================
#   API Calls
# =============================================================================
def upload_suite(suite: Dict[str, Any]) -> bool:
    """Upload a single test suite. Returns True on success."""
    suite_id = suite["testSuiteId"]
    try:
        resp = requests.post(f"{BASE_URL}/v1/test-suite/", json=suite, timeout=30)
        if resp.status_code == 201:
            logger.info("Uploaded %s (%d tests).", suite_id, len(suite["tests"]))
            return True
        elif resp.status_code == 409:
            logger.warning("Suite %s already exists, skipping upload.", suite_id)
            return True  # already there, can still evaluate
        else:
            logger.error("Upload %s failed: %d – %s", suite_id, resp.status_code, resp.text)
            return False
    except requests.RequestException as exc:
        logger.error("Upload %s connection error: %s", suite_id, exc)
        return False


def evaluate_suite(suite_id: str, strategy: str, budget: int | None = None) -> dict | None:
    """Evaluate a suite with a given strategy. Returns True on success."""
    payload = {"testSuiteId": suite_id, "strategy": strategy}
    if budget is not None:
        payload["budget"] = budget

    try:
        resp = requests.post(f"{BASE_URL}/v1/test-suite/evaluation", json=payload, timeout=60)
        if resp.status_code == 201:
            report = resp.json()
            logger.info(
                "Evaluated %s | %s → failures=%d cost=%d score=%.4f",
                suite_id, strategy,
                report["failuresDetected"],
                report["executionCost"],
                report["score"],
            )
            return report
        else:
            logger.error(
                "Evaluate %s/%s failed: %d – %s",
                suite_id, strategy, resp.status_code, resp.text,
            )
            return None
    except requests.RequestException as exc:
        logger.error("Evaluate %s/%s connection error: %s", suite_id, strategy, exc)
        return None


def export_history(data_name: str, strategies: List[str]) -> None:
    """Download evaluation history CSV, split by strategy, save to experiments/."""
    try:
        resp = requests.get(f"{BASE_URL}/v1/history/", timeout=30)
        if resp.status_code != 200:
            logger.error("Export failed: %d – %s", resp.status_code, resp.text)
            return

        # Create output folder
        output_dir = Path("experiments")
        output_dir.mkdir(exist_ok=True)

        # Parse CSV
        lines = resp.text.strip().split("\n")
        header = lines[0]
        rows = lines[1:]

        # strategy is the 3rd column (index 2)
        for strategy in strategies:
            filtered = [row for row in rows if row.split(",")[2] == strategy]
            filename = f"evaluation_report_{data_name}_{strategy}.csv"
            filepath = output_dir / filename

            filepath.write_text(header + "\n" + "\n".join(filtered) + "\n")
            logger.info("Saved %d records to %s", len(filtered), filepath)

    except requests.RequestException as exc:
        logger.error("Export connection error: %s", exc)


# =============================================================================
#   Main
# =============================================================================
def main():
    parser = argparse.ArgumentParser(description="SDC Prioritizer Experiment Runner")
    parser.add_argument("--data", default=DEFAULT_DATA_FILE, help="Path to JSON test data.")
    parser.add_argument("--budget", type=int, default=None, help="Execution budget (omit for base mode).")
    args = parser.parse_args()

    mode = "budget" if args.budget else "base"
    logger.info("=== Experiment started (mode=%s) ===", mode)

    # 1. Load data
    data_path = Path(args.data)
    if not data_path.exists():
        logger.error("Data file not found: %s", data_path)
        sys.exit(1)

    with open(data_path) as f:
        raw_data = json.load(f)
    logger.info("Loaded %d test cases from %s.", len(raw_data), data_path)

    # 2. Transform into suites
    suites = transform_to_suites(raw_data)

    # 3. Upload all suites
    logger.info("--- Uploading %d suites ---", len(suites))
    upload_ok = 0
    for suite in suites:
        if upload_suite(suite):
            upload_ok += 1
    logger.info("Uploaded %d/%d suites.", upload_ok, len(suites))

    # 4. Evaluate all suites with all strategies
    logger.info("--- Evaluating with strategies: %s ---", STRATEGIES)
    eval_ok = 0
    eval_total = 0
    scores = {s: [] for s in STRATEGIES}

    for suite in suites:
        suite_id = suite["testSuiteId"]
        for strategy in STRATEGIES:
            eval_total += 1
            resp = evaluate_suite(suite_id, strategy, args.budget)
            if resp:
                eval_ok += 1
                scores[strategy].append(resp["score"])
    logger.info("Evaluated %d/%d suite-strategy combinations.", eval_ok, eval_total)

    # Print average scores
    print("\n" + "=" * 60)
    print("  EXPERIMENT RESULTS")
    print("=" * 60)
    for strategy in STRATEGIES:
        if scores[strategy]:
            avg = sum(scores[strategy]) / len(scores[strategy])
            print(f"  {strategy:<25s}  avg APFD = {avg:.4f}  (n={len(scores[strategy])})")
        else:
            print(f"  {strategy:<25s}  no results")
    print("=" * 60 + "\n")

    # 5. Export history
    logger.info("--- Exporting history ---")
    data_name = Path(args.data).stem  # "sdc-test-data"
    export_history(data_name, STRATEGIES)

    logger.info("=== Experiment complete ===")


if __name__ == "__main__":
    main()
