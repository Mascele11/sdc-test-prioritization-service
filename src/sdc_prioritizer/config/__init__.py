from sdc_prioritizer.config.config import Config
from sdc_prioritizer.config.constants import CONFIG_DIR, LOGS_DIR, PROJECT_ROOT

# Load once at import time – mirrors the sample project pattern.
configuration: Config = Config.load_from_file(file_path=CONFIG_DIR / "config.yml")

__all__ = [
    "Config",
    "configuration",
    "PROJECT_ROOT",
    "CONFIG_DIR",
    "LOGS_DIR",
]
