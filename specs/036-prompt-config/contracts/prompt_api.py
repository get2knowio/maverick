"""Contract: Three-Tier Prompt Configuration API.

Branch: 036-prompt-config
Date: 2026-02-27

This file defines the public API contracts for the prompt configuration system.
It is a design artifact — NOT runnable code. Implementation MUST match these
signatures and behaviors.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OverridePolicy(str, Enum):
    """Governs what kind of user override a step allows."""

    AUGMENT_ONLY = "augment_only"
    """Only prompt_suffix is allowed. Full replacement via prompt_file is rejected."""

    REPLACE = "replace"
    """Both prompt_suffix and prompt_file are allowed (prompt_file replaces the default)."""


class PromptSource(str, Enum):
    """Describes how the final prompt was resolved."""

    DEFAULT = "default"
    """Registry default with no user override."""

    SUFFIX = "suffix"
    """Registry default + user-supplied suffix appended."""

    FILE = "file"
    """Full replacement from a user-supplied prompt_file."""

    PROVIDER_VARIANT = "provider-variant"
    """Provider-specific default was selected as the base (before any override).
    This is the final source only when no user override (suffix/file) is applied.
    If an override is applied on top, source changes to SUFFIX or FILE."""


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

GENERIC_PROVIDER: str = "__generic__"
"""Sentinel provider value meaning 'any/default provider'."""


@dataclass(frozen=True, slots=True)
class PromptEntry:
    """A single prompt registered in the PromptRegistry.

    Attributes:
        text: Default prompt/instructions text.
        policy: Override policy governing user customization.
        provider: Provider key; defaults to GENERIC_PROVIDER.
        is_template: Whether text contains $-variable placeholders
            that require render_prompt() processing.
    """

    text: str
    policy: OverridePolicy
    provider: str = GENERIC_PROVIDER
    is_template: bool = False


@dataclass(frozen=True, slots=True)
class PromptResolution:
    """Result of resolve_prompt() — the final resolved prompt with metadata.

    Attributes:
        text: The final resolved prompt string, ready to pass to an agent.
        source: How the prompt was resolved (default, suffix, file, provider-variant).
        step_name: The step name this resolution was for.
        provider: The provider that was matched in the registry.
        override_applied: Whether a user override (suffix or file) was applied.
    """

    text: str
    source: PromptSource
    step_name: str
    provider: str
    override_applied: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for logging and DSL integration."""
        return {
            "text": self.text,
            "source": self.source.value,
            "step_name": self.step_name,
            "provider": self.provider,
            "override_applied": self.override_applied,
        }


# ---------------------------------------------------------------------------
# PromptRegistry
# ---------------------------------------------------------------------------


class PromptRegistry:
    """Immutable registry of default prompts keyed by (step_name, provider).

    Created once at application startup via build_default_registry().
    Read-only after construction — no add/remove/update methods.

    Args:
        entries: Mapping of (step_name, provider) tuples to PromptEntry objects.

    Raises:
        PromptConfigError: If entries is empty.
    """

    def __init__(self, entries: dict[tuple[str, str], PromptEntry]) -> None: ...

    def get(self, step_name: str, provider: str = GENERIC_PROVIDER) -> PromptEntry:
        """Look up a prompt entry with fallback to generic provider.

        Resolution order:
        1. (step_name, provider) — exact match
        2. (step_name, GENERIC_PROVIDER) — generic fallback

        Args:
            step_name: The canonical step/role name (e.g., "implement").
            provider: Provider identifier (e.g., "claude", "gemini").

        Returns:
            The matching PromptEntry.

        Raises:
            PromptConfigError: If no entry exists for the step_name.
        """
        ...

    def get_policy(self, step_name: str) -> OverridePolicy:
        """Shortcut to get the override policy for a step.

        Uses the generic provider entry's policy.

        Args:
            step_name: The canonical step/role name.

        Returns:
            The OverridePolicy for the step.

        Raises:
            PromptConfigError: If no entry exists for the step_name.
        """
        ...

    def has(self, step_name: str, provider: str = GENERIC_PROVIDER) -> bool:
        """Check if a step+provider combination is registered.

        Args:
            step_name: The canonical step/role name.
            provider: Provider identifier.

        Returns:
            True if the combination exists in the registry.
        """
        ...

    def step_names(self) -> frozenset[str]:
        """Return all registered step names (deduplicated across providers).

        Returns:
            Frozen set of step name strings.
        """
        ...

    def validate_override(
        self,
        step_name: str,
        override: PromptOverrideConfig,
    ) -> None:
        """Validate a user override against the step's policy.

        Args:
            step_name: The canonical step/role name.
            override: The user's override configuration.

        Raises:
            PromptConfigError: If the override violates the step's policy
                (e.g., prompt_file on an augment_only step).
        """
        ...


# ---------------------------------------------------------------------------
# PromptOverrideConfig (Pydantic — for maverick.yaml parsing)
# ---------------------------------------------------------------------------

# class PromptOverrideConfig(BaseModel):
#     """User-provided prompt override for a single step.
#
#     Configured in maverick.yaml under the `prompts:` key:
#
#         prompts:
#           implement:
#             prompt_suffix: "Always use snake_case."
#           pr_description:
#             prompt_file: ".maverick/prompts/pr-desc.md"
#
#     Validation:
#         - prompt_suffix and prompt_file are mutually exclusive.
#         - At least one must be set.
#         - prompt_file path validated at startup (exists, readable, within project root).
#     """
#
#     prompt_suffix: str | None = None
#     prompt_file: str | None = None


# ---------------------------------------------------------------------------
# resolve_prompt()
# ---------------------------------------------------------------------------


def resolve_prompt(
    *,
    step_name: str,
    registry: PromptRegistry,
    provider: str = GENERIC_PROVIDER,
    override: PromptOverrideConfig | None = None,
    project_root: Path | None = None,
    render_context: dict[str, Any] | None = None,
) -> PromptResolution:
    """Resolve the final prompt for a step using the three-tier system.

    Resolution order (FR-005):
    1. Select base prompt from registry using (step_name, provider) with
       fallback to (step_name, generic).
    2. If override.prompt_file is configured and step policy allows replacement,
       use file contents as base.
    3. If override.prompt_suffix is configured, append it to the base prompt
       with a separator heading.

    Template rendering (FR-014):
    If the base prompt is a template (entry.is_template=True), render_prompt()
    is called with render_context before applying overrides.

    Logging (FR-015):
    Emits a DEBUG-level `prompt_resolved` structlog event.

    Args:
        step_name: Canonical step/role name (e.g., "implement").
        registry: The immutable PromptRegistry.
        provider: Provider identifier for provider-specific variant lookup.
        override: User's prompt override config (from maverick.yaml prompts: section).
        project_root: Project root for resolving relative prompt_file paths.
            Required if override.prompt_file is set.
        render_context: Template variables for render_prompt() (e.g., project_type).

    Returns:
        PromptResolution with the final text and resolution metadata.

    Raises:
        PromptConfigError: If step_name not in registry, policy violated,
            prompt_file missing/outside project root, or other config error.
    """
    ...


# ---------------------------------------------------------------------------
# build_default_registry()
# ---------------------------------------------------------------------------


def build_default_registry() -> PromptRegistry:
    """Build the default PromptRegistry from shipped agent/generator prompts.

    Imports prompt constants from agent modules by reference (FR-003: no
    duplication of prompt text). Each entry declares its override policy.

    Returns:
        A fully populated, immutable PromptRegistry.
    """
    ...


# ---------------------------------------------------------------------------
# validate_prompt_config()
# ---------------------------------------------------------------------------


def validate_prompt_config(
    prompts: dict[str, PromptOverrideConfig],
    registry: PromptRegistry,
    project_root: Path,
) -> None:
    """Validate all prompt overrides in the config at startup (FR-011).

    Checks:
    - All step names in prompts: config exist in the registry.
    - Override policy is not violated (no prompt_file on augment_only steps).
    - All prompt_file paths exist, are readable, and are within project_root.

    Args:
        prompts: The prompts: section from MaverickConfig.
        registry: The PromptRegistry to validate against.
        project_root: Project root for file path validation.

    Raises:
        PromptConfigError: On the first validation failure found.
    """
    ...
