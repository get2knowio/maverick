"""Tests for prompt configuration core models."""

from __future__ import annotations

import dataclasses

import pytest

from maverick.exceptions.config import ConfigError
from maverick.prompts.models import (
    GENERIC_PROVIDER,
    OverridePolicy,
    PromptConfigError,
    PromptEntry,
    PromptResolution,
    PromptSource,
)

# ---------- OverridePolicy enum ----------


class TestOverridePolicy:
    """Tests for the OverridePolicy enum."""

    def test_augment_only_value(self) -> None:
        assert OverridePolicy.AUGMENT_ONLY.value == "augment_only"

    def test_replace_value(self) -> None:
        assert OverridePolicy.REPLACE.value == "replace"

    def test_str_inheritance(self) -> None:
        assert isinstance(OverridePolicy.AUGMENT_ONLY, str)
        assert isinstance(OverridePolicy.REPLACE, str)

    def test_str_equals_value(self) -> None:
        assert OverridePolicy.AUGMENT_ONLY == "augment_only"
        assert OverridePolicy.REPLACE == "replace"


# ---------- PromptSource enum ----------


class TestPromptSource:
    """Tests for the PromptSource enum."""

    def test_default_value(self) -> None:
        assert PromptSource.DEFAULT.value == "default"

    def test_suffix_value(self) -> None:
        assert PromptSource.SUFFIX.value == "suffix"

    def test_file_value(self) -> None:
        assert PromptSource.FILE.value == "file"

    def test_provider_variant_value(self) -> None:
        assert PromptSource.PROVIDER_VARIANT.value == "provider-variant"

    def test_str_inheritance(self) -> None:
        for member in PromptSource:
            assert isinstance(member, str)

    def test_str_equals_value(self) -> None:
        assert PromptSource.DEFAULT == "default"
        assert PromptSource.SUFFIX == "suffix"
        assert PromptSource.FILE == "file"
        assert PromptSource.PROVIDER_VARIANT == "provider-variant"


# ---------- PromptEntry frozen dataclass ----------


class TestPromptEntry:
    """Tests for the PromptEntry frozen dataclass."""

    def test_default_provider(self, sample_entry: PromptEntry) -> None:
        assert sample_entry.provider == GENERIC_PROVIDER
        assert sample_entry.provider == "__generic__"

    def test_default_is_template(self, sample_entry: PromptEntry) -> None:
        assert sample_entry.is_template is False

    def test_all_fields_accessible(self, sample_entry: PromptEntry) -> None:
        assert sample_entry.text == "You are a code implementer."
        assert sample_entry.policy is OverridePolicy.AUGMENT_ONLY
        assert sample_entry.provider == GENERIC_PROVIDER
        assert sample_entry.is_template is False

    def test_custom_provider(self, provider_entry: PromptEntry) -> None:
        assert provider_entry.provider == "gemini"

    def test_template_flag(self, template_entry: PromptEntry) -> None:
        assert template_entry.is_template is True

    def test_replace_policy(self, replace_entry: PromptEntry) -> None:
        assert replace_entry.policy is OverridePolicy.REPLACE

    def test_frozen_immutability_text(self, sample_entry: PromptEntry) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            sample_entry.text = "new text"  # type: ignore[misc]

    def test_frozen_immutability_policy(self, sample_entry: PromptEntry) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            sample_entry.policy = OverridePolicy.REPLACE  # type: ignore[misc]

    def test_frozen_immutability_provider(self, sample_entry: PromptEntry) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            sample_entry.provider = "openai"  # type: ignore[misc]

    def test_frozen_immutability_is_template(self, sample_entry: PromptEntry) -> None:
        with pytest.raises(dataclasses.FrozenInstanceError):
            sample_entry.is_template = True  # type: ignore[misc]


# ---------- PromptResolution frozen dataclass ----------


class TestPromptResolution:
    """Tests for the PromptResolution frozen dataclass."""

    def test_all_fields_set(self) -> None:
        resolution = PromptResolution(
            text="Resolved prompt text.",
            source=PromptSource.DEFAULT,
            step_name="implement",
            provider=GENERIC_PROVIDER,
            override_applied=False,
        )
        assert resolution.text == "Resolved prompt text."
        assert resolution.source is PromptSource.DEFAULT
        assert resolution.step_name == "implement"
        assert resolution.provider == GENERIC_PROVIDER
        assert resolution.override_applied is False

    def test_override_applied_true(self) -> None:
        resolution = PromptResolution(
            text="Base prompt.\n\nUser suffix.",
            source=PromptSource.SUFFIX,
            step_name="review",
            provider="gemini",
            override_applied=True,
        )
        assert resolution.override_applied is True
        assert resolution.source is PromptSource.SUFFIX

    def test_frozen_immutability(self) -> None:
        resolution = PromptResolution(
            text="prompt",
            source=PromptSource.FILE,
            step_name="describe",
            provider=GENERIC_PROVIDER,
            override_applied=True,
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            resolution.text = "changed"  # type: ignore[misc]

    def test_to_dict_returns_correct_dict(self) -> None:
        resolution = PromptResolution(
            text="Final prompt.",
            source=PromptSource.SUFFIX,
            step_name="implement",
            provider="anthropic",
            override_applied=True,
        )
        result = resolution.to_dict()
        assert result == {
            "text": "Final prompt.",
            "source": "suffix",
            "step_name": "implement",
            "provider": "anthropic",
            "override_applied": True,
        }

    def test_to_dict_source_is_string_not_enum(self) -> None:
        resolution = PromptResolution(
            text="text",
            source=PromptSource.PROVIDER_VARIANT,
            step_name="step",
            provider=GENERIC_PROVIDER,
            override_applied=False,
        )
        result = resolution.to_dict()
        assert isinstance(result["source"], str)
        assert result["source"] == "provider-variant"
        assert not isinstance(result["source"], PromptSource)

    def test_to_dict_default_source(self) -> None:
        resolution = PromptResolution(
            text="default text",
            source=PromptSource.DEFAULT,
            step_name="review",
            provider=GENERIC_PROVIDER,
            override_applied=False,
        )
        result = resolution.to_dict()
        assert result["source"] == "default"

    def test_to_dict_file_source(self) -> None:
        resolution = PromptResolution(
            text="file-loaded prompt",
            source=PromptSource.FILE,
            step_name="describe",
            provider=GENERIC_PROVIDER,
            override_applied=True,
        )
        result = resolution.to_dict()
        assert result["source"] == "file"


# ---------- PromptConfigError ----------


class TestPromptConfigError:
    """Tests for the PromptConfigError exception."""

    def test_inherits_from_config_error(self) -> None:
        error = PromptConfigError("bad config")
        assert isinstance(error, ConfigError)

    def test_accepts_message(self) -> None:
        error = PromptConfigError("Step 'review' not found in registry")
        assert "Step 'review' not found in registry" in str(error)

    def test_str_returns_message(self) -> None:
        msg = "Invalid prompt_file path: /nonexistent.txt"
        error = PromptConfigError(msg)
        assert str(error) == msg

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(PromptConfigError, match="something went wrong"):
            raise PromptConfigError("something went wrong")

    def test_catchable_as_config_error(self) -> None:
        with pytest.raises(ConfigError):
            raise PromptConfigError("caught as parent")
