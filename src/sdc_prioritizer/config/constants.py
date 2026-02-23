from pathlib import Path

# =============================================================================
#   Project-level path constants
# =============================================================================
# __file__ is src/sdc_prioritizer/config/constants.py
# parents[3] → project root (sdc-prioritizer/)
PROJECT_ROOT: Path = Path(__file__).parents[3]
CONFIG_DIR:   Path = PROJECT_ROOT / "config"
LOGS_DIR:     Path = PROJECT_ROOT / "logs"
