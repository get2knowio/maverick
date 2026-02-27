"""Tests for PromptOverrideConfig Pydantic model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maverick.prompts.config import PromptOverrideConfig


class TestPromptOverrideConfigValid:
    """Test valid PromptOverrideConfig construction."""

    def test_prompt_suffix_only(self) -> None:
        """Valid when only prompt_suffix is set."""
        config = PromptOverrideConfig(prompt_suffix="Always use type hints.")
        assert config.prompt_suffix == "Always use type hints."
        assert config.prompt_file is None

    def test_prompt_file_only(self) -> None:
        """Valid when only prompt_file is set."""
        config = PromptOverrideConfig(prompt_file="prompts/review.md")
        assert config.prompt_file == "prompts/review.md"
        assert config.prompt_suffix is None

    def test_prompt_suffix_with_leading_trailing_spaces(self) -> None:
        """Non-empty suffix with spaces is retained as-is."""
        config = PromptOverrideConfig(prompt_suffix="  use async  ")
        assert config.prompt_suffix == "  use async  "
        assert config.prompt_file is None


class TestPromptOverrideConfigInvalid:
    """Test PromptOverrideConfig validation errors."""

    def test_both_set_raises(self) -> None:
        """Cannot configure both prompt_suffix and prompt_file."""
        with pytest.raises(ValidationError, match="Cannot configure both"):
            PromptOverrideConfig(
                prompt_suffix="extra instructions",
                prompt_file="prompts/review.md",
            )

    def test_neither_set_raises(self) -> None:
        """At least one of prompt_suffix or prompt_file must be set."""
        with pytest.raises(ValidationError, match="At least one of"):
            PromptOverrideConfig()

    def test_empty_string_suffix_raises(self) -> None:
        """Empty string prompt_suffix is treated as None → at-least-one error."""
        with pytest.raises(ValidationError, match="At least one of"):
            PromptOverrideConfig(prompt_suffix="")

    def test_empty_string_file_raises(self) -> None:
        """Empty string prompt_file is treated as None → at-least-one error."""
        with pytest.raises(ValidationError, match="At least one of"):
            PromptOverrideConfig(prompt_file="")

    def test_whitespace_only_suffix_raises(self) -> None:
        """Whitespace-only prompt_suffix is treated as None → at-least-one error."""
        with pytest.raises(ValidationError, match="At least one of"):
            PromptOverrideConfig(prompt_suffix="   ")

    def test_whitespace_only_file_raises(self) -> None:
        """Whitespace-only prompt_file is treated as None → at-least-one error."""
        with pytest.raises(ValidationError, match="At least one of"):
            PromptOverrideConfig(prompt_file="  \t  ")

    def test_both_empty_strings_raises(self) -> None:
        """Both set as empty strings → normalized to None → at-least-one error."""
        with pytest.raises(ValidationError, match="At least one of"):
            PromptOverrideConfig(prompt_suffix="", prompt_file="")
