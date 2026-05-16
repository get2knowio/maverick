"""Configuration generation for ``maverick init``.

Builds an ``InitConfig`` from project detection, git remote info, and
airframe provider discovery. The generator writes:

* ``project_type``, ``github`` — from detection + git parsing.
* ``validation`` — language defaults from the detected project type.
* ``agents`` — per-role airframe bindings (one ``(provider, model_id)``
  per role). Baked into the generated yaml so users see the routing
  decisions and can edit them per project.

Per-actor overrides go under ``actors.<workflow>.<actor>``, written
manually when needed.
"""

from __future__ import annotations

from pathlib import Path

from maverick.exceptions.init import ConfigExistsError, ConfigWriteError
from maverick.init.models import (
    GitRemoteInfo,
    InitConfig,
    InitGitHubConfig,
    InitValidationConfig,
    ProjectDetectionResult,
    ProjectType,
    ValidationCommands,
)
from maverick.init.provider_discovery import ProviderDiscoveryResult

__all__ = [
    "generate_config",
    "write_config",
]


def generate_config(
    git_info: GitRemoteInfo,
    detection: ProjectDetectionResult | None,
    project_type: ProjectType | None = None,
    provider_discovery: ProviderDiscoveryResult | None = None,
) -> InitConfig:
    """Generate :class:`InitConfig` from detection + git + provider discovery.

    Args:
        git_info: Parsed git remote information (owner/repo).
        detection: Project detection result, or ``None`` if detection
            was skipped (e.g. explicit ``project_type`` override).
        project_type: Explicit project type override; takes precedence
            over ``detection.primary_type``.
        provider_discovery: Airframe discovery result. Surfaced to the
            caller for verbose console output; not currently written
            into the generated yaml (the ``agents:`` block is the
            canonical routing surface).

    Returns:
        Complete :class:`InitConfig` ready for serialization.
    """
    del provider_discovery  # surfaced to caller for verbose output; not written into yaml
    # Determine effective project type
    if project_type is not None:
        effective_type = project_type
    elif detection is not None:
        effective_type = detection.primary_type
    else:
        effective_type = ProjectType.PYTHON

    validation_commands = ValidationCommands.for_project_type(effective_type)

    github_config = InitGitHubConfig(
        owner=git_info.owner,
        repo=git_info.repo,
        default_branch="main",
    )

    validation_config = InitValidationConfig(
        sync_cmd=list(validation_commands.sync_cmd) if validation_commands.sync_cmd else None,
        format_cmd=list(validation_commands.format_cmd)
        if validation_commands.format_cmd
        else None,
        lint_cmd=list(validation_commands.lint_cmd) if validation_commands.lint_cmd else None,
        typecheck_cmd=list(validation_commands.typecheck_cmd)
        if validation_commands.typecheck_cmd
        else None,
        test_cmd=list(validation_commands.test_cmd) if validation_commands.test_cmd else None,
    )

    return InitConfig(
        project_type=effective_type.value,
        github=github_config,
        validation=validation_config,
    )


def write_config(
    config: InitConfig,
    output_path: Path,
    force: bool = False,
) -> None:
    """Write ``config`` to ``output_path`` as YAML.

    Raises :class:`ConfigExistsError` when the file exists and
    ``force=False``; :class:`ConfigWriteError` on I/O failure.
    """
    if output_path.exists() and not force:
        raise ConfigExistsError(output_path)

    try:
        yaml_content = config.to_yaml()
        output_path.write_text(yaml_content)
    except OSError as e:
        raise ConfigWriteError(output_path, e) from e
