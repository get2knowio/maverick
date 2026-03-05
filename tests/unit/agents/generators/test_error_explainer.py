"""Unit tests for ErrorExplainer generator."""

from __future__ import annotations

from unittest.mock import patch

from maverick.agents.generators.base import MAX_SNIPPET_SIZE
from maverick.agents.generators.error_explainer import ErrorExplainer


class TestErrorExplainerConstruction:
    """Tests for ErrorExplainer construction."""

    def test_construction_with_defaults(self) -> None:
        """Test successful construction with default model."""
        explainer = ErrorExplainer()

        assert explainer.name == "error-explainer"
        assert "what happened" in explainer.system_prompt.lower()
        assert "why" in explainer.system_prompt.lower()
        assert "how to fix" in explainer.system_prompt.lower()

    def test_construction_with_custom_model(self) -> None:
        """Test construction with custom model."""
        explainer = ErrorExplainer(model="claude-opus-4-5-20250929")

        assert explainer.model == "claude-opus-4-5-20250929"


class TestErrorExplainerPromptBuilding:
    """Tests for ErrorExplainer.build_prompt() method."""

    def test_prompt_includes_error_output(self) -> None:
        """Test that error_output is included in the prompt."""
        explainer = ErrorExplainer()

        context = {
            "error_output": (
                "TypeError: unsupported operand type(s) for +: 'int' and 'str'"
            ),
        }

        prompt = explainer.build_prompt(context)

        assert "TypeError" in prompt
        assert "unsupported operand" in prompt

    def test_prompt_includes_error_type_when_provided(self) -> None:
        """Test that the prompt includes error_type when provided."""
        explainer = ErrorExplainer()

        context = {
            "error_output": "Build failed: missing dependency",
            "error_type": "build",
        }

        prompt = explainer.build_prompt(context)

        assert "build" in prompt.lower()

    def test_prompt_includes_source_context_when_provided(self) -> None:
        """Test that the prompt includes source_context when provided."""
        explainer = ErrorExplainer()

        source_code = "def broken():\n    return undefined_var"
        context = {
            "error_output": "NameError: name 'undefined_var' is not defined",
            "source_context": source_code,
        }

        prompt = explainer.build_prompt(context)

        assert "undefined_var" in prompt or source_code in prompt

    def test_prompt_without_source_context(self) -> None:
        """Test that prompt builds correctly without source_context."""
        explainer = ErrorExplainer()

        context = {
            "error_output": (
                "FileNotFoundError: [Errno 2] No such file or directory: 'data.txt'"
            ),
        }

        prompt = explainer.build_prompt(context)

        assert len(prompt) > 0
        assert "FileNotFoundError" in prompt

    def test_source_context_truncation_at_10kb_with_warning(self) -> None:
        """Test source_context truncation at 10KB with WARNING."""
        explainer = ErrorExplainer()

        large_source = "A" * (MAX_SNIPPET_SIZE + 1000)
        context = {
            "error_output": "SyntaxError: invalid syntax",
            "source_context": large_source,
        }

        with patch("maverick.agents.generators.base.logger") as mock_logger:
            prompt = explainer.build_prompt(context)

            # Verify warning was logged
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "source_context" in str(call_args)

        # Verify prompt was still built
        assert len(prompt) > 0

    def test_handles_all_error_types(self) -> None:
        """Test that all error types produce valid prompts."""
        explainer = ErrorExplainer()

        error_types = ["lint", "test", "build", "type"]

        for error_type in error_types:
            context = {
                "error_output": f"{error_type.capitalize()} error occurred",
                "error_type": error_type,
            }

            prompt = explainer.build_prompt(context)
            assert len(prompt) > 0
            assert error_type in prompt.lower()

    def test_invalid_error_type_is_ignored(self) -> None:
        """Test that invalid error_type is omitted from the prompt."""
        explainer = ErrorExplainer()

        context = {
            "error_output": "Some error",
            "error_type": "totally_invalid",
        }

        # Should not crash; invalid type is simply omitted
        prompt = explainer.build_prompt(context)
        assert "Some error" in prompt
        assert "totally_invalid" not in prompt

    def test_error_output_is_not_truncated(self) -> None:
        """Test that error_output is never truncated (only source_context is)."""
        explainer = ErrorExplainer()

        large_error = "E" * (MAX_SNIPPET_SIZE + 1000)
        context = {
            "error_output": large_error,
        }

        prompt = explainer.build_prompt(context)

        # Error output should be fully in the prompt
        assert large_error in prompt

    def test_empty_error_output_produces_prompt(self) -> None:
        """Test that empty error_output still produces a prompt (no raise)."""
        explainer = ErrorExplainer()

        context = {"error_output": ""}

        # build_prompt does not validate; it just builds
        prompt = explainer.build_prompt(context)
        assert isinstance(prompt, str)
