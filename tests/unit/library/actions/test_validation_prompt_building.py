"""Unit tests for _build_fix_prompt helper function.

Tests the prompt building logic for fix attempts.
"""

from __future__ import annotations

from maverick.library.actions.validation import _build_fix_prompt

from .conftest import create_validation_result


class TestBuildFixPrompt:
    """Tests for _build_fix_prompt helper function."""

    def test_build_fix_prompt_includes_attempt_number(self) -> None:
        """Prompt includes current attempt number."""
        result = create_validation_result(success=False)
        prompt = _build_fix_prompt(result, ["lint"], attempt_number=2)

        assert "Attempt 2" in prompt

    def test_build_fix_prompt_includes_stages(self) -> None:
        """Prompt includes validation stages."""
        result = create_validation_result(success=False)
        prompt = _build_fix_prompt(
            result, ["lint", "test", "typecheck"], attempt_number=1
        )

        assert "lint" in prompt
        assert "test" in prompt
        assert "typecheck" in prompt

    def test_build_fix_prompt_includes_errors(self) -> None:
        """Prompt includes validation errors."""
        result = create_validation_result(
            success=False,
            stage_results={
                "lint": {
                    "passed": False,
                    "output": "",
                    "errors": [{"message": "E501: line too long"}],
                },
                "test": {"passed": True, "output": "", "errors": []},
            },
        )
        prompt = _build_fix_prompt(result, ["lint", "test"], attempt_number=1)

        assert "lint" in prompt
        assert "E501: line too long" in prompt
        # Passing stages shouldn't have errors in prompt
        assert "test:" not in prompt or "passed" not in prompt.lower()

    def test_build_fix_prompt_handles_empty_stages(self) -> None:
        """Handles validation result with no stage errors."""
        result = {"success": False, "stages": [], "stage_results": {}}
        prompt = _build_fix_prompt(result, ["lint"], attempt_number=1)

        assert "No specific errors provided" in prompt

    def test_build_fix_prompt_says_validation_reruns_automatically(self) -> None:
        """Prompt tells the fixer not to run validation commands itself."""
        result = create_validation_result(success=False)
        prompt = _build_fix_prompt(result, ["lint", "test"], attempt_number=1)

        assert (
            "re-run automatically" in prompt.lower() or "re-run automatically" in prompt
        )
        # Must NOT include shell commands or a "Validation Commands" section
        assert "Validation Commands" not in prompt
        assert "ruff check" not in prompt
        assert "pytest" not in prompt

    def test_build_fix_prompt_includes_raw_output_when_no_errors(self) -> None:
        """Falls back to raw output when errors list is empty but stage failed."""
        result = create_validation_result(
            success=False,
            stage_results={
                "test": {
                    "passed": False,
                    "output": "FAILED tests/test_foo.py::test_bar - AssertionError",
                    "errors": [],
                },
            },
        )
        prompt = _build_fix_prompt(result, ["test"], attempt_number=1)

        # Should contain the raw output since errors list was empty
        assert "FAILED tests/test_foo.py::test_bar" in prompt
