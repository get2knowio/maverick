"""Structured logging configuration for Maverick.

This module provides structlog-based logging with:
- JSON output for production (when env var MAVERICK_LOG_FORMAT=json)
- Pretty console output for development (default)
- Automatic context binding (workflow_id, step_name, agent_name)

Usage:
    from maverick.logging import get_logger, configure_logging

    # Configure logging once at application startup
    configure_logging()

    # Get a logger and bind context
    log = get_logger()
    log = log.bind(workflow_id="fly-123")
    log.info("step_started", step_name="implementation")
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

import structlog
from structlog.types import Processor

__all__ = [
    "get_logger",
    "configure_logging",
    "bind_context",
    "clear_context",
]

# Environment variable for log format
LOG_FORMAT_ENV_VAR = "MAVERICK_LOG_FORMAT"

# Environment variable for log level
LOG_LEVEL_ENV_VAR = "MAVERICK_LOG_LEVEL"

# Default log level
DEFAULT_LOG_LEVEL = "INFO"


def _get_log_level() -> int:
    """Get the log level from environment or default.

    Returns:
        Logging level constant (e.g., logging.INFO).
    """
    level_name = os.environ.get(LOG_LEVEL_ENV_VAR, DEFAULT_LOG_LEVEL).upper()
    return getattr(logging, level_name, logging.INFO)


def _is_json_output() -> bool:
    """Check if JSON output is enabled.

    Returns:
        True if MAVERICK_LOG_FORMAT=json, False otherwise.
    """
    return os.environ.get(LOG_FORMAT_ENV_VAR, "").lower() == "json"


def _get_shared_processors() -> list[Processor]:
    """Get processors shared between stdlib and structlog.

    Returns:
        List of common processors for log processing.
    """
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]


def _get_development_processors() -> list[Processor]:
    """Get processors for development (pretty console output).

    Returns:
        List of processors for development environment.
    """
    return [
        *_get_shared_processors(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.plain_traceback,
        ),
    ]


def _get_production_processors() -> list[Processor]:
    """Get processors for production (JSON output).

    Returns:
        List of processors for production environment.
    """
    return [
        *_get_shared_processors(),
        structlog.processors.dict_tracebacks,
        structlog.processors.JSONRenderer(),
    ]


def configure_logging(
    *,
    force_json: bool = False,
    level: int | None = None,
) -> None:
    """Configure structlog for the application.

    This should be called once at application startup. Subsequent calls
    will reconfigure logging.

    Args:
        force_json: Force JSON output regardless of environment variable.
        level: Override log level. If None, reads from MAVERICK_LOG_LEVEL env var.

    Example:
        # Default configuration (reads from environment)
        configure_logging()

        # Force JSON output for testing
        configure_logging(force_json=True)

        # Set specific log level
        configure_logging(level=logging.DEBUG)
    """
    use_json = force_json or _is_json_output()
    log_level = level if level is not None else _get_log_level()

    # Choose processors based on output format
    if use_json:
        processors = _get_production_processors()
    else:
        processors = _get_development_processors()

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to work with structlog
    # This ensures that existing stdlib loggers are also processed by structlog
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add a stream handler for output
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(log_level)

    # Use structlog's formatter for stdlib logging
    if use_json:
        # For JSON output, use structlog's ProcessorFormatter
        handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.JSONRenderer(),
                ],
                foreign_pre_chain=_get_shared_processors(),
            )
        )
    else:
        # For console output, use structlog's ConsoleRenderer
        handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.dev.ConsoleRenderer(colors=True),
                ],
                foreign_pre_chain=_get_shared_processors(),
            )
        )

    root_logger.addHandler(handler)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger instance.

    This is the recommended way to get a logger in Maverick. The returned
    logger supports context binding for structured logging.

    Args:
        name: Logger name. If None, uses the caller's module name.

    Returns:
        A bound structlog logger.

    Example:
        log = get_logger(__name__)
        log.info("processing_started", items=10)

        # Bind context for subsequent calls
        log = log.bind(workflow_id="fly-123")
        log.info("step_started", step_name="init")
    """
    log: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return log


def bind_context(**context: Any) -> None:
    """Bind context variables that will be included in all log messages.

    This uses structlog's contextvars to propagate context across async
    boundaries. Useful for setting workflow-level context.

    Args:
        **context: Key-value pairs to bind to log context.

    Example:
        bind_context(workflow_id="fly-123", run_id="abc-456")
        log.info("event")  # Includes workflow_id and run_id
    """
    structlog.contextvars.bind_contextvars(**context)


def clear_context() -> None:
    """Clear all bound context variables.

    Call this at the end of a workflow or request to prevent
    context leakage.

    Example:
        try:
            bind_context(workflow_id="fly-123")
            await run_workflow()
        finally:
            clear_context()
    """
    structlog.contextvars.clear_contextvars()
