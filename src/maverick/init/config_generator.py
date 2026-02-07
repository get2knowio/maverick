"""Configuration generation for maverick init command.

This module provides functions for generating InitConfig from detection results
and git information, and writing the configuration to disk.
"""

from __future__ import annotations

from pathlib import Path

from maverick.exceptions.init import ConfigExistsError, ConfigWriteError
from maverick.init.models import (
    GitRemoteInfo,
    InitConfig,
    InitGitHubConfig,
    InitModelConfig,
    InitValidationConfig,
    ProjectDetectionResult,
    ProjectType,
    ValidationCommands,
)

__all__ = [
    "generate_config",
    "write_config",
]


def generate_config(
    git_info: GitRemoteInfo,
    detection: ProjectDetectionResult | None,
    project_type: ProjectType | None = None,
    model_id: str | None = None,
) -> InitConfig:
    """Generate InitConfig from detection results and git info.

    Creates a complete InitConfig based on project detection results,
    git remote information, and optional explicit project type.

    Args:
        git_info: Parsed git remote information containing owner/repo.
        detection: Project detection result, or None if detection was skipped.
        project_type: Optional explicit project type override. If provided,
            this type's defaults are used instead of detection.primary_type.
        model_id: Optional Claude model ID to use. If not provided, uses default.

    Returns:
        Complete InitConfig ready for serialization.

    Examples:
        >>> config = generate_config(
        ...     git_info=GitRemoteInfo(owner="acme", repo="project"),
        ...     detection=detection_result,
        ... )
        >>> print(config.github.owner)
        'acme'

        >>> config = generate_config(
        ...     git_info=GitRemoteInfo(),
        ...     detection=None,
        ...     project_type=ProjectType.NODEJS,
        ... )
        >>> print(config.validation.test_cmd)
        ['npm', 'test']

        >>> config = generate_config(
        ...     git_info=GitRemoteInfo(),
        ...     detection=None,
        ...     model_id="claude-opus-4-5-20251101",
        ... )
        >>> print(config.model.model_id)
        'claude-opus-4-5-20251101'
    """
    # Determine which project type to use for validation defaults
    if project_type is not None:
        effective_type = project_type
    elif detection is not None:
        effective_type = detection.primary_type
    else:
        # Fall back to Python defaults when no detection and no explicit type
        effective_type = ProjectType.PYTHON

    # Get validation commands for the effective project type
    validation_commands = ValidationCommands.for_project_type(effective_type)

    # Build GitHub config from git info
    github_config = InitGitHubConfig(
        owner=git_info.owner,
        repo=git_info.repo,
        default_branch="main",
    )

    # Build validation config from validation commands
    # Convert tuples to lists for Pydantic model compatibility
    validation_config = InitValidationConfig(
        sync_cmd=list(validation_commands.sync_cmd)
        if validation_commands.sync_cmd
        else None,
        format_cmd=list(validation_commands.format_cmd)
        if validation_commands.format_cmd
        else None,
        lint_cmd=list(validation_commands.lint_cmd)
        if validation_commands.lint_cmd
        else None,
        typecheck_cmd=list(validation_commands.typecheck_cmd)
        if validation_commands.typecheck_cmd
        else None,
        test_cmd=list(validation_commands.test_cmd)
        if validation_commands.test_cmd
        else None,
    )

    # Build model config with defaults or custom model_id
    model_config = InitModelConfig(model_id=model_id) if model_id else InitModelConfig()

    # Assemble complete config
    return InitConfig(
        project_type=effective_type.value,
        github=github_config,
        validation=validation_config,
        model=model_config,
    )


def write_config(
    config: InitConfig,
    output_path: Path,
    force: bool = False,
) -> None:
    """Write configuration to a file.

    Serializes the InitConfig to YAML format and writes it to the specified path.
    Raises ConfigExistsError if the file exists and force is False.

    Args:
        config: The configuration to write.
        output_path: Path where the configuration file should be written.
        force: If True, overwrite existing file. If False, raise error if exists.

    Raises:
        ConfigExistsError: If output_path exists and force is False.
        ConfigWriteError: If writing the file fails due to I/O errors.

    Examples:
        >>> write_config(config, Path("maverick.yaml"))

        >>> # Force overwrite existing file
        >>> write_config(config, Path("maverick.yaml"), force=True)
    """
    # Check if file exists and force is not set
    if output_path.exists() and not force:
        raise ConfigExistsError(output_path)

    # Write the config to file
    try:
        yaml_content = config.to_yaml()
        output_path.write_text(yaml_content)
    except OSError as e:
        raise ConfigWriteError(output_path, e) from e
