import sys
from pathlib import Path

from sdc_prioritizer.config import LOGS_DIR, configuration
from sdc_prioritizer.utils import setup_logging

# =============================================================================
#   Logging – Initialization from config
# =============================================================================
setup_logging(
    log_dir=LOGS_DIR,
    log_level=configuration.logging.log_level,
    main_function_name=Path(sys.argv[0]).stem, # sdc_prioritizer
    file_log_level=configuration.logging.file_log_level,
    file_log_file_size_mb=configuration.logging.file_log_file_size_mb,
    file_log_max_files=configuration.logging.file_log_max_files,
)

__all__ = ["configuration"]
