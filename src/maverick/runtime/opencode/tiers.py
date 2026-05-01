"""Provider-tier resolution and cascade logic.

A "tier" is an ordered list of ``(provider_id, model_id)`` pairs an
actor will try in turn. The first entry is the preferred binding; the
rest are fallbacks engaged when the preferred binding fails for a
recoverable reason (auth, model-not-found, transient outage,
structured-output failure).

Each agentic actor declares a tier name in :class:`OpenCodeAgentMixin`
via ``provider_tier: ClassVar[str | None]``. The names are role-based
(``"review"``, ``"implement"``, ``"decompose"``, etc.) rather than
cost-banded — this keeps the per-actor declaration stable while letting
users tune the underlying model lists per role in
``maverick.yaml::provider_tiers``.

Defaults are set in :data:`DEFAULT_TIERS` and reflect the spike's
empirical reliability data: qwen3-coder for cheap-and-fast roles,
claude-haiku for typical mailbox work, claude-sonnet for frontier
reasoning. Users can override the entire mapping via config without
touching code.

Cost telemetry: every send through :func:`cascade_send` records the
``info.cost`` / ``info.tokens`` / ``info.modelID`` / ``info.providerID``
fields on the structured log and (optionally) a per-actor sink, so
``maverick fly`` runs can be aggregated without re-parsing trace logs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from maverick.logging import get_logger
from maverick.runtime.opencode.client import SendResult
from maverick.runtime.opencode.errors import (
    OpenCodeAuthError,
    OpenCodeContextOverflowError,
    OpenCodeError,
    OpenCodeModelNotFoundError,
    OpenCodeStructuredOutputError,
    OpenCodeTransientError,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProviderModel:
    """One ``(provider_id, model_id)`` binding within a tier."""

    provider_id: str
    model_id: str

    @property
    def label(self) -> str:
        return f"{self.provider_id}/{self.model_id}"

    def to_dict(self) -> dict[str, str]:
        return {"providerID": self.provider_id, "modelID": self.model_id}


@dataclass(frozen=True, slots=True)
class Tier:
    """Ordered cascade of bindings for a single actor role."""

    name: str
    bindings: tuple[ProviderModel, ...]

    def __post_init__(self) -> None:
        if not self.bindings:
            raise ValueError(f"Tier {self.name!r} must have at least one binding")


# ---------------------------------------------------------------------------
# Default mapping (spec table from the migration plan)
# ---------------------------------------------------------------------------


def _pm(provider: str, model: str) -> ProviderModel:
    return ProviderModel(provider_id=provider, model_id=model)


DEFAULT_TIERS: dict[str, Tier] = {
    # Reviewer/implementer in steady state: claude-haiku-4.5 has 100%
    # structured-output reliability with the envelope unwrap; qwen3-coder
    # is a cheaper open-weights fallback (also 100% in the spike).
    "review": Tier(
        "review",
        bindings=(
            _pm("openrouter", "anthropic/claude-haiku-4.5"),
            _pm("openrouter", "qwen/qwen3-coder"),
        ),
    ),
    "implement": Tier(
        "implement",
        bindings=(
            _pm("openrouter", "anthropic/claude-haiku-4.5"),
            _pm("openrouter", "qwen/qwen3-coder"),
            _pm("openrouter", "anthropic/claude-sonnet-4.5"),
        ),
    ),
    # Briefing agents are read-only, scoped tasks — qwen3-coder handles
    # them comfortably and is the cheapest reliable option.
    "briefing": Tier(
        "briefing",
        bindings=(
            _pm("openrouter", "qwen/qwen3-coder"),
            _pm("openrouter", "anthropic/claude-haiku-4.5"),
        ),
    ),
    # Decomposer outline + detail benefits from frontier reasoning;
    # the seeded-context cache benefit makes the more-expensive model
    # less impactful per call.
    "decompose": Tier(
        "decompose",
        bindings=(
            _pm("openrouter", "anthropic/claude-sonnet-4.5"),
            _pm("openrouter", "anthropic/claude-haiku-4.5"),
        ),
    ),
    # Generator is a one-shot flight-plan synthesis — frontier-tier
    # reasoning, but only one call per workflow run.
    "generate": Tier(
        "generate",
        bindings=(
            _pm("openrouter", "anthropic/claude-sonnet-4.5"),
            _pm("openrouter", "anthropic/claude-haiku-4.5"),
        ),
    ),
}


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def tiers_from_config(config: Any) -> dict[str, Tier]:
    """Convert a :class:`MaverickConfig.provider_tiers` block into a runtime map.

    Returns an empty dict when no overrides are configured. Workflows
    pass the result to :func:`actor_pool(provider_tiers=...)`.
    """
    block = getattr(config, "provider_tiers", None)
    if block is None:
        return {}
    raw = getattr(block, "tiers", None)
    if not raw:
        return {}
    out: dict[str, Tier] = {}
    for tier_name, entries in raw.items():
        if not entries:
            continue
        bindings = tuple(
            ProviderModel(provider_id=entry.provider, model_id=entry.model_id) for entry in entries
        )
        if bindings:
            out[tier_name] = Tier(name=tier_name, bindings=bindings)
    return out


def resolve_tier(name: str, *, override: dict[str, Tier] | None = None) -> Tier:
    """Return the configured tier for ``name``.

    Args:
        name: Role tier name as declared on an actor's
            ``provider_tier`` class attribute (e.g. ``"review"``).
        override: Optional per-call override map (typically built from
            user config). Falls back to :data:`DEFAULT_TIERS` when the
            override is ``None`` or doesn't include ``name``.

    Raises:
        KeyError: When ``name`` matches no entry in either map.
    """
    if override and name in override:
        return override[name]
    if name in DEFAULT_TIERS:
        return DEFAULT_TIERS[name]
    raise KeyError(
        f"Unknown provider tier: {name!r}. "
        f"Define it in maverick.yaml::provider_tiers or pick from "
        f"{sorted(DEFAULT_TIERS.keys())}."
    )


# ---------------------------------------------------------------------------
# Cascade
# ---------------------------------------------------------------------------


#: Errors that are cascadable — i.e. retrying with a different binding
#: has a real chance of succeeding. Context-overflow needs a bigger
#: context model rather than just a different one, so it's NOT in this
#: set; callers handle it explicitly.
CASCADE_ERRORS: tuple[type[OpenCodeError], ...] = (
    OpenCodeAuthError,
    OpenCodeModelNotFoundError,
    OpenCodeTransientError,
    OpenCodeStructuredOutputError,
)


@dataclass(slots=True)
class CascadeOutcome:
    """Captures the result of a cascade — useful for telemetry."""

    binding: ProviderModel
    result: SendResult
    attempts: tuple[ProviderModel, ...] = field(default_factory=tuple)
    failed_bindings: tuple[tuple[ProviderModel, str], ...] = field(default_factory=tuple)


SendFn = Callable[[ProviderModel], Awaitable[SendResult]]


async def cascade_send(
    tier: Tier,
    send_fn: SendFn,
    *,
    skip: set[ProviderModel] | None = None,
) -> CascadeOutcome:
    """Walk ``tier.bindings`` invoking ``send_fn`` until one succeeds.

    Args:
        tier: Resolved tier whose bindings to try in order.
        send_fn: Async callable invoked with each :class:`ProviderModel`.
            Returns a :class:`SendResult` on success; raises a
            :class:`CASCADE_ERRORS` member to fail over, or any other
            :class:`OpenCodeError` to abort.
        skip: Bindings already known to fail this run (e.g. from a prior
            cascade for the same actor); skipped without retry.

    Returns:
        :class:`CascadeOutcome` with the binding that succeeded, the
        :class:`SendResult`, the ordered list of attempted bindings,
        and the failures observed along the way.

    Raises:
        OpenCodeError: When every binding fails. The last raised
            exception is re-raised (the cascade history is preserved
            via the structured log).
    """
    skip = skip or set()
    attempts: list[ProviderModel] = []
    failed: list[tuple[ProviderModel, str]] = []
    last_exc: BaseException | None = None

    for binding in tier.bindings:
        if binding in skip:
            continue
        attempts.append(binding)
        try:
            result = await send_fn(binding)
        except CASCADE_ERRORS as exc:
            failed.append((binding, _classify(exc)))
            last_exc = exc
            logger.info(
                "opencode.cascade_fallback",
                tier=tier.name,
                failed_binding=binding.label,
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            continue
        except OpenCodeContextOverflowError:
            # Different shape — not a tier failure. Re-raise so the
            # caller can decide (shrink the prompt, escalate to a
            # larger-context model, abandon the bead).
            raise
        # Success.
        return CascadeOutcome(
            binding=binding,
            result=result,
            attempts=tuple(attempts),
            failed_bindings=tuple(failed),
        )

    # Cascade exhausted.
    logger.warning(
        "opencode.cascade_exhausted",
        tier=tier.name,
        attempted=[b.label for b in attempts],
        failures=[(b.label, e) for b, e in failed],
    )
    if last_exc is not None:
        raise last_exc
    raise OpenCodeError(
        f"Cascade for tier {tier.name!r} exhausted with no attempts (every binding was in `skip`)."
    )


def _classify(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:120]}"


# ---------------------------------------------------------------------------
# Cost telemetry
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CostRecord:
    """One row of cost telemetry — captured from each send's ``info``."""

    provider_id: str | None
    model_id: str | None
    cost_usd: float | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    finish: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "providerID": self.provider_id,
            "modelID": self.model_id,
            "cost_usd": self.cost_usd,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "finish": self.finish,
        }


def cost_record_from_send(result: SendResult) -> CostRecord:
    """Extract a :class:`CostRecord` from a :class:`SendResult`'s ``info``."""
    info = result.info or {}
    tokens = info.get("tokens") or {}
    if not isinstance(tokens, dict):
        tokens = {}
    cache = tokens.get("cache") or {}
    if not isinstance(cache, dict):
        cache = {}

    cost_raw = info.get("cost")
    cost: float | None
    if isinstance(cost_raw, int | float):
        cost = float(cost_raw)
    else:
        cost = None

    return CostRecord(
        provider_id=info.get("providerID"),
        model_id=info.get("modelID"),
        cost_usd=cost,
        input_tokens=int(tokens.get("input", 0) or 0),
        output_tokens=int(tokens.get("output", 0) or 0),
        cache_read_tokens=int(cache.get("read", 0) or 0),
        cache_write_tokens=int(cache.get("write", 0) or 0),
        finish=info.get("finish"),
    )


__all__ = [
    "CASCADE_ERRORS",
    "CostRecord",
    "DEFAULT_TIERS",
    "ProviderModel",
    "Tier",
    "CascadeOutcome",
    "cascade_send",
    "cost_record_from_send",
    "resolve_tier",
    "tiers_from_config",
]
