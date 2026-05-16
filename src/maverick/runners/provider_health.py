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

from maverick.logging import get_logger
from maverick.runners.preflight import ValidationResult

__all__ = [
    "ProviderHealthCheck",
    "build_provider_health_checks",
    "providers_for_fly",
    "providers_referenced_by_actors",
]

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Provider-name extraction (no runtime deps)
# ---------------------------------------------------------------------------


def _providers_from_agents(config: Any) -> dict[str, set[str]]:
    """Walk ``config.agents.<role>`` → ``{provider: {model_id, ...}}``.

    The airframe-canonical config surface. Each populated role
    contributes its binding's ``(provider, model_id)`` to the result.
    """
    out: dict[str, set[str]] = {}
    agents = getattr(config, "agents", None)
    if agents is None:
        return out
    for role in ("implement", "review", "briefing", "decompose", "generate"):
        binding = getattr(agents, role, None)
        if binding is None:
            continue
        out.setdefault(binding.provider, set()).add(binding.model_id)
    return out


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
    seen |= set(_providers_from_agents(config).keys())
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
        models_to_validate: Model IDs that must appear in the adapter's
            catalogue. Empty means "just check the adapter answers".
        timeout: Maximum seconds for ``list_models``.
    """

    provider_name: str
    models_to_validate: frozenset[str] = field(default_factory=frozenset)
    timeout: float = 30.0

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


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_provider_health_checks(
    config: Any,
    *,
    timeout: float | None = None,
    provider_filter: set[str] | frozenset[str] | None = None,
) -> list[ProviderHealthCheck]:
    """Build one health check per provider referenced in ``config.agents``.

    Each populated ``agents.<role>`` contributes its binding's
    ``(provider, model_id)``; the result is one check per unique
    provider with the model_ids it's expected to serve. ``timeout``
    defaults to 30s — generous so a slow provider catalogue doesn't
    fail an otherwise-healthy check.
    """
    if timeout is None:
        timeout = 30.0

    provider_models = _providers_from_agents(config)
    return [
        ProviderHealthCheck(
            provider_name=name,
            models_to_validate=frozenset(models),
            timeout=timeout,
        )
        for name, models in sorted(provider_models.items())
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
