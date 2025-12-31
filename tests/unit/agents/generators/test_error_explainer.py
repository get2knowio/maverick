"""Unit tests for ErrorExplainer generator."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from maverick.agents.generators.base import MAX_SNIPPET_SIZE
from maverick.agents.generators.error_explainer import ErrorExplainer
from maverick.exceptions import GeneratorError


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


class TestErrorExplainerGenerate:
    """Tests for ErrorExplainer.generate()."""

    @pytest.mark.asyncio
    async def test_type_error_explanation_with_source_context(self) -> None:
        """Test type error explanation with source context."""
        explainer = ErrorExplainer()

        context = {
            "error_output": (
                "TypeError: unsupported operand type(s) for +: 'int' and 'str'"
            ),
            "source_context": (
                "def add(a: int, b: int) -> int:\n"
                '    return a + b\n\nresult = add(5, "10")'
            ),
            "error_type": "type",
        }

        # Mock the _query method to return a structured explanation
        mock_explanation = (
            "**What happened**: You tried to add an integer and a string.\n"
            "**Why this occurred**: Python cannot add different types.\n"
            "**How to fix**: Convert the string to an integer.\n"
            "**Code example**: result = add(5, 10)"
        )

        with patch.object(
            explainer, "_query", new_callable=AsyncMock, return_value=mock_explanation
        ):
            result = await explainer.generate(context)

        assert "What happened" in result
        assert "Why this occurred" in result
        assert "How to fix" in result

    @pytest.mark.asyncio
    async def test_test_failure_explanation(self) -> None:
        """Test test failure explanation."""
        explainer = ErrorExplainer()

        context = {
            "error_output": (
                "AssertionError: assert 5 == 6\n"
                "  File test_math.py, line 10, in test_addition\n"
                "    assert add(2, 3) == 6"
            ),
            "error_type": "test",
        }

        mock_explanation = (
            "**What happened**: The assertion failed because "
            "add(2, 3) returned 5, not 6.\n"
            "**Why this occurred**: The expected value in the test "
            "is incorrect.\n"
            "**How to fix**: Change the assertion to "
            "assert add(2, 3) == 5."
        )

        with patch.object(
            explainer, "_query", new_callable=AsyncMock, return_value=mock_explanation
        ):
            result = await explainer.generate(context)

        assert "assertion" in result.lower() or "test" in result.lower()

    @pytest.mark.asyncio
    async def test_lint_error_explanation(self) -> None:
        """Test lint error explanation."""
        explainer = ErrorExplainer()

        context = {
            "error_output": (
                "src/example.py:15:1: E302 expected 2 blank lines, found 1"
            ),
            "error_type": "lint",
        }

        mock_explanation = (
            "**What happened**: PEP 8 style violation - "
            "insufficient blank lines.\n"
            "**Why this occurred**: Python style guide requires 2 "
            "blank lines before top-level definitions.\n"
            "**How to fix**: Add one more blank line before line 15."
        )

        with patch.object(
            explainer, "_query", new_callable=AsyncMock, return_value=mock_explanation
        ):
            result = await explainer.generate(context)

        assert "blank line" in result.lower() or "pep" in result.lower()

    @pytest.mark.asyncio
    async def test_error_without_source_context_still_produces_explanation(
        self,
    ) -> None:
        """Test error without source context still produces explanation."""
        explainer = ErrorExplainer()

        context = {
            "error_output": (
                "FileNotFoundError: [Errno 2] No such file or directory: 'data.txt'"
            )
        }

        mock_explanation = (
            "**What happened**: The program tried to access a file "
            "that doesn't exist.\n"
            "**Why this occurred**: The file 'data.txt' is not in "
            "the expected location.\n"
            "**How to fix**: Ensure the file exists or check the "
            "file path."
        )

        with patch.object(
            explainer, "_query", new_callable=AsyncMock, return_value=mock_explanation
        ):
            result = await explainer.generate(context)

        assert len(result) > 0
        assert "What happened" in result or "file" in result.lower()

    @pytest.mark.asyncio
    async def test_empty_error_output_raises_generator_error(self) -> None:
        """Test empty error_output raises GeneratorError."""
        explainer = ErrorExplainer()

        context = {"error_output": ""}

        with pytest.raises(GeneratorError) as exc_info:
            await explainer.generate(context)

        assert "error_output" in exc_info.value.message.lower()
        assert exc_info.value.generator_name == "error-explainer"

    @pytest.mark.asyncio
    async def test_missing_error_output_raises_generator_error(self) -> None:
        """Test missing error_output raises GeneratorError."""
        explainer = ErrorExplainer()

        context: dict[str, Any] = {}

        with pytest.raises(GeneratorError) as exc_info:
            await explainer.generate(context)

        assert "error_output" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_source_context_truncation_at_10kb_with_warning(self) -> None:
        """Test source_context truncation at 10KB with WARNING."""
        explainer = ErrorExplainer()

        large_source = "A" * (MAX_SNIPPET_SIZE + 1000)
        context = {
            "error_output": "SyntaxError: invalid syntax",
            "source_context": large_source,
        }

        mock_explanation = "**What happened**: Syntax error in code."

        with (
            patch.object(
                explainer,
                "_query",
                new_callable=AsyncMock,
                return_value=mock_explanation,
            ),
            patch("maverick.agents.generators.base.logger") as mock_logger,
        ):
            result = await explainer.generate(context)

            # Verify warning was logged
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "source_context" in str(call_args)

        # Verify result was still generated
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_prompt_includes_error_type_when_provided(self) -> None:
        """Test that the prompt includes error_type when provided."""
        explainer = ErrorExplainer()

        context = {
            "error_output": "Build failed: missing dependency",
            "error_type": "build",
        }

        mock_explanation = "**What happened**: Build dependency missing."

        # Capture the prompt passed to _query
        captured_prompt = None

        async def capture_query(prompt: str) -> str:
            nonlocal captured_prompt
            captured_prompt = prompt
            return mock_explanation

        with patch.object(
            explainer, "_query", new_callable=AsyncMock, side_effect=capture_query
        ):
            await explainer.generate(context)

        assert captured_prompt is not None
        assert "build" in captured_prompt.lower()

    @pytest.mark.asyncio
    async def test_prompt_includes_source_context_when_provided(self) -> None:
        """Test that the prompt includes source_context when provided."""
        explainer = ErrorExplainer()

        source_code = "def broken():\n    return undefined_var"
        context = {
            "error_output": "NameError: name 'undefined_var' is not defined",
            "source_context": source_code,
        }

        mock_explanation = "**What happened**: Variable is not defined."

        # Capture the prompt passed to _query
        captured_prompt = None

        async def capture_query(prompt: str) -> str:
            nonlocal captured_prompt
            captured_prompt = prompt
            return mock_explanation

        with patch.object(
            explainer, "_query", new_callable=AsyncMock, side_effect=capture_query
        ):
            await explainer.generate(context)

        assert captured_prompt is not None
        assert "undefined_var" in captured_prompt or source_code in captured_prompt

    @pytest.mark.asyncio
    async def test_handles_all_error_types(self) -> None:
        """Test that all error types are handled correctly."""
        explainer = ErrorExplainer()

        error_types = ["lint", "test", "build", "type"]
        mock_explanation = "**What happened**: Error occurred."

        for error_type in error_types:
            context = {
                "error_output": f"{error_type.capitalize()} error occurred",
                "error_type": error_type,
            }

            with patch.object(
                explainer,
                "_query",
                new_callable=AsyncMock,
                return_value=mock_explanation,
            ):
                result = await explainer.generate(context)
                assert len(result) > 0


class TestErrorExplainerEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_whitespace_only_error_output_raises_generator_error(self) -> None:
        """Test whitespace-only error_output raises GeneratorError."""
        explainer = ErrorExplainer()

        context = {"error_output": "   \n\t  "}

        with pytest.raises(GeneratorError) as exc_info:
            await explainer.generate(context)

        assert "error_output" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_api_error_propagates_as_generator_error(self) -> None:
        """Test that API errors are wrapped in GeneratorError."""
        explainer = ErrorExplainer()

        context = {
            "error_output": "RuntimeError: something went wrong",
        }

        # Simulate SDK error by raising GeneratorError from _query
        # (which is what the base class does when SDK fails)
        async def mock_query_error(prompt: str) -> str:
            raise GeneratorError(
                message="Query failed: API connection timeout",
                generator_name="error-explainer",
            )

        with patch.object(
            explainer, "_query", new_callable=AsyncMock, side_effect=mock_query_error
        ):
            with pytest.raises(GeneratorError) as exc_info:
                await explainer.generate(context)

            assert "API connection timeout" in exc_info.value.message
            assert exc_info.value.generator_name == "error-explainer"

    @pytest.mark.asyncio
    async def test_none_error_output_raises_generator_error(self) -> None:
        """Test None error_output raises GeneratorError."""
        explainer = ErrorExplainer()

        context = {"error_output": None}

        with pytest.raises(GeneratorError) as exc_info:
            await explainer.generate(context)

        assert "error_output" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_truncation_preserves_error_output(self) -> None:
        """Test that error_output is never truncated (only source_context)."""
        explainer = ErrorExplainer()

        large_error = "E" * (MAX_SNIPPET_SIZE + 1000)
        context = {
            "error_output": large_error,
        }

        mock_explanation = "**What happened**: Large error occurred."

        # Capture the prompt passed to _query
        captured_prompt = None

        async def capture_query(prompt: str) -> str:
            nonlocal captured_prompt
            captured_prompt = prompt
            return mock_explanation

        with patch.object(
            explainer, "_query", new_callable=AsyncMock, side_effect=capture_query
        ):
            await explainer.generate(context)

        # Error output should be in prompt without truncation
        assert captured_prompt is not None
        assert large_error in captured_prompt
