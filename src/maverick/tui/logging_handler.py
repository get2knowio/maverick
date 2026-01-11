"""TUI logging handler for routing logs to the log panel.

This module provides a logging handler that routes structlog output
to the TUI's LogPanel widget when running in TUI mode.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from maverick.tui.app import MaverickApp

__all__ = ["TUILoggingHandler", "configure_tui_logging"]


class TUILoggingHandler(logging.Handler):
    """Logging handler that routes logs to the TUI log panel.

    This handler captures log records and sends them to the MaverickApp's
    log panel, providing real-time logging visibility in the TUI.
    """

    def __init__(self, app: MaverickApp) -> None:
        """Initialize the TUI logging handler.

        Args:
            app: The MaverickApp instance to route logs to.
        """
        super().__init__()
        self._app = app

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the TUI log panel.

        Args:
            record: The log record to emit.
        """
        try:
            # Map logging levels to TUI log levels
            level_map = {
                logging.DEBUG: "info",
                logging.INFO: "info",
                logging.WARNING: "warning",
                logging.ERROR: "error",
                logging.CRITICAL: "error",
            }
            level = level_map.get(record.levelno, "info")

            # Format the message
            message = self.format(record)

            # Get source from logger name
            source = record.name.split(".")[-1] if record.name else ""

            # Route to app's log panel
            self._app.add_log(message, level, source)

        except Exception:
            # Don't let logging errors crash the app
            self.handleError(record)


def configure_tui_logging(app: MaverickApp, level: int = logging.INFO) -> None:
    """Configure logging to route to the TUI.

    This replaces the default stderr handler with a TUI handler,
    routing all log output to the TUI's log panel.

    Args:
        app: The MaverickApp instance.
        level: Logging level to use.
    """
    import structlog

    # Get the root logger
    root_logger = logging.getLogger()

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Add TUI handler
    tui_handler = TUILoggingHandler(app)
    tui_handler.setLevel(level)

    # Use a simple formatter (the TUI handler adds timestamps itself)
    formatter = logging.Formatter("%(message)s")
    tui_handler.setFormatter(formatter)

    root_logger.addHandler(tui_handler)
    root_logger.setLevel(level)

    # Also configure structlog to use a simpler processor chain
    # that outputs plain text (the TUI handles coloring)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="%H:%M:%S"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.UnicodeDecoder(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(colors=False),  # No colors, TUI handles it
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,  # Allow reconfiguration
    )
