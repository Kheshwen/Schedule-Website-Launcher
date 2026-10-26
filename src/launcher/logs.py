"""Log file: %APPDATA%\\WebsiteLauncher\\launcher.log (rotated, so it never grows without limit).

Only the website's host name is ever logged, never the full URL, because paths and query strings
can contain private tokens.
"""
import logging
import os
from logging.handlers import RotatingFileHandler

from .paths import app_data_dir

LOG_NAME = "launcher"


def log_path() -> str:
    return os.path.join(app_data_dir(), "launcher.log")


def setup_logging(path: str | None = None) -> logging.Logger:
    """Starts file logging once. If the file can't be opened the app still runs, just without a log."""
    logger = logging.getLogger(LOG_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        path = path or log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=200_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)
    except OSError:
        logger.addHandler(logging.NullHandler())
    return logger
