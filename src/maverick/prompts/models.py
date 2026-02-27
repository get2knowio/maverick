"""Core data models for three-tier prompt configuration.

Defines enums, frozen dataclasses, and the error type shared across
the prompt configuration subsystem.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from maverick.exceptions.config import ConfigError

GENERIC_PROVIDER: str = "__generic__"
"""Sentinel provider value meaning 'any/default provider'."""


class OverridePolicy(str, Enum):
    """Governs what kind of user override a step allows."""

    AUGMENT_ONLY = "augment_only"
    """Only prompt_suffix is allowed. Full replacement via prompt_file is rejected."""

    REPLACE = "replace"
    """Both prompt_suffix and prompt_file are allowed."""


class PromptSource(str, Enum):
    """Describes how the final prompt was resolved."""

    DEFAULT = "default"
    """Registry default with no user override."""

    SUFFIX = "suffix"
    """Registry default + user-supplied suffix appended."""

    FILE = "file"
    """Full replacement from a user-supplied prompt_file."""

    PROVIDER_VARIANT = "provider-variant"
    """Provider-specific default was selected (no user override applied)."""


@dataclass(frozen=True, slots=True)
class PromptEntry:
    """A single prompt registered in the PromptRegistry.

    Attributes:
        text: Default prompt/instructions text.
        policy: Override policy governing user customization.
        provider: Provider key; defaults to GENERIC_PROVIDER.
        is_template: Whether text contains $-variable placeholders.
    """

    text: str
    policy: OverridePolicy
    provider: str = GENERIC_PROVIDER
    is_template: bool = False


@dataclass(frozen=True, slots=True)
class PromptResolution:
    """Result of resolve_prompt() — the final resolved prompt with metadata.

    Attributes:
        text: The final resolved prompt string.
        source: How the prompt was resolved.
        step_name: The step name this resolution was for.
        provider: The provider that was matched in the registry.
        override_applied: Whether a user override was applied.
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


class PromptConfigError(ConfigError):
    """Raised for prompt configuration or resolution errors."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
    ) -> None:
        super().__init__(message, field=field, value=value)
