"""Configuration generation for ``maverick init``.

Builds an ``InitConfig`` from project detection, git remote info, and
OpenCode provider discovery. The generator writes:

* ``project_type``, ``github`` — from detection + git parsing.
* ``validation`` — language defaults from the detected project type.
* ``model`` — optional global default model id (rare; tier cascades
  drive routing now).
* ``agent_providers`` — one entry per provider returned by
  ``GET /provider`` (the OpenCode runtime's ``connected[]`` list).
  Used by ``maverick doctor`` for health checks.
* ``provider_tiers`` — the cross-provider cascade ``DEFAULT_TIERS``
  baked into the generated yaml, so users see the routing decisions
  and can edit them per project.

The legacy PATH-based ACP probe + ``actors:`` auto-distribution were
deleted in the OpenCode-substrate cleanup. The runtime resolves
``provider_tiers`` from the yaml directly; per-actor overrides go
under ``actors.<workflow>.<actor>``, written manually when needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
from maverick.init.opencode_discovery import OpenCodeDiscoveryResult
from maverick.runtime.opencode import DEFAULT_TIERS

__all__ = [
    "generate_config",
    "write_config",
]


def _provider_tiers_block() -> dict[str, list[dict[str, str]]]:
    """Serialize :data:`DEFAULT_TIERS` into yaml-shaped dicts.

    Mirrors the schema ``maverick.config::ProviderTiersConfig.tiers``
    expects: ``{tier_name: [{provider, model_id}, ...]}``. Putting the
    cascade in the user's yaml at init time means the user sees the
    routing decisions and can edit them per project without spelunking
    through the runtime defaults.
    """
    return {
        name: [{"provider": b.provider_id, "model_id": b.model_id} for b in tier.bindings]
        for name, tier in DEFAULT_TIERS.items()
    }


def generate_config(
    git_info: GitRemoteInfo,
    detection: ProjectDetectionResult | None,
    project_type: ProjectType | None = None,
    model_id: str | None = None,
    provider_discovery: OpenCodeDiscoveryResult | None = None,
) -> InitConfig:
    """Generate :class:`InitConfig` from detection + git + provider discovery.

    Args:
        git_info: Parsed git remote information (owner/repo).
        detection: Project detection result, or ``None`` if detection
            was skipped (e.g. explicit ``project_type`` override).
        project_type: Explicit project type override; takes precedence
            over ``detection.primary_type``.
        model_id: Optional global default model id to embed at
            ``model.model_id``. Most projects leave this unset because
            tier cascades drive routing.
        provider_discovery: Result of querying OpenCode's
            ``/provider`` endpoint. When present, populates the
            ``agent_providers`` block with the connected providers and
            flags the highest-preference one as ``default: true``.

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

    model_config = InitModelConfig(model_id=model_id) if model_id else InitModelConfig()

    # agent_providers from /provider connected list. The first entry in
    # preference order (per OpenCodeDiscoveryResult sort) becomes the
    # default. When discovery failed (None) the block stays empty —
    # workflows still work via the runtime DEFAULT_TIERS, doctor just
    # has nothing to validate.
    agent_providers: dict[str, dict[str, Any]] = {}
    if provider_discovery is not None:
        for prov in provider_discovery.providers:
            agent_providers[prov.provider_id] = {
                "default": prov.provider_id == provider_discovery.default_provider_id,
            }

    return InitConfig(
        project_type=effective_type.value,
        github=github_config,
        validation=validation_config,
        model=model_config,
        agent_providers=agent_providers,
        provider_tiers={"tiers": _provider_tiers_block()},
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
