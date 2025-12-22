"""Unit tests for GeneratorAgent base class."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from maverick.agents.generators.base import (
    DEFAULT_MODEL,
    MAX_DIFF_SIZE,
    MAX_SNIPPET_SIZE,
    GeneratorAgent,
)
from maverick.exceptions import GeneratorError


class ConcreteGenerator(GeneratorAgent):
    """Concrete implementation for testing the abstract base class."""

    def __init__(
        self,
        name: str = "test-generator",
        system_prompt: str = "You are a test generator.",
        model: str = DEFAULT_MODEL,
    ) -> None:
        super().__init__(name=name, system_prompt=system_prompt, model=model)

    async def generate(self, context: dict[str, Any]) -> str:
        """Simple implementation that calls _query with context."""
        prompt = f"Generate for: {context.get('input', 'default')}"
        return await self._query(prompt)


class TestGeneratorAgentConstruction:
    """Tests for GeneratorAgent construction."""

    def test_construction_with_required_fields(self) -> None:
        """Test successful construction with required fields."""
        generator = ConcreteGenerator(
            name="my-generator",
            system_prompt="You generate text.",
        )

        assert generator.name == "my-generator"
        assert generator.system_prompt == "You generate text."
        assert generator.model == DEFAULT_MODEL

    def test_construction_with_custom_model(self) -> None:
        """Test construction with custom model."""
        generator = ConcreteGenerator(
            name="my-generator",
            system_prompt="You generate text.",
            model="claude-opus-4-5-20250929",
        )

        assert generator.model == "claude-opus-4-5-20250929"

    def test_construction_with_empty_name_raises_error(self) -> None:
        """Test that empty name raises ValueError."""
        with pytest.raises(ValueError, match="name must be non-empty"):
            ConcreteGenerator(name="", system_prompt="You generate text.")

    def test_construction_with_empty_system_prompt_raises_error(self) -> None:
        """Test that empty system_prompt raises ValueError."""
        with pytest.raises(ValueError, match="system_prompt must be non-empty"):
            ConcreteGenerator(name="my-generator", system_prompt="")


class TestGeneratorAgentProperties:
    """Tests for GeneratorAgent property immutability."""

    def test_name_property_is_read_only(self) -> None:
        """Test that name property cannot be set."""
        generator = ConcreteGenerator(name="test-name")
        assert generator.name == "test-name"
        with pytest.raises(AttributeError):
            generator.name = "new-name"  # type: ignore[misc]

    def test_system_prompt_property_is_read_only(self) -> None:
        """Test that system_prompt property cannot be set."""
        generator = ConcreteGenerator(system_prompt="Test prompt.")
        assert generator.system_prompt == "Test prompt."
        with pytest.raises(AttributeError):
            generator.system_prompt = "New prompt"  # type: ignore[misc]

    def test_model_property_is_read_only(self) -> None:
        """Test that model property cannot be set."""
        generator = ConcreteGenerator(model="custom-model")
        assert generator.model == "custom-model"
        with pytest.raises(AttributeError):
            generator.model = "new-model"  # type: ignore[misc]


class TestTruncateInput:
    """Tests for _truncate_input helper."""

    def test_no_truncation_when_under_limit(self) -> None:
        """Test that content under limit is returned unchanged."""
        generator = ConcreteGenerator()
        content = "Short content"

        result = generator._truncate_input(content, 1000, "test_field")

        assert result == content

    def test_truncation_when_over_limit(self) -> None:
        """Test that content over limit is truncated with marker."""
        generator = ConcreteGenerator()
        content = "A" * 200

        result = generator._truncate_input(content, 100, "test_field")

        assert len(result) < len(content)
        assert result.endswith("\n... [truncated]")
        assert result.startswith("A" * 100)

    def test_truncation_logs_warning(self) -> None:
        """Test that truncation logs a warning."""
        generator = ConcreteGenerator()
        content = "A" * 200

        with patch("maverick.agents.generators.base.logger") as mock_logger:
            generator._truncate_input(content, 100, "test_field")

            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "test_field" in str(call_args)
            assert "200" in str(call_args)
            assert "100" in str(call_args)

    def test_exact_limit_no_truncation(self) -> None:
        """Test that content at exact limit is not truncated."""
        generator = ConcreteGenerator()
        content = "A" * 100

        result = generator._truncate_input(content, 100, "test_field")

        assert result == content


class TestQuery:
    """Tests for _query helper method."""

    @pytest.mark.asyncio
    async def test_query_returns_text_from_response(self) -> None:
        """Test that _query extracts text from Claude response."""
        generator = ConcreteGenerator()

        # Create mock message with TextBlock
        mock_text_block = MagicMock()
        mock_text_block.text = "Generated output"
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
            result = await generator._query("Test prompt")

        assert result == "Generated output"

    @pytest.mark.asyncio
    async def test_query_handles_multiple_text_blocks(self) -> None:
        """Test that _query concatenates multiple text blocks."""
        generator = ConcreteGenerator()

        # Create mock message with multiple TextBlocks
        mock_block1 = MagicMock()
        mock_block1.text = "First part"
        type(mock_block1).__name__ = "TextBlock"

        mock_block2 = MagicMock()
        mock_block2.text = "Second part"
        type(mock_block2).__name__ = "TextBlock"

        mock_message = MagicMock()
        mock_message.content = [mock_block1, mock_block2]
        type(mock_message).__name__ = "AssistantMessage"

        async def mock_query_iter(*args: Any, **kwargs: Any) -> Any:
            yield mock_message

        with patch(
            "maverick.agents.generators.base.query",
            return_value=mock_query_iter(),
        ):
            result = await generator._query("Test prompt")

        assert "First part" in result
        assert "Second part" in result

    @pytest.mark.asyncio
    async def test_query_handles_multiple_messages(self) -> None:
        """Test that _query concatenates text from multiple messages."""
        generator = ConcreteGenerator()

        # Mock messages
        mock_msg1 = MagicMock()
        mock_msg1.content = [MagicMock(text="Part 1")]
        mock_msg1.content[0].__class__.__name__ = "TextBlock"
        type(mock_msg1).__name__ = "AssistantMessage"

        mock_msg2 = MagicMock()
        mock_msg2.content = [MagicMock(text="Part 2")]
        mock_msg2.content[0].__class__.__name__ = "TextBlock"
        type(mock_msg2).__name__ = "AssistantMessage"

        async def mock_iter(*args: Any, **kwargs: Any) -> Any:
            yield mock_msg1
            yield mock_msg2

        with patch(
            "maverick.agents.generators.base.query",
            side_effect=mock_iter,
        ):
            result = await generator._query("prompt")

        assert result == "Part 1\nPart 2"

    @pytest.mark.asyncio
    async def test_query_wraps_expected_errors_in_generator_error(self) -> None:
        """Test that expected SDK errors are wrapped in GeneratorError."""
        generator = ConcreteGenerator()

        async def mock_query_error(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError("SDK connection error")
            yield  # Make this a generator

        with patch(
            "maverick.agents.generators.base.query",
            return_value=mock_query_error(),
        ):
            with pytest.raises(GeneratorError) as exc_info:
                await generator._query("Test prompt")

            assert "SDK connection error" in exc_info.value.message
            assert exc_info.value.generator_name == "test-generator"

    @pytest.mark.asyncio
    async def test_query_reraises_unexpected_errors(self) -> None:
        """Test that unexpected errors are re-raised, not wrapped."""
        generator = ConcreteGenerator()

        class UnexpectedError(Exception):
            pass

        async def mock_query_error(*args: Any, **kwargs: Any) -> Any:
            raise UnexpectedError("Something unexpected")
            yield  # Make this a generator

        with patch(
            "maverick.agents.generators.base.query",
            return_value=mock_query_error(),
        ):
            with pytest.raises(UnexpectedError) as exc_info:
                await generator._query("Test prompt")

            assert "Something unexpected" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_logs_debug_info(self) -> None:
        """Test that _query logs debug information for inputs/outputs."""
        generator = ConcreteGenerator()

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
            await generator._query("Test prompt")

            # Should log prompt and output at DEBUG level
            assert mock_logger.debug.call_count >= 1


class TestConstants:
    """Tests for module constants."""

    def test_max_diff_size_is_100kb(self) -> None:
        """Test MAX_DIFF_SIZE is 100KB."""
        assert MAX_DIFF_SIZE == 102400

    def test_max_snippet_size_is_10kb(self) -> None:
        """Test MAX_SNIPPET_SIZE is 10KB."""
        assert MAX_SNIPPET_SIZE == 10240

    def test_default_model(self) -> None:
        """Test DEFAULT_MODEL is set correctly."""
        assert DEFAULT_MODEL == "claude-sonnet-4-5-20250929"
