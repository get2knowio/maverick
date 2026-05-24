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

_AGENT_ROLE_ORDER: tuple[str, ...] = (
    "implement",
    "review",
    "briefing",
    "decompose",
    "generate",
)

_PROVIDER_FALLBACK_MODELS: dict[str, tuple[str, ...]] = {
    "claude": ("claude-sonnet-4-6", "claude-haiku-4-5"),
    "github-copilot": ("gpt-5.3-codex", "gpt-5-mini"),
    "opencode": ("claude-sonnet-4-6",),
    "opencode-go": ("minimax-m2.7",),
}


def generate_config(
    git_info: GitRemoteInfo,
    detection: ProjectDetectionResult | None,
    project_type: ProjectType | None = None,
    provider_discovery: ProviderDiscoveryResult | None = None,
    selected_provider_ids: tuple[str, ...] | None = None,
    model_specs: dict[str, tuple[str, ...]] | None = None,
) -> InitConfig:
    """Generate :class:`InitConfig` from detection + git + provider discovery.

    Args:
        git_info: Parsed git remote information (owner/repo).
        detection: Project detection result, or ``None`` if detection
            was skipped (e.g. explicit ``project_type`` override).
        project_type: Explicit project type override; takes precedence
            over ``detection.primary_type``.
        provider_discovery: Airframe discovery result. Used as a
            fallback source for provider/model defaults when explicit
            flags are not supplied.
        selected_provider_ids: Explicit provider ids from ``--providers``.
            When present, the generated ``agents:`` block is spread
            across these providers.
        model_specs: Explicit provider → model list from ``--models``.
            Provider ids here also participate in the generated spread
            when ``selected_provider_ids`` is absent.

    Returns:
        Complete :class:`InitConfig` ready for serialization.
    """
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

    agents = _agents_from_provider_selection(
        provider_discovery=provider_discovery,
        selected_provider_ids=selected_provider_ids,
        model_specs=model_specs,
    )

    if agents is not None:
        return InitConfig(
            project_type=effective_type.value,
            github=github_config,
            validation=validation_config,
            agents=agents,
        )

    return InitConfig(
        project_type=effective_type.value,
        github=github_config,
        validation=validation_config,
    )


def _agents_from_provider_selection(
    *,
    provider_discovery: ProviderDiscoveryResult | None,
    selected_provider_ids: tuple[str, ...] | None,
    model_specs: dict[str, tuple[str, ...]] | None,
) -> dict[str, dict[str, str]] | None:
    """Build the generated ``agents:`` block from Airframe selection."""
    specs = model_specs or {}

    if selected_provider_ids is not None:
        provider_ids = selected_provider_ids
    elif specs:
        provider_ids = tuple(specs)
    elif provider_discovery and provider_discovery.providers:
        provider_ids = tuple(provider.provider_id for provider in provider_discovery.providers)
    else:
        return None

    if not provider_ids:
        return None

    discovery_by_id = {
        provider.provider_id: provider
        for provider in (provider_discovery.providers if provider_discovery else ())
    }
    provider_models: dict[str, tuple[str, ...]] = {}
    for provider_id in provider_ids:
        if provider_id in specs:
            provider_models[provider_id] = specs[provider_id]
            continue
        discovered = discovery_by_id.get(provider_id)
        if discovered and discovered.default_model_id:
            provider_models[provider_id] = (discovered.default_model_id,)
            continue
        provider_models[provider_id] = _PROVIDER_FALLBACK_MODELS.get(provider_id, ("default",))

    assignments: dict[str, dict[str, str]] = {}
    model_offsets: dict[str, int] = dict.fromkeys(provider_ids, 0)
    for index, role in enumerate(_AGENT_ROLE_ORDER):
        provider_id = provider_ids[index % len(provider_ids)]
        models = provider_models[provider_id]
        model_index = model_offsets[provider_id] % len(models)
        assignments[role] = {
            "provider": provider_id,
            "model_id": models[model_index],
        }
        model_offsets[provider_id] += 1

    return assignments


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
