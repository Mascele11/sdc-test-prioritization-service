import logging
import sys
from logging import Logger
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


# =============================================================================
#   setup_logging
# =============================================================================
def setup_logging(
    log_dir: Path,
    log_level: str,
    main_function_name: str,
    file_log_level: str,
    file_log_file_size_mb: int,
    file_log_max_files: int,
) -> None:
    """Configure root logger with a console handler and a rotating file handler.

    Args:
        log_dir: Directory where log files will be written.
        log_level: Console handler log level (e.g. "INFO").
        main_function_name: Used as the log file stem.
        file_log_level: File handler log level (e.g. "DEBUG").
        file_log_file_size_mb: Maximum size of each log file in MB.
        file_log_max_files: Number of rotated log files to keep.
    """
    logger: Logger = logging.getLogger()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging._nameToLevel[log_level])
    console_handler.setFormatter(formatter)

    # Rotating file handler
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / f"{main_function_name}.log",
        maxBytes=1024 * 1024 * file_log_file_size_mb,
        backupCount=file_log_max_files,
    )
    file_handler.setLevel(logging._nameToLevel[file_log_level])
    file_handler.setFormatter(formatter)

    logger.handlers = [console_handler, file_handler]
    logger.setLevel(logging.NOTSET)

    def _handle_uncaught(exc_type: Any, exc_value: Any, exc_traceback: Any) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = _handle_uncaught
