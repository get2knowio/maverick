"""Airframe runtime factory — `agents:` config block → constructed runtime.

Squadrons call :func:`runtime_for_agent` to materialise the
:class:`airframe.AgentRuntime` for a given role, optionally narrowed
to a per-complexity override pulled from
``actors.<workflow>.<actor>.tiers.<complexity>``.

Resolution order (highest → lowest):

1. ``binding_override`` — explicit binding the caller supplies. Used
   by squadrons to thread a complexity-tier override
   (``ImplementerTierConfig`` from
   :class:`maverick.config.ImplementerTiersConfig`) through to the
   factory.
2. ``agents.<role>`` from :class:`MaverickConfig.agents` — the role's
   default binding.

When neither layer supplies a binding, :class:`ValueError` is raised —
explicit failure is better than the legacy ``DEFAULT_TIERS`` fallback,
which silently picked a model the user hadn't authorised.

The factory dispatches via :func:`airframe.runtime_for`, so install-
state gating + `pip install airframe-agents[<extra>]` hints work
out of the box: a missing SDK surfaces as a clear ``ImportError`` here
rather than an opaque attribute error at execute time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import airframe

from maverick.config import AgentBindingConfig, AgentsConfig

if TYPE_CHECKING:
    from airframe.protocol import AgentRuntime, ProviderModel

__all__ = ["runtime_for_agent", "binding_for_role"]


#: Canonical role names — must match each agent's
#: ``provider_tier`` :class:`ClassVar`. Keeps the factory's allowed-roles
#: validation aligned with the agent surface.
KNOWN_ROLES: frozenset[str] = frozenset(
    {"implement", "review", "briefing", "decompose", "generate"}
)


def binding_for_role(
    role: str,
    *,
    agents_config: AgentsConfig,
    binding_override: AgentBindingConfig | None = None,
) -> AgentBindingConfig:
    """Resolve the effective :class:`AgentBindingConfig` for ``role``.

    Args:
        role: One of :data:`KNOWN_ROLES`.
        agents_config: The user's ``agents:`` block.
        binding_override: Optional explicit override (typically derived
            from a per-complexity tier config).

    Returns:
        The resolved binding.

    Raises:
        ValueError: When ``role`` is unknown, or neither layer supplies
            a binding for it.
    """
    if role not in KNOWN_ROLES:
        raise ValueError(f"Unknown agent role {role!r}. Pick one of {sorted(KNOWN_ROLES)}.")
    if binding_override is not None:
        return binding_override
    binding = getattr(agents_config, role, None)
    if binding is None:
        raise ValueError(
            f"No binding configured for role {role!r}. Set "
            f"agents.{role}.provider + .model_id in maverick.yaml."
        )
    return binding


def runtime_for_agent(
    role: str,
    *,
    agents_config: AgentsConfig,
    binding_override: AgentBindingConfig | None = None,
) -> tuple[AgentRuntime, ProviderModel]:
    """Build the airframe runtime for ``role`` and the resolved binding.

    The returned runtime is constructed with ``model=binding.model_id``
    so per-call ``execute()`` honours the role's binding without the
    caller having to thread ``ProviderModel`` through every send.

    Args:
        role: One of :data:`KNOWN_ROLES`.
        agents_config: The user's ``agents:`` block.
        binding_override: Optional explicit override (per-complexity
            actor tier, inline workflow override, etc.).

    Returns:
        A two-tuple ``(runtime, provider_model)``. ``provider_model``
        is the canonical :class:`airframe.ProviderModel`; callers can
        pass it to :meth:`AgentRuntime.execute` if they want to make
        the binding explicit at the call site.

    Raises:
        ValueError: No binding configured for ``role``.
        ImportError: The provider's adapter SDK isn't installed.
            Error message names the right ``pip install
            airframe-agents[<extra>]`` command.
        UnsupportedBindingError: The adapter loaded for ``binding.provider``
            doesn't satisfy the binding (typically a model the adapter
            explicitly rejects — e.g. CopilotRuntime won't serve
            ``claude-*`` model ids). Surfaced here instead of at the
            first :meth:`AgentRuntime.execute` so a misconfigured
            ``agents:`` block fails at squadron-open with a clear
            cause rather than mid-workflow.
    """
    from airframe.protocol import ProviderModel, UnsupportedBindingError

    binding = binding_for_role(
        role,
        agents_config=agents_config,
        binding_override=binding_override,
    )
    runtime_cls = airframe.runtime_for(binding.provider)
    runtime = runtime_cls(model=binding.model_id)
    provider_model = ProviderModel(binding.provider, binding.model_id)
    if not runtime.validate_binding(provider_model):
        raise UnsupportedBindingError(
            f"Provider {binding.provider!r} adapter {type(runtime).__name__} "
            f"rejected model {binding.model_id!r} for role {role!r}. "
            f"Check ``agents.{role}`` in maverick.yaml."
        )
    return runtime, provider_model
