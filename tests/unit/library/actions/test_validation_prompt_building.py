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

    def test_build_fix_prompt_includes_default_commands(self) -> None:
        """Prompt includes default validation commands when none provided."""
        result = create_validation_result(success=False)
        prompt = _build_fix_prompt(result, ["lint", "test"], attempt_number=1)

        assert "Validation Commands" in prompt
        assert "ruff check" in prompt
        assert "pytest" in prompt
        assert "NOT npm/node" in prompt

    def test_build_fix_prompt_includes_custom_commands(self) -> None:
        """Prompt includes custom validation commands when provided."""
        custom_commands = {
            "lint": ("pylint", "src/"),
            "test": ("python", "-m", "pytest", "-v"),
        }
        result = create_validation_result(success=False)
        prompt = _build_fix_prompt(
            result,
            ["lint", "test"],
            attempt_number=1,
            validation_commands=custom_commands,
        )

        assert "pylint src/" in prompt
        assert "python -m pytest -v" in prompt
        # Should NOT include default commands
        assert "ruff check" not in prompt

    def test_build_fix_prompt_commands_from_validation_result(self) -> None:
        """Prompt uses commands embedded in validation result via _validation_commands."""
        from maverick.library.actions.validation import DEFAULT_STAGE_COMMANDS

        result = create_validation_result(success=False)
        # When no explicit commands passed, defaults are used
        prompt = _build_fix_prompt(result, ["format"], attempt_number=1)

        expected_cmd = " ".join(DEFAULT_STAGE_COMMANDS["format"])
        assert expected_cmd in prompt
