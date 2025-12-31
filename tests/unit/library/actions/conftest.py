"""Shared test fixtures for validation actions tests.

Provides factory functions for creating mock validation and fix results.
"""

from __future__ import annotations

from typing import Any


def create_validation_result(
    success: bool,
    stages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a mock validation result for testing.

    Args:
        success: Whether validation passed
        stages: Optional list of stage results

    Returns:
        Validation result dict
    """
    if stages is None:
        stages = [
            {
                "stage": "lint",
                "success": success,
                "output": "" if success else "E501: line too long",
                "duration_ms": 100,
                "error": None if success else "E501: line too long",
            }
        ]
    return {
        "success": success,
        "stages": stages,
        "total_duration_ms": 100,
    }


def create_fix_result(
    success: bool,
    changes_made: str = "Fix applied",
    error: str | None = None,
) -> dict[str, Any]:
    """Create a mock fix result for testing.

    Args:
        success: Whether fix succeeded
        changes_made: Description of changes if successful
        error: Error message if failed

    Returns:
        Fix result dict
    """
    if success:
        return {
            "success": True,
            "changes_made": changes_made,
        }
    return {
        "success": False,
        "error": error or "Fix failed",
    }
