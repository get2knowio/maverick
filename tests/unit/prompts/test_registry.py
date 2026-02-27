"""Tests for PromptRegistry."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from maverick.prompts.models import (
    GENERIC_PROVIDER,
    OverridePolicy,
    PromptConfigError,
    PromptEntry,
)
from maverick.prompts.registry import PromptRegistry


class TestPromptRegistryConstruction:
    """Tests for PromptRegistry construction."""

    def test_creates_with_valid_entries(
        self,
        sample_entries: dict[tuple[str, str], PromptEntry],
    ) -> None:
        registry = PromptRegistry(sample_entries)
        assert registry.has("implement")
        assert registry.has("pr_description")

    def test_raises_on_empty_entries(self) -> None:
        with pytest.raises(PromptConfigError, match="empty entries"):
            PromptRegistry({})

    def test_defensive_copy(
        self,
        sample_entries: dict[tuple[str, str], PromptEntry],
    ) -> None:
        """Mutating the original dict does not affect the registry."""
        registry = PromptRegistry(sample_entries)
        sample_entries[("new_step", GENERIC_PROVIDER)] = PromptEntry(
            text="extra",
            policy=OverridePolicy.REPLACE,
        )
        assert not registry.has("new_step")


class TestPromptRegistryGet:
    """Tests for PromptRegistry.get()."""

    def test_returns_exact_match(
        self,
        multi_provider_entries: dict[tuple[str, str], PromptEntry],
        provider_entry: PromptEntry,
    ) -> None:
        registry = PromptRegistry(multi_provider_entries)
        result = registry.get("review", "gemini")
        assert result is provider_entry

    def test_falls_back_to_generic_provider(
        self,
        multi_provider_entries: dict[tuple[str, str], PromptEntry],
        sample_entry: PromptEntry,
    ) -> None:
        registry = PromptRegistry(multi_provider_entries)
        # "implement" only has a generic entry; asking for "openai" should fall back
        result = registry.get("implement", "openai")
        assert result is sample_entry

    def test_raises_for_unknown_step(
        self,
        sample_entries: dict[tuple[str, str], PromptEntry],
    ) -> None:
        registry = PromptRegistry(sample_entries)
        with pytest.raises(
            PromptConfigError,
            match="No default prompt registered for step 'nonexistent'",
        ):
            registry.get("nonexistent")

    def test_default_provider_is_generic(
        self,
        sample_entries: dict[tuple[str, str], PromptEntry],
        sample_entry: PromptEntry,
    ) -> None:
        registry = PromptRegistry(sample_entries)
        result = registry.get("implement")
        assert result is sample_entry


class TestPromptRegistryGetPolicy:
    """Tests for PromptRegistry.get_policy()."""

    def test_returns_correct_policy(
        self,
        sample_entries: dict[tuple[str, str], PromptEntry],
    ) -> None:
        registry = PromptRegistry(sample_entries)
        assert registry.get_policy("implement") == OverridePolicy.AUGMENT_ONLY
        assert registry.get_policy("pr_description") == OverridePolicy.REPLACE


class TestPromptRegistryHas:
    """Tests for PromptRegistry.has()."""

    def test_returns_true_for_registered(
        self,
        sample_entries: dict[tuple[str, str], PromptEntry],
    ) -> None:
        registry = PromptRegistry(sample_entries)
        assert registry.has("implement") is True
        assert registry.has("pr_description") is True

    def test_returns_false_for_unregistered(
        self,
        sample_entries: dict[tuple[str, str], PromptEntry],
    ) -> None:
        registry = PromptRegistry(sample_entries)
        assert registry.has("nonexistent") is False

    def test_returns_true_for_specific_provider(
        self,
        multi_provider_entries: dict[tuple[str, str], PromptEntry],
    ) -> None:
        registry = PromptRegistry(multi_provider_entries)
        assert registry.has("review", "gemini") is True

    def test_returns_false_for_wrong_provider(
        self,
        multi_provider_entries: dict[tuple[str, str], PromptEntry],
    ) -> None:
        registry = PromptRegistry(multi_provider_entries)
        assert registry.has("review", "openai") is False


class TestPromptRegistryStepNames:
    """Tests for PromptRegistry.step_names()."""

    def test_returns_deduplicated_frozenset(
        self,
        multi_provider_entries: dict[tuple[str, str], PromptEntry],
    ) -> None:
        registry = PromptRegistry(multi_provider_entries)
        names = registry.step_names()
        # "review" appears twice (generic + gemini), but should be deduplicated
        assert names == frozenset({"review", "implement"})
        assert isinstance(names, frozenset)


class TestPromptRegistryValidateOverride:
    """Tests for PromptRegistry.validate_override()."""

    def test_allows_prompt_file_on_replace_policy(
        self,
        sample_entries: dict[tuple[str, str], PromptEntry],
    ) -> None:
        registry = PromptRegistry(sample_entries)
        override = SimpleNamespace(prompt_file="/path/to/file.txt", prompt_suffix=None)
        # Should not raise — pr_description has REPLACE policy
        registry.validate_override("pr_description", override)

    def test_raises_for_prompt_file_on_augment_only(
        self,
        sample_entries: dict[tuple[str, str], PromptEntry],
    ) -> None:
        registry = PromptRegistry(sample_entries)
        override = SimpleNamespace(prompt_file="/path/to/file.txt", prompt_suffix=None)
        with pytest.raises(
            PromptConfigError,
            match="does not allow full prompt replacement.*augment_only",
        ):
            registry.validate_override("implement", override)

    def test_allows_suffix_only_on_augment_only(
        self,
        sample_entries: dict[tuple[str, str], PromptEntry],
    ) -> None:
        registry = PromptRegistry(sample_entries)
        override = SimpleNamespace(prompt_file=None, prompt_suffix="Be concise.")
        # Should not raise — suffix is always allowed
        registry.validate_override("implement", override)
