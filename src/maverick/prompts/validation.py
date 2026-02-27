"""Startup validation for prompt configuration."""

from __future__ import annotations

from pathlib import Path

from maverick.prompts.config import PromptOverrideConfig
from maverick.prompts.models import PromptConfigError
from maverick.prompts.registry import PromptRegistry


def validate_prompt_config(
    prompts: dict[str, PromptOverrideConfig],
    registry: PromptRegistry,
    project_root: Path,
) -> None:
    """Validate all prompt overrides in the config at startup.

    Checks:
    - All step names exist in the registry.
    - Override policy is not violated.
    - All prompt_file paths exist, are readable, and are within project_root.

    Args:
        prompts: The prompts: section from MaverickConfig.
        registry: The PromptRegistry to validate against.
        project_root: Project root for file path validation.

    Raises:
        PromptConfigError: On the first validation failure found.
    """
    registered = registry.step_names()

    for step_name, override in prompts.items():
        # Check step name exists
        if step_name not in registered:
            raise PromptConfigError(f"'{step_name}' is not a registered step name")

        # Check policy compliance
        registry.validate_override(step_name, override)

        # Check prompt_file path
        if override.prompt_file is not None:
            _validate_file_path(override.prompt_file, project_root)


def _validate_file_path(prompt_file: str, project_root: Path) -> None:
    """Validate a prompt_file path is safe and accessible.

    Args:
        prompt_file: Relative path to the prompt file.
        project_root: Project root directory.

    Raises:
        PromptConfigError: If path is invalid, outside root, or missing.
    """
    if Path(prompt_file).is_absolute():
        raise PromptConfigError(
            f"Absolute paths are not allowed for prompt_file: {prompt_file}"
        )

    file_path = project_root / prompt_file
    resolved_path = file_path.resolve()
    project_root_resolved = project_root.resolve()

    try:
        resolved_path.relative_to(project_root_resolved)
    except ValueError as err:
        raise PromptConfigError(
            f"Prompt file must be within project root: {prompt_file}"
        ) from err

    if not resolved_path.is_file():
        raise PromptConfigError(f"Prompt file not found: {resolved_path}")
