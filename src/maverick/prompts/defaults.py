"""Build the default PromptRegistry from shipped agent/generator prompts."""

from __future__ import annotations

from maverick.prompts.models import GENERIC_PROVIDER, OverridePolicy, PromptEntry
from maverick.prompts.registry import PromptRegistry

_cached_registry: PromptRegistry | None = None


def build_default_registry() -> PromptRegistry:
    """Build the default PromptRegistry from shipped agent/generator prompts.

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
    from maverick.agents.generators.bead_enricher import BEAD_ENRICHER_SYSTEM_PROMPT
    from maverick.agents.generators.commit_message import (
        COMMIT_MESSAGE_SYSTEM_PROMPT,
    )
    from maverick.agents.generators.dependency_extractor import (
        DEPENDENCY_EXTRACTOR_SYSTEM_PROMPT,
    )
    from maverick.agents.generators.pr_description import PRDescriptionGenerator
    from maverick.agents.generators.pr_title import PR_TITLE_SYSTEM_PROMPT
    from maverick.agents.implementer import IMPLEMENTER_SYSTEM_PROMPT_TEMPLATE
    from maverick.agents.reviewers.completeness_reviewer import (
        COMPLETENESS_REVIEWER_PROMPT_TEMPLATE,
    )
    from maverick.agents.reviewers.correctness_reviewer import (
        CORRECTNESS_REVIEWER_PROMPT_TEMPLATE,
    )

    # Get PR description default by instantiating with default sections
    pr_desc_gen = PRDescriptionGenerator()
    pr_desc_default = pr_desc_gen.system_prompt

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
        ("commit_message", GENERIC_PROVIDER): PromptEntry(
            text=COMMIT_MESSAGE_SYSTEM_PROMPT,
            policy=OverridePolicy.REPLACE,
        ),
        ("pr_description", GENERIC_PROVIDER): PromptEntry(
            text=pr_desc_default,
            policy=OverridePolicy.REPLACE,
        ),
        ("pr_title", GENERIC_PROVIDER): PromptEntry(
            text=PR_TITLE_SYSTEM_PROMPT,
            policy=OverridePolicy.REPLACE,
        ),
        ("dependency_extract", GENERIC_PROVIDER): PromptEntry(
            text=DEPENDENCY_EXTRACTOR_SYSTEM_PROMPT,
            policy=OverridePolicy.REPLACE,
        ),
        ("bead_enrich", GENERIC_PROVIDER): PromptEntry(
            text=BEAD_ENRICHER_SYSTEM_PROMPT,
            policy=OverridePolicy.REPLACE,
        ),
    }

    _cached_registry = PromptRegistry(entries)
    return _cached_registry


def _clear_registry_cache() -> None:
    """Clear the cached registry. For testing only."""
    global _cached_registry
    _cached_registry = None
