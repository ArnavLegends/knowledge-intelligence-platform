"""Application-wide structured logging configuration."""

import logging
import sys

from app.core.config import Settings, settings

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"

_configured = False


def setup_logging(app_settings: Settings | None = None, *, force: bool = False) -> None:
    """Initialize root logging with a consistent structured format."""
    global _configured
    if _configured and not force:
        return

    active_settings = app_settings or settings
    level_name = active_settings.log_level.upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root_logger.addHandler(handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for application modules."""
    return logging.getLogger(name)
