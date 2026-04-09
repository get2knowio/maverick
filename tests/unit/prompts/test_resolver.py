"""Tests for resolve_prompt() — accumulated across user stories."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.prompts.config import PromptOverrideConfig
from maverick.prompts.models import (
    GENERIC_PROVIDER,
    OverridePolicy,
    PromptConfigError,
    PromptEntry,
    PromptResolution,
    PromptSource,
)
from maverick.prompts.registry import PromptRegistry
from maverick.prompts.resolver import resolve_prompt


class TestResolvePromptDefault:
    """T010: Default path — no override returns default text."""

    def test_returns_default_text(self, sample_entries: dict) -> None:
        registry = PromptRegistry(sample_entries)
        result = resolve_prompt(step_name="implement", registry=registry)
        assert result.text == "You are a code implementer."

    def test_source_is_default(self, sample_entries: dict) -> None:
        registry = PromptRegistry(sample_entries)
        result = resolve_prompt(step_name="implement", registry=registry)
        assert result.source == PromptSource.DEFAULT

    def test_override_not_applied(self, sample_entries: dict) -> None:
        registry = PromptRegistry(sample_entries)
        result = resolve_prompt(step_name="implement", registry=registry)
        assert result.override_applied is False

    def test_step_name_in_result(self, sample_entries: dict) -> None:
        registry = PromptRegistry(sample_entries)
        result = resolve_prompt(step_name="implement", registry=registry)
        assert result.step_name == "implement"

    def test_provider_in_result(self, sample_entries: dict) -> None:
        registry = PromptRegistry(sample_entries)
        result = resolve_prompt(step_name="implement", registry=registry)
        assert result.provider == GENERIC_PROVIDER

    def test_missing_step_raises_error(self, sample_entries: dict) -> None:
        registry = PromptRegistry(sample_entries)
        with pytest.raises(PromptConfigError, match="No default prompt registered"):
            resolve_prompt(step_name="nonexistent", registry=registry)

    def test_returns_prompt_resolution_type(self, sample_entries: dict) -> None:
        registry = PromptRegistry(sample_entries)
        result = resolve_prompt(step_name="implement", registry=registry)
        assert isinstance(result, PromptResolution)


class TestResolvePromptSuffix:
    """T020: Suffix path — prompt_suffix appended to default text."""

    SUFFIX_SEPARATOR = "\n\n---\n\n## Project-Specific Instructions\n\n"

    def test_suffix_appended_with_separator(self, sample_entries: dict) -> None:
        registry = PromptRegistry(sample_entries)
        override = PromptOverrideConfig(prompt_suffix="Use snake_case.")
        result = resolve_prompt(step_name="implement", registry=registry, override=override)
        expected = "You are a code implementer." + self.SUFFIX_SEPARATOR + "Use snake_case."
        assert result.text == expected

    def test_source_is_suffix(self, sample_entries: dict) -> None:
        registry = PromptRegistry(sample_entries)
        override = PromptOverrideConfig(prompt_suffix="Use snake_case.")
        result = resolve_prompt(step_name="implement", registry=registry, override=override)
        assert result.source == PromptSource.SUFFIX

    def test_override_applied_true(self, sample_entries: dict) -> None:
        registry = PromptRegistry(sample_entries)
        override = PromptOverrideConfig(prompt_suffix="Use snake_case.")
        result = resolve_prompt(step_name="implement", registry=registry, override=override)
        assert result.override_applied is True

    def test_template_rendering_in_base_and_suffix(self) -> None:
        entries = {
            ("implement", GENERIC_PROVIDER): PromptEntry(
                text="You implement $project_type code.",
                policy=OverridePolicy.AUGMENT_ONLY,
                is_template=True,
            ),
        }
        registry = PromptRegistry(entries)
        override = PromptOverrideConfig(prompt_suffix="Follow $project_conventions rules.")
        result = resolve_prompt(
            step_name="implement",
            registry=registry,
            override=override,
            render_context={
                "project_type": "python",
                "project_conventions": "PEP8",
            },
        )
        assert "python" in result.text
        assert "PEP8" in result.text


class TestResolvePromptProviderVariant:
    """T012: Provider-specific prompt resolution."""

    def test_provider_variant_selected(self, multi_provider_entries: dict) -> None:
        """When provider matches a registered variant, return that variant."""
        registry = PromptRegistry(multi_provider_entries)
        result = resolve_prompt(step_name="review", registry=registry, provider="gemini")
        assert "Gemini" in result.text
        assert result.source == PromptSource.PROVIDER_VARIANT

    def test_generic_fallback_when_no_provider_variant(self, multi_provider_entries: dict) -> None:
        """When no provider is specified, fall back to generic entry."""
        registry = PromptRegistry(multi_provider_entries)
        result = resolve_prompt(step_name="review", registry=registry)
        assert "Gemini" not in result.text
        assert result.source == PromptSource.DEFAULT

    def test_default_provider_returns_generic(self, multi_provider_entries: dict) -> None:
        """Explicitly passing GENERIC_PROVIDER returns the generic entry."""
        registry = PromptRegistry(multi_provider_entries)
        result = resolve_prompt(
            step_name="review",
            registry=registry,
            provider=GENERIC_PROVIDER,
        )
        assert result.source == PromptSource.DEFAULT
        assert "Gemini" not in result.text

    def test_provider_variant_override_not_applied(self, multi_provider_entries: dict) -> None:
        """Provider variant with no user override has override_applied=False."""
        registry = PromptRegistry(multi_provider_entries)
        result = resolve_prompt(step_name="review", registry=registry, provider="gemini")
        assert result.override_applied is False


class TestResolvePromptFile:
    """T030: prompt_file resolution — full replacement from file."""

    def test_file_replaces_default_for_replace_policy(self, tmp_path: Path) -> None:
        """prompt_file overrides default text when policy is replace."""
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Custom PR description prompt.")

        entries = {
            ("pr_description", GENERIC_PROVIDER): PromptEntry(
                text="Generate a PR description.",
                policy=OverridePolicy.REPLACE,
            ),
        }
        registry = PromptRegistry(entries)
        override = PromptOverrideConfig(prompt_file="prompt.md")

        result = resolve_prompt(
            step_name="pr_description",
            registry=registry,
            override=override,
            project_root=tmp_path,
        )

        assert result.text == "Custom PR description prompt."
        assert result.source == PromptSource.FILE
        assert result.override_applied is True

    def test_augment_only_rejects_file(self, tmp_path: Path) -> None:
        """augment_only policy rejects prompt_file override."""
        entries = {
            ("implement", GENERIC_PROVIDER): PromptEntry(
                text="You are a code implementer.",
                policy=OverridePolicy.AUGMENT_ONLY,
            ),
        }
        registry = PromptRegistry(entries)
        override = PromptOverrideConfig(prompt_file="custom.md")

        with pytest.raises(
            PromptConfigError,
            match="does not allow full prompt replacement",
        ):
            resolve_prompt(
                step_name="implement",
                registry=registry,
                override=override,
                project_root=tmp_path,
            )

    def test_missing_file_raises_error(self, tmp_path: Path) -> None:
        """Nonexistent prompt_file raises PromptConfigError."""
        entries = {
            ("pr_description", GENERIC_PROVIDER): PromptEntry(
                text="Generate a PR description.",
                policy=OverridePolicy.REPLACE,
            ),
        }
        registry = PromptRegistry(entries)
        override = PromptOverrideConfig(prompt_file="nonexistent.md")

        with pytest.raises(
            PromptConfigError,
            match="Prompt file not found",
        ):
            resolve_prompt(
                step_name="pr_description",
                registry=registry,
                override=override,
                project_root=tmp_path,
            )

    def test_path_outside_project_root_raises_error(self, tmp_path: Path) -> None:
        """prompt_file with path traversal outside project root is rejected."""
        entries = {
            ("pr_description", GENERIC_PROVIDER): PromptEntry(
                text="Generate a PR description.",
                policy=OverridePolicy.REPLACE,
            ),
        }
        registry = PromptRegistry(entries)
        override = PromptOverrideConfig(prompt_file="../../../etc/passwd")

        with pytest.raises(
            PromptConfigError,
            match="must be within project root",
        ):
            resolve_prompt(
                step_name="pr_description",
                registry=registry,
                override=override,
                project_root=tmp_path,
            )

    def test_template_rendering_on_file_contents(self, tmp_path: Path) -> None:
        """Template variables in prompt_file contents are rendered."""
        prompt_file = tmp_path / "template_prompt.md"
        prompt_file.write_text("You implement $project_type code.")

        entries = {
            ("pr_description", GENERIC_PROVIDER): PromptEntry(
                text="Default text.",
                policy=OverridePolicy.REPLACE,
                is_template=True,
            ),
        }
        registry = PromptRegistry(entries)
        override = PromptOverrideConfig(prompt_file="template_prompt.md")

        result = resolve_prompt(
            step_name="pr_description",
            registry=registry,
            override=override,
            project_root=tmp_path,
            render_context={"project_type": "python"},
        )

        assert result.text == "You implement python code."
