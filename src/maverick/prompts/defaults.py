"""Build the default PromptRegistry from shipped agent prompts."""

from __future__ import annotations

from maverick.prompts.models import GENERIC_PROVIDER, OverridePolicy, PromptEntry
from maverick.prompts.registry import PromptRegistry

_cached_registry: PromptRegistry | None = None


def build_default_registry() -> PromptRegistry:
    """Build the default PromptRegistry from shipped agent prompts.

    Imports prompt constants from agent modules by reference (no duplication).
    Each entry declares its override policy. The result is cached at module level
    so subsequent calls return the same registry.

    Returns:
        A fully populated, immutable PromptRegistry.
    """
    global _cached_registry
    if _cached_registry is not None:
        return _cached_registry
    # Lazy imports to avoid circular dependencies
    from maverick.agents.curator import SYSTEM_PROMPT as CURATOR_SYSTEM_PROMPT
    from maverick.agents.fixer import FIXER_SYSTEM_PROMPT
    from maverick.agents.implementer import IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE
    from maverick.agents.reviewers.completeness_reviewer import (
        COMPLETENESS_REVIEWER_PROMPT_TEMPLATE,
    )
    from maverick.agents.reviewers.correctness_reviewer import (
        CORRECTNESS_REVIEWER_PROMPT_TEMPLATE,
    )

    entries: dict[tuple[str, str], PromptEntry] = {
        ("implement", GENERIC_PROVIDER): PromptEntry(
            text=IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE,
            policy=OverridePolicy.AUGMENT_ONLY,
            is_template=True,
        ),
        ("completeness_review", GENERIC_PROVIDER): PromptEntry(
            text=COMPLETENESS_REVIEWER_PROMPT_TEMPLATE,
            policy=OverridePolicy.AUGMENT_ONLY,
        ),
        ("correctness_review", GENERIC_PROVIDER): PromptEntry(
            text=CORRECTNESS_REVIEWER_PROMPT_TEMPLATE,
            policy=OverridePolicy.AUGMENT_ONLY,
        ),
        ("fix", GENERIC_PROVIDER): PromptEntry(
            text=FIXER_SYSTEM_PROMPT,
            policy=OverridePolicy.AUGMENT_ONLY,
        ),
        ("curator", GENERIC_PROVIDER): PromptEntry(
            text=CURATOR_SYSTEM_PROMPT,
            policy=OverridePolicy.AUGMENT_ONLY,
        ),
    }

    _cached_registry = PromptRegistry(entries)
    return _cached_registry


def _clear_registry_cache() -> None:
    """Clear the cached registry. For testing only."""
    global _cached_registry
    _cached_registry = None
