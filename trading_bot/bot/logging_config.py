"""
Centralized logging configuration.

Design goals:
- One log file capturing every API request/response/error (for audit + debugging).
- A quieter console stream so the CLI stays readable.
- No secrets (API key/secret) ever written to the log file.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
LOG_FILE = os.path.join(LOG_DIR, "trading_bot.log")

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Rotate at 2MB, keep 5 backups. A CLI trading bot that runs repeatedly
# over weeks would otherwise grow an unbounded log file.
MAX_BYTES = 2 * 1024 * 1024
BACKUP_COUNT = 5


def setup_logging(log_file: str = LOG_FILE, console_level: int = logging.INFO) -> logging.Logger:
    """
    Configure and return the 'trading_bot' logger.

    - File handler: DEBUG level, full detail, rotates at 2MB (5 backups kept)
    - Console handler: INFO level by default, concise, for interactive use
    """
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    logger = logging.getLogger("trading_bot")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Avoid duplicate handlers if setup_logging() is called more than once
    if logger.handlers:
        return logger

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
