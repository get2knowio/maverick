"""Unit tests for CodeAnalyzer generator."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from maverick.agents.generators.base import DEFAULT_MODEL, MAX_SNIPPET_SIZE
from maverick.agents.generators.code_analyzer import CodeAnalyzer
from maverick.exceptions import GeneratorError


class TestCodeAnalyzerConstruction:
    """Tests for CodeAnalyzer construction."""

    def test_construction_with_defaults(self) -> None:
        """Test successful construction with default model."""
        analyzer = CodeAnalyzer()

        assert analyzer.name == "code-analyzer"
        assert analyzer.model == DEFAULT_MODEL
        # System prompt varies by analysis type, tested separately

    def test_construction_with_custom_model(self) -> None:
        """Test construction with custom model."""
        analyzer = CodeAnalyzer(model="claude-opus-4-5-20250929")

        assert analyzer.model == "claude-opus-4-5-20250929"


class TestCodeAnalyzerGenerate:
    """Tests for CodeAnalyzer.generate() method."""

    @pytest.mark.asyncio
    async def test_generate_with_explain_type_returns_explanation(
        self,
    ) -> None:
        """Test that analysis_type='explain' returns code explanation."""
        analyzer = CodeAnalyzer()

        # Mock the _query method to return a sample explanation
        mock_text_block = MagicMock()
        mock_text_block.text = (
            "This function calculates the factorial of a number using recursion."
        )
        type(mock_text_block).__name__ = "TextBlock"

        mock_message = MagicMock()
        mock_message.content = [mock_text_block]
        type(mock_message).__name__ = "AssistantMessage"

        async def mock_query_iter(*args: Any, **kwargs: Any) -> Any:
            yield mock_message

        with patch(
            "maverick.agents.generators.base.query",
            return_value=mock_query_iter(),
        ):
            result = await analyzer.generate(
                {
                    "code": (
                        "def factorial(n): return 1 if n == 0 else n * factorial(n-1)"
                    ),
                    "analysis_type": "explain",
                }
            )

        assert "factorial" in result.lower() or "recursion" in result.lower()

    @pytest.mark.asyncio
    async def test_generate_with_review_type_returns_issues(self) -> None:
        """Test that analysis_type='review' returns code review."""
        analyzer = CodeAnalyzer()

        # Mock the _query method to return a sample review
        mock_text_block = MagicMock()
        mock_text_block.text = (
            "Issues: 1. No input validation for negative numbers. "
            "2. No handling for large inputs."
        )
        type(mock_text_block).__name__ = "TextBlock"

        mock_message = MagicMock()
        mock_message.content = [mock_text_block]
        type(mock_message).__name__ = "AssistantMessage"

        async def mock_query_iter(*args: Any, **kwargs: Any) -> Any:
            yield mock_message

        with patch(
            "maverick.agents.generators.base.query",
            return_value=mock_query_iter(),
        ):
            result = await analyzer.generate(
                {
                    "code": (
                        "def factorial(n): return 1 if n == 0 else n * factorial(n-1)"
                    ),
                    "analysis_type": "review",
                }
            )

        assert "issue" in result.lower() or "validation" in result.lower()

    @pytest.mark.asyncio
    async def test_generate_with_summarize_type_returns_summary(self) -> None:
        """Test that analysis_type='summarize' returns brief summary."""
        analyzer = CodeAnalyzer()

        # Mock the _query method to return a sample summary
        mock_text_block = MagicMock()
        mock_text_block.text = "A recursive function to calculate factorial."
        type(mock_text_block).__name__ = "TextBlock"

        mock_message = MagicMock()
        mock_message.content = [mock_text_block]
        type(mock_message).__name__ = "AssistantMessage"

        async def mock_query_iter(*args: Any, **kwargs: Any) -> Any:
            yield mock_message

        with patch(
            "maverick.agents.generators.base.query",
            return_value=mock_query_iter(),
        ):
            result = await analyzer.generate(
                {
                    "code": (
                        "def factorial(n): return 1 if n == 0 else n * factorial(n-1)"
                    ),
                    "analysis_type": "summarize",
                }
            )

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_generate_with_invalid_analysis_type_defaults_to_explain(
        self,
    ) -> None:
        """Test that invalid analysis_type defaults to 'explain' mode."""
        analyzer = CodeAnalyzer()

        # Mock the _query method
        mock_text_block = MagicMock()
        mock_text_block.text = "Code explanation output"
        type(mock_text_block).__name__ = "TextBlock"

        mock_message = MagicMock()
        mock_message.content = [mock_text_block]
        type(mock_message).__name__ = "AssistantMessage"

        async def mock_query_iter(*args: Any, **kwargs: Any) -> Any:
            yield mock_message

        with patch(
            "maverick.agents.generators.base.query",
            return_value=mock_query_iter(),
        ):
            # Should not raise an error, just default to explain
            result = await analyzer.generate(
                {
                    "code": "print('hello')",
                    "analysis_type": "invalid_type",
                }
            )

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_generate_with_language_hint_includes_language_in_prompt(
        self,
    ) -> None:
        """Test that optional language parameter is used in prompt."""
        analyzer = CodeAnalyzer()

        # Mock the _query method and capture the prompt
        mock_text_block = MagicMock()
        mock_text_block.text = "Python code explanation"
        type(mock_text_block).__name__ = "TextBlock"

        mock_message = MagicMock()
        mock_message.content = [mock_text_block]
        type(mock_message).__name__ = "AssistantMessage"

        async def mock_query_iter(*args: Any, **kwargs: Any) -> Any:
            yield mock_message

        with patch(
            "maverick.agents.generators.base.query",
            return_value=mock_query_iter(),
        ) as mock_query:
            result = await analyzer.generate(
                {
                    "code": "def hello(): pass",
                    "analysis_type": "explain",
                    "language": "Python",
                }
            )

            # Verify the query was called
            assert mock_query.called
            # The prompt should include the language
            call_args = mock_query.call_args
            prompt = call_args[1]["prompt"]
            assert "python" in prompt.lower()

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_generate_with_empty_code_raises_error(self) -> None:
        """Test that empty code raises GeneratorError."""
        analyzer = CodeAnalyzer()

        with pytest.raises(GeneratorError) as exc_info:
            await analyzer.generate(
                {
                    "code": "",
                    "analysis_type": "explain",
                }
            )

        assert "code" in exc_info.value.message.lower()
        assert "empty" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_generate_with_whitespace_only_code_raises_error(self) -> None:
        """Test that whitespace-only code raises GeneratorError."""
        analyzer = CodeAnalyzer()

        with pytest.raises(GeneratorError) as exc_info:
            await analyzer.generate(
                {
                    "code": "   \n\t  ",
                    "analysis_type": "explain",
                }
            )

        assert "code" in exc_info.value.message.lower()
        assert "empty" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_generate_with_missing_code_raises_error(self) -> None:
        """Test that missing code key raises GeneratorError."""
        analyzer = CodeAnalyzer()

        with pytest.raises(GeneratorError) as exc_info:
            await analyzer.generate(
                {
                    "analysis_type": "explain",
                }
            )

        assert "code" in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_generate_truncates_large_code_at_10kb(self) -> None:
        """Test that code exceeding MAX_SNIPPET_SIZE is truncated with warning."""
        analyzer = CodeAnalyzer()

        # Create code larger than MAX_SNIPPET_SIZE
        large_code = "# " + ("x" * MAX_SNIPPET_SIZE)

        # Mock the _query method
        mock_text_block = MagicMock()
        mock_text_block.text = "Analysis of truncated code"
        type(mock_text_block).__name__ = "TextBlock"

        mock_message = MagicMock()
        mock_message.content = [mock_text_block]
        type(mock_message).__name__ = "AssistantMessage"

        async def mock_query_iter(*args: Any, **kwargs: Any) -> Any:
            yield mock_message

        with (
            patch(
                "maverick.agents.generators.base.query",
                return_value=mock_query_iter(),
            ),
            patch("maverick.agents.generators.base.logger") as mock_logger,
        ):
            result = await analyzer.generate(
                {
                    "code": large_code,
                    "analysis_type": "explain",
                }
            )

            # Should log a WARNING about truncation
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "code" in str(call_args).lower()

        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_generate_logs_truncation_at_warning_level(self) -> None:
        """Test that truncation is logged at WARNING level per FR-017."""
        analyzer = CodeAnalyzer()

        # Create oversized code
        large_code = "x" * (MAX_SNIPPET_SIZE + 1000)

        # Mock the _query method
        mock_text_block = MagicMock()
        mock_text_block.text = "Output"
        type(mock_text_block).__name__ = "TextBlock"

        mock_message = MagicMock()
        mock_message.content = [mock_text_block]
        type(mock_message).__name__ = "AssistantMessage"

        async def mock_query_iter(*args: Any, **kwargs: Any) -> Any:
            yield mock_message

        with (
            patch(
                "maverick.agents.generators.base.query",
                return_value=mock_query_iter(),
            ),
            patch("maverick.agents.generators.base.logger") as mock_logger,
        ):
            await analyzer.generate(
                {
                    "code": large_code,
                    "analysis_type": "explain",
                }
            )

            # Verify WARNING was called for truncation
            assert mock_logger.warning.called
            warning_msg = str(mock_logger.warning.call_args)
            assert "truncat" in warning_msg.lower()

    @pytest.mark.asyncio
    async def test_generate_without_analysis_type_defaults_to_explain(self) -> None:
        """Test that missing analysis_type defaults to 'explain'."""
        analyzer = CodeAnalyzer()

        # Mock the _query method
        mock_text_block = MagicMock()
        mock_text_block.text = "Explanation output"
        type(mock_text_block).__name__ = "TextBlock"

        mock_message = MagicMock()
        mock_message.content = [mock_text_block]
        type(mock_message).__name__ = "AssistantMessage"

        async def mock_query_iter(*args: Any, **kwargs: Any) -> Any:
            yield mock_message

        with patch(
            "maverick.agents.generators.base.query",
            return_value=mock_query_iter(),
        ):
            # Should not raise an error
            result = await analyzer.generate(
                {
                    "code": "print('hello')",
                }
            )

        assert len(result) > 0
