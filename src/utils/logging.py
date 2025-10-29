"""Structured logging utilities for workflow and activity logging."""

import json
import logging
from datetime import UTC, datetime
from typing import Any


try:
    from temporalio import workflow
    WORKFLOW_AVAILABLE = True
except ImportError:
    WORKFLOW_AVAILABLE = False


class SafeJSONEncoder(json.JSONEncoder):
    """JSON encoder that safely handles non-serializable types.

    Converts common non-serializable types to safe representations:
    - datetime: ISO format string
    - sets/frozensets: lists
    - bytes: UTF-8 string (with errors='replace')
    - Other objects: str() representation
    """

    def default(self, obj: Any) -> Any:
        """Convert non-serializable objects to serializable forms.

        Args:
            obj: Object to serialize

        Returns:
            Serializable representation of the object
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, (set, frozenset)):
            return list(obj)
        elif isinstance(obj, bytes):
            return obj.decode('utf-8', errors='replace')
        else:
            # Fallback: convert to string
            return str(obj)


class StructuredLogger:
    """Logger that emits structured JSON logs.

    Provides consistent structured logging across workflows and activities.
    """

    def __init__(self, name: str, logger: logging.Logger | None = None):
        """Initialize structured logger.

        Args:
            name: Logger name (typically module or component name)
            logger: Optional underlying logger (creates one if None)
        """
        self.name = name
        self.logger = logger or logging.getLogger(name)

    def _log_structured(
        self,
        level: int,
        event: str,
        **fields: Any
    ) -> None:
        """Log a structured message.

        Args:
            level: Logging level (e.g., logging.INFO)
            event: Event name/type
            **fields: Additional structured fields
        """
        log_entry = {
            "logger": self.name,
            "event": event,
            **fields
        }

        # Get timestamp in a Temporal-safe way
        # In workflow context, use workflow.now() which is deterministic
        # In activity/worker context, use datetime.now() which is allowed
        if WORKFLOW_AVAILABLE and workflow.in_workflow():
            # Use workflow.now() for deterministic time in workflows
            log_entry["timestamp"] = workflow.now().isoformat()
        else:
            # Use datetime.now() in activities and workers
            log_entry["timestamp"] = datetime.now(UTC).isoformat()

        # Emit as JSON string with safe serialization
        try:
            json_output = json.dumps(log_entry, cls=SafeJSONEncoder)
        except Exception as e:
            # Fallback: emit minimal log with serialization error
            # This ensures we never crash due to serialization issues
            fallback_entry = {
                "logger": self.name,
                "event": event,
                "timestamp": log_entry.get("timestamp", datetime.now(UTC).isoformat()),
                "serialization_error": str(e)
            }
            try:
                json_output = json.dumps(fallback_entry)
            except Exception:
                # Last resort: emit plain string
                json_output = f'{{"logger":"{self.name}","event":"{event}","error":"serialization_failed"}}'

        self.logger.log(level, json_output)

    def info(self, event: str, **fields: Any) -> None:
        """Log info-level structured message.

        Args:
            event: Event name/type
            **fields: Additional structured fields
        """
        self._log_structured(logging.INFO, event, **fields)

    def warning(self, event: str, **fields: Any) -> None:
        """Log warning-level structured message.

        Args:
            event: Event name/type
            **fields: Additional structured fields
        """
        self._log_structured(logging.WARNING, event, **fields)

    def error(self, event: str, **fields: Any) -> None:
        """Log error-level structured message.

        Args:
            event: Event name/type
            **fields: Additional structured fields
        """
        self._log_structured(logging.ERROR, event, **fields)

    def debug(self, event: str, **fields: Any) -> None:
        """Log debug-level structured message.

        Args:
            event: Event name/type
            **fields: Additional structured fields
        """
        self._log_structured(logging.DEBUG, event, **fields)


def get_structured_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance.

    Args:
        name: Logger name (typically module or component name)

    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(name)
