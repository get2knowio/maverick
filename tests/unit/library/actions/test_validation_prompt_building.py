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
            stages=[
                {"stage": "lint", "success": False, "error": "E501: line too long"},
                {"stage": "test", "success": True, "error": None},
            ],
        )
        prompt = _build_fix_prompt(result, ["lint", "test"], attempt_number=1)

        assert "lint" in prompt
        assert "E501: line too long" in prompt
        # Passing stages shouldn't have errors in prompt
        assert "test:" not in prompt or "success" not in prompt.lower()

    def test_build_fix_prompt_handles_empty_stages(self) -> None:
        """Handles validation result with no stage errors."""
        result = {"success": False, "stages": []}
        prompt = _build_fix_prompt(result, ["lint"], attempt_number=1)

        assert "No specific errors provided" in prompt
