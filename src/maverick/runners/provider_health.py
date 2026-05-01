"""Provider health checks (slimmed for the OpenCode runtime).

The legacy ACP-based health probe (spawn the bridge, run an
``initialize`` handshake, fire a tiny prompt, optionally exercise the
MCP gateway) was deleted with the ACP path. This stub keeps the public
surface — :func:`build_provider_health_checks`, :class:`AcpProviderHealthCheck`,
:func:`providers_for_fly` — so ``maverick doctor`` and the workflow
preflights still run, but the per-provider check is now reduced to:

* binary on PATH exists, and
* command list is non-empty.

Phase 6 of the OpenCode migration (see
``.claude/scratchpads/opencode-substrate-migration.md``) replaces this
file with a real OpenCode probe (``GET /provider`` + ``connected``
membership check). The class name ``AcpProviderHealthCheck`` and the
``test_mcp_tool_call`` argument are kept for source compatibility with
existing callers.
"""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from typing import Any

from maverick.config import AgentProviderConfig
from maverick.logging import get_logger
from maverick.runners.preflight import ValidationResult

__all__ = [
    "AcpProviderHealthCheck",
    "build_provider_health_checks",
    "providers_for_fly",
    "providers_referenced_by_actors",
    "providers_referenced_by_agents",
]

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Provider-name extraction (no ACP deps)
# ---------------------------------------------------------------------------


_FLY_AGENT_ROLES: tuple[str, ...] = ("implementer", "reviewer", "briefing")


def _default_provider_name(config: Any) -> str | None:
    """Return the name of the default provider in ``config.agent_providers``."""
    for name, pcfg in config.agent_providers.items():
        if getattr(pcfg, "default", False):
            return name
    if config.agent_providers:
        return next(iter(config.agent_providers))
    return None


def providers_referenced_by_actors(config: Any, workflow: str) -> set[str]:
    """Return the providers named under ``actors.<workflow>.*.provider``."""
    providers: set[str] = set()
    block = config.actors.get(workflow, {}) or {}
    for actor_cfg in block.values():
        if not isinstance(actor_cfg, dict):
            continue
        if actor_cfg.get("provider"):
            providers.add(actor_cfg["provider"])
        tiers = actor_cfg.get("tiers")
        if isinstance(tiers, dict):
            for tier_cfg in tiers.values():
                if isinstance(tier_cfg, dict) and tier_cfg.get("provider"):
                    providers.add(tier_cfg["provider"])
    return providers


def providers_referenced_by_agents(config: Any, roles: tuple[str, ...]) -> set[str]:
    """Return the providers named in legacy ``agents.<role>.provider``."""
    providers: set[str] = set()
    for role in roles:
        agent_cfg = config.agents.get(role)
        if agent_cfg is not None and getattr(agent_cfg, "provider", None):
            providers.add(agent_cfg.provider)
    return providers


def providers_for_fly(config: Any) -> set[str]:
    """Union of every provider ``maverick fly`` may route through."""
    seen: set[str] = set()
    seen |= providers_referenced_by_actors(config, "fly")
    seen |= providers_referenced_by_agents(config, _FLY_AGENT_ROLES)
    default = _default_provider_name(config)
    if default:
        seen.add(default)
    return seen


# ---------------------------------------------------------------------------
# Stub health check
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AcpProviderHealthCheck:
    """Slim binary-presence check.

    Returns ``success=True`` when the provider command's first arg
    resolves on ``$PATH`` and the command list is non-empty. Doesn't
    spawn the binary, doesn't run any handshake. Phase 6 reconstitutes
    this against OpenCode's :http:`/provider` endpoint.
    """

    provider_name: str
    provider_config: AgentProviderConfig
    models_to_validate: frozenset[str] = frozenset()
    timeout: float = 15.0
    test_mcp_tool_call: bool = False

    async def validate(self) -> ValidationResult:
        start_time = time.monotonic()
        component = f"ACP:{self.provider_name}"

        command_args = self.provider_config.command
        if not command_args:
            return ValidationResult(
                success=False,
                component=component,
                errors=(f"Provider '{self.provider_name}' has an empty command list",),
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        binary = command_args[0]
        if shutil.which(binary) is None:
            return ValidationResult(
                success=False,
                component=component,
                errors=(
                    f"Binary '{binary}' for provider '{self.provider_name}' not found on PATH",
                ),
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        return ValidationResult(
            success=True,
            component=component,
            duration_ms=int((time.monotonic() - start_time) * 1000),
        )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_provider_health_checks(
    config: Any,
    *,
    timeout: float | None = None,
    test_mcp_tool_call: bool = False,
    provider_filter: set[str] | frozenset[str] | None = None,
) -> list[AcpProviderHealthCheck]:
    """Build one :class:`AcpProviderHealthCheck` per configured provider.

    Args mirror the legacy signature so callers don't need to change.
    ``test_mcp_tool_call`` is preserved but ignored (Phase 6 will revisit).
    """
    del test_mcp_tool_call  # legacy flag, currently ignored

    if timeout is None:
        timeout = 15.0

    items = list(config.agent_providers.items())
    return [
        AcpProviderHealthCheck(
            provider_name=name,
            provider_config=pcfg,
            models_to_validate=frozenset(),
            timeout=timeout,
        )
        for name, pcfg in sorted(items)
        if provider_filter is None or name in provider_filter
    ]
