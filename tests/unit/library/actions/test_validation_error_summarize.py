"""Unit tests for _summarize_errors helper function.

Tests the error summarization logic for validation results.
"""

from __future__ import annotations

from maverick.library.actions.validation import _summarize_errors

from .conftest import create_validation_result


class TestSummarizeErrors:
    """Tests for _summarize_errors helper function."""

    def test_summarize_errors_lists_failed_stages(self) -> None:
        """Summarizes failed stages."""
        result = create_validation_result(
            success=False,
            stage_results={
                "lint": {"passed": False, "output": "error", "errors": []},
                "test": {"passed": True, "output": "", "errors": []},
                "typecheck": {"passed": False, "output": "error", "errors": []},
            },
        )
        summary = _summarize_errors(result)

        assert "2 stage(s)" in summary
        assert "lint" in summary
        assert "typecheck" in summary
        assert "test" not in summary

    def test_summarize_errors_handles_no_failures(self) -> None:
        """Handles case with no failed stages."""
        result = {"success": True, "stages": [], "stage_results": {}}
        summary = _summarize_errors(result)

        assert "validation failures" in summary

    def test_summarize_errors_handles_all_passing(self) -> None:
        """Handles case where all stages pass."""
        result = {
            "success": True,
            "stages": ["lint", "test"],
            "stage_results": {
                "lint": {"passed": True, "output": "", "errors": []},
                "test": {"passed": True, "output": "", "errors": []},
            },
        }
        summary = _summarize_errors(result)

        assert "validation failures" in summary
