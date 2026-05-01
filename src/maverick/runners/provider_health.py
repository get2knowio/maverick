"""Provider health checks against the OpenCode runtime.

Each check spawns (or shares) an ``opencode serve`` subprocess, calls
``GET /provider``, and verifies that:

1. The configured provider name is in OpenCode's ``connected`` list (the
   server has valid auth for it via ``opencode auth login``).
2. Every model the user references — provider default, global
   ``model.model_id``, per-agent overrides — appears in that provider's
   catalogue.

Used by ``maverick doctor`` and the workflow preflights. Class name
``AcpProviderHealthCheck`` and the ``test_mcp_tool_call`` argument are
kept for source compatibility with the legacy callers; both delegate
through to the OpenCode probe.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from maverick.config import AgentProviderConfig
from maverick.logging import get_logger
from maverick.runners.preflight import ValidationResult
from maverick.runtime.opencode import (
    OpenCodeError,
    OpenCodeServerHandle,
    client_for,
    list_connected_providers,
    opencode_server,
)

__all__ = [
    "AcpProviderHealthCheck",
    "OpenCodeProviderHealthCheck",
    "build_provider_health_checks",
    "providers_for_fly",
    "providers_referenced_by_actors",
    "providers_referenced_by_agents",
]

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Provider-name extraction (no runtime deps)
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
# OpenCode-backed health check
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OpenCodeProviderHealthCheck:
    """Probe one provider against an OpenCode server's ``/provider`` response.

    Fast: spawns a server, hits one HTTP endpoint, terminates. The server
    spawn cost (~0.5-1s) dominates; the actual check is sub-millisecond.
    For multi-provider checks pass a shared ``handle`` so the spawn cost
    is paid once.

    Args:
        provider_name: Logical provider name (e.g. ``"openrouter"``).
        provider_config: Provider configuration. Currently only used to
            surface a meaningful error message when the binary isn't on
            PATH; the probe itself reaches OpenCode, not the bridge.
        models_to_validate: Model IDs that must appear in the provider's
            catalogue. Empty means "just check the provider is connected".
        timeout: Maximum seconds for the entire check.
        test_mcp_tool_call: Preserved for source compatibility with the
            legacy ACP doctor flag. Currently a no-op — OpenCode's
            ``StructuredOutput`` tool-forcing makes a per-provider tool
            probe redundant.
    """

    provider_name: str
    provider_config: AgentProviderConfig
    models_to_validate: frozenset[str] = frozenset()
    timeout: float = 30.0
    test_mcp_tool_call: bool = False

    async def validate(self, handle: OpenCodeServerHandle | None = None) -> ValidationResult:
        """Run the health check.

        Args:
            handle: Optional pre-spawned OpenCode server handle. When
                ``None``, the check spawns its own server and tears it
                down on exit. Doctor / preflight callers SHOULD pass a
                shared handle so multi-provider checks don't pay the
                spawn cost N times.
        """
        component = f"OpenCode:{self.provider_name}"
        start_time = time.monotonic()

        if handle is None:
            try:
                async with opencode_server() as owned_handle:
                    return await self._validate_with_handle(owned_handle, component, start_time)
            except OpenCodeError as exc:
                return ValidationResult(
                    success=False,
                    component=component,
                    errors=(f"OpenCode subprocess spawn failed: {exc}",),
                    duration_ms=int((time.monotonic() - start_time) * 1000),
                )
        return await self._validate_with_handle(handle, component, start_time)

    async def _validate_with_handle(
        self,
        handle: OpenCodeServerHandle,
        component: str,
        start_time: float,
    ) -> ValidationResult:
        client = client_for(handle, timeout=self.timeout)
        try:
            connected = await asyncio.wait_for(
                list_connected_providers(client), timeout=self.timeout
            )
        except (TimeoutError, OpenCodeError) as exc:
            return ValidationResult(
                success=False,
                component=component,
                errors=(f"Failed to query OpenCode /provider for '{self.provider_name}': {exc}",),
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )
        finally:
            await client.aclose()

        if self.provider_name not in connected:
            available = ", ".join(sorted(connected.keys())) or "(none)"
            return ValidationResult(
                success=False,
                component=component,
                errors=(
                    f"Provider '{self.provider_name}' is not connected on "
                    f"the OpenCode server. Run "
                    f"`opencode auth login {self.provider_name}` to add an "
                    f"API key. Connected providers: {available}.",
                ),
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        catalogue = connected[self.provider_name]
        missing = sorted(self.models_to_validate - catalogue)
        if missing:
            sample = sorted(catalogue)[:8]
            return ValidationResult(
                success=False,
                component=component,
                errors=(
                    f"Models {missing!r} are not available on provider "
                    f"'{self.provider_name}'. Sample of available models: "
                    f"{sample}.",
                ),
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        return ValidationResult(
            success=True,
            component=component,
            duration_ms=int((time.monotonic() - start_time) * 1000),
        )


#: Backwards-compatible alias. The class name is misleading now (the
#: check no longer touches ACP), but renaming the public symbol would
#: break ``maverick.runners.provider_health.AcpProviderHealthCheck``
#: imports across docstrings, tests, and downstream tooling.
AcpProviderHealthCheck = OpenCodeProviderHealthCheck


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_provider_health_checks(
    config: Any,
    *,
    timeout: float | None = None,
    test_mcp_tool_call: bool = False,
    provider_filter: set[str] | frozenset[str] | None = None,
) -> list[OpenCodeProviderHealthCheck]:
    """Build one health check per configured provider.

    The result mirrors :class:`AgentProviderRegistry`'s shape: every
    entry in ``config.agent_providers`` produces a check, optionally
    filtered to ``provider_filter``. Each check's ``models_to_validate``
    is the union of:

    * the provider's ``default_model``,
    * for the default provider only: the global ``config.model.model_id``
      (when explicitly set) and any per-agent ``model_id`` overrides.

    ``timeout`` defaults to 30s — generous so a slow provider catalogue
    doesn't fail an otherwise-healthy check.
    """
    del test_mcp_tool_call  # legacy flag, currently ignored
    if timeout is None:
        timeout = 30.0

    default_provider = _default_provider_name(config)
    provider_models: dict[str, set[str]] = {}
    for name, pcfg in config.agent_providers.items():
        models: set[str] = set()
        if pcfg.default_model:
            models.add(pcfg.default_model)
        provider_models[name] = models

    if default_provider:
        # Global ``model.model_id`` only counts when the user explicitly
        # set it — the Pydantic default is a Claude alias, meaningless
        # for non-Claude providers.
        if "model_id" in config.model.model_fields_set and config.model.model_id:
            provider_models.setdefault(default_provider, set()).add(config.model.model_id)
        for agent_cfg in config.agents.values():
            if getattr(agent_cfg, "model_id", None):
                provider_models.setdefault(default_provider, set()).add(agent_cfg.model_id)

    items = sorted(config.agent_providers.items())
    return [
        OpenCodeProviderHealthCheck(
            provider_name=name,
            provider_config=pcfg,
            models_to_validate=frozenset(provider_models.get(name, set())),
            timeout=timeout,
        )
        for name, pcfg in items
        if provider_filter is None or name in provider_filter
    ]


async def run_provider_health_checks(
    checks: list[OpenCodeProviderHealthCheck],
) -> list[ValidationResult]:
    """Run every check against ONE shared OpenCode subprocess.

    Pays the spawn cost once instead of N times. Use this whenever
    you have multiple checks to run; the per-check ``validate()`` API
    is preserved for one-shot callers.
    """
    if not checks:
        return []
    async with opencode_server() as handle:
        return await asyncio.gather(*(check.validate(handle) for check in checks))
