"""Shared fixtures for prompt configuration tests."""

from __future__ import annotations

import pytest

from maverick.prompts.models import (
    GENERIC_PROVIDER,
    OverridePolicy,
    PromptEntry,
)


@pytest.fixture()
def sample_entry() -> PromptEntry:
    """A basic prompt entry with augment_only policy."""
    return PromptEntry(
        text="You are a code implementer.",
        policy=OverridePolicy.AUGMENT_ONLY,
    )


@pytest.fixture()
def replace_entry() -> PromptEntry:
    """A prompt entry with replace policy."""
    return PromptEntry(
        text="Generate a PR description.",
        policy=OverridePolicy.REPLACE,
    )


@pytest.fixture()
def template_entry() -> PromptEntry:
    """A prompt entry with template variables."""
    return PromptEntry(
        text="You implement $project_type code. $project_conventions",
        policy=OverridePolicy.AUGMENT_ONLY,
        is_template=True,
    )


@pytest.fixture()
def provider_entry() -> PromptEntry:
    """A provider-specific prompt entry."""
    return PromptEntry(
        text="You are a code reviewer optimized for Gemini.",
        policy=OverridePolicy.AUGMENT_ONLY,
        provider="gemini",
    )


@pytest.fixture()
def sample_entries(
    sample_entry: PromptEntry,
    replace_entry: PromptEntry,
) -> dict[tuple[str, str], PromptEntry]:
    """A small registry mapping for testing."""
    return {
        ("implement", GENERIC_PROVIDER): sample_entry,
        ("pr_description", GENERIC_PROVIDER): replace_entry,
    }


@pytest.fixture()
def multi_provider_entries(
    sample_entry: PromptEntry,
    provider_entry: PromptEntry,
) -> dict[tuple[str, str], PromptEntry]:
    """Registry entries with generic and provider-specific variants."""
    return {
        ("review", GENERIC_PROVIDER): PromptEntry(
            text="You are a code reviewer.",
            policy=OverridePolicy.AUGMENT_ONLY,
        ),
        ("review", "gemini"): provider_entry,
        ("implement", GENERIC_PROVIDER): sample_entry,
    }
