"""Shared test fixtures for validation actions tests.

Provides factory functions for creating mock validation and fix results.
"""

from __future__ import annotations

from typing import Any


def create_validation_result(
    success: bool,
    stage_results: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a mock validation result for testing.

    Args:
        success: Whether validation passed
        stage_results: Optional dict mapping stage name to result dict

    Returns:
        Validation result dict matching ValidationResult.to_dict() format
    """
    if stage_results is None:
        stage_results = {
            "lint": {
                "passed": success,
                "output": "" if success else "E501: line too long",
                "duration_ms": 100,
                "errors": [] if success else [{"message": "E501: line too long"}],
            }
        }
    return {
        "success": success,
        "stages": list(stage_results.keys()),
        "passed": success,
        "stage_results": stage_results,
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
