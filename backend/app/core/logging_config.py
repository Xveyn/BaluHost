"""Logging configuration for BaluHost backend."""
import logging
import sys
from typing import Optional

from pythonjsonlogger import jsonlogger

from app.core.config import get_settings


def setup_logging() -> None:
    """
    Configure structured logging for the application.

    Uses JSON format for production (log aggregation) and human-readable format for development.
    Log level is configured via settings (LOG_LEVEL environment variable).
    """
    settings = get_settings()

    # Determine log level
    log_level_str = settings.log_level.upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Choose formatter based on environment
    if settings.log_format.lower() == "json" or settings.environment == "production":
        # JSON formatter for production (log aggregation friendly)
        formatter = jsonlogger.JsonFormatter(
            '%(asctime)s %(name)s %(levelname)s %(message)s',
            rename_fields={
                "levelname": "severity",
                "name": "logger",
                "asctime": "timestamp"
            },
            datefmt='%Y-%m-%dT%H:%M:%S'
        )
    else:
        # Human-readable formatter for development
        formatter = logging.Formatter(
            fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # Suppress plugp100 Tapo library internal errors (device queries still work despite these logs)
    logging.getLogger("plugp100").setLevel(logging.WARNING)

    # Log startup configuration
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured",
        extra={
            "log_level": log_level_str,
            "log_format": settings.log_format,
            "environment": settings.environment
        }
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)
