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
            stages=[
                {"stage": "lint", "success": False},
                {"stage": "test", "success": True},
                {"stage": "typecheck", "success": False},
            ],
        )
        summary = _summarize_errors(result)

        assert "2 stage(s)" in summary
        assert "lint" in summary
        assert "typecheck" in summary
        assert "test" not in summary

    def test_summarize_errors_handles_no_failures(self) -> None:
        """Handles case with no failed stages."""
        result = {"success": True, "stages": []}
        summary = _summarize_errors(result)

        assert "validation failures" in summary

    def test_summarize_errors_handles_missing_stage_name(self) -> None:
        """Handles stages without name field."""
        result = {
            "success": False,
            "stages": [{"success": False}],  # No "stage" field
        }
        summary = _summarize_errors(result)

        assert "1 stage(s)" in summary
        assert "unknown" in summary
