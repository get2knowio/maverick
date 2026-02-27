"""Three-tier prompt configuration system.

Provides default prompt registry, resolution with user overrides
(suffix/file), and provider-specific variants.
"""

from __future__ import annotations

from maverick.prompts.config import PromptOverrideConfig
from maverick.prompts.defaults import build_default_registry
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
from maverick.prompts.validation import validate_prompt_config

__all__ = [
    "GENERIC_PROVIDER",
    "OverridePolicy",
    "PromptConfigError",
    "PromptEntry",
    "PromptOverrideConfig",
    "PromptRegistry",
    "PromptResolution",
    "PromptSource",
    "build_default_registry",
    "resolve_prompt",
    "validate_prompt_config",
]
