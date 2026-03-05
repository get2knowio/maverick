"""Unit tests for GeneratorAgent base class."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from maverick.agents.generators.base import (
    DEFAULT_MODEL,
    MAX_DIFF_SIZE,
    MAX_SNIPPET_SIZE,
    GeneratorAgent,
)


class ConcreteGenerator(GeneratorAgent):
    """Concrete implementation for testing the abstract base class."""

    def __init__(
        self,
        name: str = "test-generator",
        system_prompt: str = "You are a test generator.",
        model: str = DEFAULT_MODEL,
    ) -> None:
        super().__init__(name=name, system_prompt=system_prompt, model=model)

    def build_prompt(self, context: dict[str, Any]) -> str:
        """Simple implementation that returns a prompt from context."""
        return f"Generate for: {context.get('input', 'default')}"


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
