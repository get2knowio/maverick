"""Prompt resolution with three-tier override support."""

from __future__ import annotations

from pathlib import Path
from string import Template
from typing import TYPE_CHECKING, Any

from maverick.logging import get_logger
from maverick.prompts.models import (
    GENERIC_PROVIDER,
    OverridePolicy,
    PromptConfigError,
    PromptResolution,
    PromptSource,
)
from maverick.prompts.registry import PromptRegistry

if TYPE_CHECKING:
    from maverick.prompts.config import PromptOverrideConfig

logger = get_logger(__name__)

_SUFFIX_SEPARATOR = "\n\n---\n\n## Project-Specific Instructions\n\n"


def _render_template(text: str, context: dict[str, Any]) -> str:
    """Apply safe_substitute template rendering."""
    return Template(text).safe_substitute(context)


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

    Resolution order:
    1. Select base prompt from registry using (step_name, provider) with
       fallback to (step_name, generic).
    2. If override.prompt_file is configured and step policy allows,
       use file contents as base.
    3. If override.prompt_suffix is configured, append to base with separator.

    Args:
        step_name: Canonical step/role name.
        registry: The immutable PromptRegistry.
        provider: Provider identifier for provider-specific variant lookup.
        override: User's prompt override config (from maverick.yaml).
        project_root: Project root for resolving relative prompt_file paths.
        render_context: Template variables for safe_substitute rendering.

    Returns:
        PromptResolution with the final text and metadata.

    Raises:
        PromptConfigError: If step_name not in registry, policy violated,
            or prompt_file missing/outside project root.
    """
    # Step 1: Look up entry with provider fallback
    entry = registry.get(step_name, provider)

    # Determine source based on provider match
    if provider != GENERIC_PROVIDER and registry.has(step_name, provider):
        source = PromptSource.PROVIDER_VARIANT
    else:
        source = PromptSource.DEFAULT
    matched_provider = entry.provider

    # Step 2: Get base text, apply template rendering if needed
    base_text = entry.text
    if entry.is_template and render_context:
        base_text = _render_template(base_text, render_context)

    # Step 3: Apply override if present
    override_applied = False
    resolved_text = base_text

    if override is not None:
        prompt_file = getattr(override, "prompt_file", None)
        prompt_suffix = getattr(override, "prompt_suffix", None)

        if prompt_file is not None:
            # File replacement — validate policy
            if entry.policy == OverridePolicy.AUGMENT_ONLY:
                raise PromptConfigError(
                    f"Step '{step_name}' does not allow full prompt replacement "
                    f"(policy: augment_only)"
                )
            if project_root is None:
                raise PromptConfigError(
                    "project_root is required when prompt_file is configured"
                )
            if Path(prompt_file).is_absolute():
                raise PromptConfigError(
                    f"Absolute paths are not allowed for prompt_file: {prompt_file}"
                )
            file_path = Path(project_root) / prompt_file
            resolved_path = file_path.resolve()
            project_root_resolved = Path(project_root).resolve()
            try:
                resolved_path.relative_to(project_root_resolved)
            except ValueError as err:
                raise PromptConfigError(
                    f"Prompt file must be within project root: {prompt_file}"
                ) from err
            if not resolved_path.is_file():
                raise PromptConfigError(f"Prompt file not found: {resolved_path}")
            file_text = resolved_path.read_text()
            if entry.is_template and render_context:
                file_text = _render_template(file_text, render_context)
            resolved_text = file_text
            source = PromptSource.FILE
            override_applied = True

        elif prompt_suffix is not None:
            suffix = prompt_suffix
            if entry.is_template and render_context:
                suffix = _render_template(suffix, render_context)
            resolved_text = base_text + _SUFFIX_SEPARATOR + suffix
            source = PromptSource.SUFFIX
            override_applied = True

    resolution = PromptResolution(
        text=resolved_text,
        source=source,
        step_name=step_name,
        provider=matched_provider,
        override_applied=override_applied,
    )

    logger.debug(
        "prompt_resolved",
        step_name=step_name,
        provider=matched_provider,
        source=source.value,
        override_applied=override_applied,
    )

    return resolution
