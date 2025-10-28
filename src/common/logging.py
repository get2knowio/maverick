"""Structured logging setup for maverick.

Provides consistent logging configuration across activities, workflows,
and CLI components with appropriate formatting and log levels.
"""

import logging
import sys
from typing import Optional


# Default log format with timestamp, level, logger name, and message
LOG_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: int = logging.INFO,
    format_string: Optional[str] = None,
    date_format: Optional[str] = None,
) -> None:
    """Configure the root logger with standard formatting.
    
    Args:
        level: Logging level (default: INFO)
        format_string: Custom log format (default: LOG_FORMAT)
        date_format: Custom date format (default: DATE_FORMAT)
    """
    logging.basicConfig(
        level=level,
        format=format_string or LOG_FORMAT,
        datefmt=date_format or DATE_FORMAT,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,  # Reconfigure if already configured
    )


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """Get a logger for the specified module.
    
    Args:
        name: Logger name (typically __name__ from calling module)
        level: Optional logging level override for this logger
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    if level is not None:
        logger.setLevel(level)
    return logger


# Initialize default logging configuration
setup_logging()
