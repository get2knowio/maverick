"""Dry-run support actions for workflow execution."""

from __future__ import annotations

from typing import Any

from maverick.logging import get_logger

logger = get_logger(__name__)


def log_dry_run(
    operation: str,
    details: str,
) -> dict[str, Any]:
    """Log a planned operation in dry-run mode.

    Args:
        operation: Name of operation that would be performed
        details: Description of what would happen

    Returns:
        Dict with operation and details for logging
    """
    logger.info(f"[DRY-RUN] {operation}: {details}")
    return {
        "dry_run": True,
        "operation": operation,
        "details": details,
        "would_execute": True,
    }
