from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional


_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure_logging(
    name: str,
    level: str | int = "INFO",
    log_file: Optional[Path] = None
) -> logging.Logger:
    """
    Configure the logging for the ETL pipeline.

    Call once from a script or CLI; library code never configures handlers itself.

    Args:
        name (str): The name of the logger.
        level (str | int): The logging level. "INFO" = one line per step (triples in/out, main counters), "DEBUG" = the full breakdowns of each step. Defaults to "INFO".
        log_file (Optional[Path]): The path to the log file. If None, no file logging is configured.
    
    Returns:
        logging.Logger: The configured logger.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter(_FORMAT)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger