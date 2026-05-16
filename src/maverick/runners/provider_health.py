"""Airframe-backed provider health checks.

For each configured provider name, the check instantiates the matching
:class:`airframe.AgentRuntime` adapter, calls
:meth:`AgentRuntime.list_models`, and verifies:

1. The adapter can be constructed (matching ``airframe-agents`` extra is
   installed) and ``list_models`` succeeds (credentials present + vendor
   reachable).
2. Every model the user references — provider default, global
   ``model.model_id``, per-agent overrides — appears in the adapter's
   live catalogue.

Used by ``maverick doctor`` and the workflow preflights. The class
names ``OpenCodeProviderHealthCheck`` / ``AcpProviderHealthCheck`` and
the ``test_mcp_tool_call`` argument are kept for source compatibility
with legacy callers; both delegate to the same airframe-based probe.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

import airframe
from airframe.errors import AgentRuntimeError

from maverick.config import AgentProviderConfig
from maverick.logging import get_logger
from maverick.runners.preflight import ValidationResult

__all__ = [
    "AcpProviderHealthCheck",
    "OpenCodeProviderHealthCheck",
    "ProviderHealthCheck",
    "build_provider_health_checks",
    "providers_for_fly",
    "providers_referenced_by_actors",
]

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Provider-name extraction (no runtime deps)
# ---------------------------------------------------------------------------


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


def providers_for_fly(config: Any) -> set[str]:
    """Union of every provider ``maverick fly`` may route through."""
    seen: set[str] = set()
    seen |= providers_referenced_by_actors(config, "fly")
    default = _default_provider_name(config)
    if default:
        seen.add(default)
    return seen


# ---------------------------------------------------------------------------
# Airframe-backed health check
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProviderHealthCheck:
    """Probe one provider via :func:`airframe.runtime_for` + ``list_models``.

    A successful :meth:`list_models` call means: the adapter's vendor SDK
    is installed, credentials are present, and the vendor is reachable.

    Args:
        provider_name: Airframe canonical provider id
            (``claude`` / ``github-copilot`` / ``codex`` / ``opencode``).
        provider_config: Configuration; kept for source compatibility
            with the legacy doctor surface.
        models_to_validate: Model IDs that must appear in the adapter's
            catalogue. Empty means "just check the adapter answers".
        timeout: Maximum seconds for ``list_models``.
        test_mcp_tool_call: Preserved for source compatibility — no-op
            under airframe; structured-output round-trip is exercised
            by the agent layer, not by this probe.
    """

    provider_name: str
    provider_config: AgentProviderConfig
    models_to_validate: frozenset[str] = field(default_factory=frozenset)
    timeout: float = 30.0
    test_mcp_tool_call: bool = False

    async def validate(self) -> ValidationResult:
        """Run the health check.

        Args/Returns/Raises: see class docstring.
        """
        component = f"airframe:{self.provider_name}"
        start_time = time.monotonic()

        try:
            runtime_cls = airframe.runtime_for(self.provider_name)
        except ImportError as exc:
            return ValidationResult(
                success=False,
                component=component,
                errors=(f"Adapter for provider '{self.provider_name}' not installed: {exc}",),
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )
        except ValueError as exc:
            return ValidationResult(
                success=False,
                component=component,
                errors=(f"Unknown airframe provider '{self.provider_name}': {exc}",),
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )

        runtime = runtime_cls()
        try:
            models = await asyncio.wait_for(runtime.list_models(), timeout=self.timeout)
        except (TimeoutError, AgentRuntimeError) as exc:
            return ValidationResult(
                success=False,
                component=component,
                errors=(
                    f"Failed to enumerate models for '{self.provider_name}': {exc}. "
                    f"If credentials are missing, run the provider's login flow.",
                ),
                duration_ms=int((time.monotonic() - start_time) * 1000),
            )
        finally:
            try:
                await runtime.close()
            except Exception:  # noqa: BLE001
                pass

        catalogue = {m.id for m in models}
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


#: Backwards-compatible aliases. The names are misleading now (the
#: check runs through airframe, not OpenCode or ACP), but renaming
#: them would break imports across the codebase and downstream tooling.
OpenCodeProviderHealthCheck = ProviderHealthCheck
AcpProviderHealthCheck = ProviderHealthCheck


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_provider_health_checks(
    config: Any,
    *,
    timeout: float | None = None,
    test_mcp_tool_call: bool = False,
    provider_filter: set[str] | frozenset[str] | None = None,
) -> list[ProviderHealthCheck]:
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
    del test_mcp_tool_call  # legacy flag, no longer load-bearing
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

    items = sorted(config.agent_providers.items())
    return [
        ProviderHealthCheck(
            provider_name=name,
            provider_config=pcfg,
            models_to_validate=frozenset(provider_models.get(name, set())),
            timeout=timeout,
        )
        for name, pcfg in items
        if provider_filter is None or name in provider_filter
    ]


async def run_provider_health_checks(
    checks: list[ProviderHealthCheck],
) -> list[ValidationResult]:
    """Run every check concurrently.

    Each check is independent — there's no shared subprocess to
    amortise like the legacy OpenCode-backed probe had — so we
    simply gather them.
    """
    if not checks:
        return []
    return await asyncio.gather(*(check.validate() for check in checks))
