"""OpenCode-specific cascade logic + legacy re-exports.

The vendor-agnostic pieces (``ProviderModel``, ``Tier``,
``DEFAULT_TIERS``, ``tiers_from_config``, ``resolve_tier``) live in
:mod:`maverick.runtime.tiers` now. This module re-exports them for
backward compatibility and keeps the OpenCode-specific cascade
machinery (which takes ``SendResult`` and OpenCode-classified
exceptions). The cascade migrates to a vendor-neutral home in Phase 6
of the Pattern D migration.

See ``docs/migration-implementation-plan.md``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from maverick.logging import get_logger
from maverick.runtime.opencode.client import SendResult
from maverick.runtime.opencode.errors import (
    AgentRuntimeError,
    RuntimeAuthError,
    RuntimeContextOverflowError,
    RuntimeModelNotFoundError,
    RuntimeStructuredOutputError,
    RuntimeTransientError,
)

# Re-exports — these now live in the neutral runtime/tiers.py module.
from maverick.runtime.tiers import (  # noqa: F401 — public re-export
    DEFAULT_TIERS,
    ProviderModel,
    Tier,
    resolve_tier,
    tiers_from_config,
)

logger = get_logger(__name__)


# Legacy: the (provider, model) helper used by inline binding construction.
# Kept private; new code should use ProviderModel directly.
def _pm(provider: str, model: str) -> ProviderModel:
    return ProviderModel(provider_id=provider, model_id=model)


#: (legacy DEFAULT_TIERS docstring preserved for grep-readers — the
#: actual data lives in :mod:`maverick.runtime.tiers`.)
#:
#: Default tier cascades distribute load across the user's flat-rate
#: subscriptions (github-copilot, openai/Codex, opencode/Zen) and
#: reserve OpenRouter for free models only — OpenRouter is the only
#: per-token billed provider in the OpenCode-substrate world. Front-lane
#: ordering is empirical: claude-sonnet-4.6 leads ``generate`` because
#: it handles nested-object structured-output most reliably; gpt-codex
#: leads ``implement`` because Codex models are tuned for code; haiku
#: leads ``review`` because it's the cheapest sub-second classifier.
#:
#: Override per-project in ``maverick.yaml::provider_tiers.tiers`` or
#: globally by editing this map. Each binding's first failure (auth,
#: model-not-found, structured-output, sustained transient) silently
#: falls over to the next.
#
# DEFAULT_TIERS, tiers_from_config, and resolve_tier now live in
# :mod:`maverick.runtime.tiers` and are re-exported above.


# ---------------------------------------------------------------------------
# Cascade
# ---------------------------------------------------------------------------


#: Errors that are cascadable — i.e. retrying with a different binding
#: has a real chance of succeeding. Context-overflow needs a bigger
#: context model rather than just a different one, so it's NOT in this
#: set; callers handle it explicitly.
CASCADE_ERRORS: tuple[type[AgentRuntimeError], ...] = (
    RuntimeAuthError,
    RuntimeModelNotFoundError,
    RuntimeTransientError,
    RuntimeStructuredOutputError,
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
            :class:`AgentRuntimeError` to abort.
        skip: Bindings already known to fail this run (e.g. from a prior
            cascade for the same actor); skipped without retry.

    Returns:
        :class:`CascadeOutcome` with the binding that succeeded, the
        :class:`SendResult`, the ordered list of attempted bindings,
        and the failures observed along the way.

    Raises:
        AgentRuntimeError: When every binding fails. The last raised
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
        except RuntimeContextOverflowError:
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
    raise AgentRuntimeError(
        f"Cascade for tier {tier.name!r} exhausted with no attempts (every binding was in `skip`)."
    )


def _classify(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:120]}"


# ---------------------------------------------------------------------------
# Cost telemetry
# ---------------------------------------------------------------------------


# ``CostRecord`` lives in :mod:`airframe.cost`. Re-exported here for
# backward compatibility with the legacy import path used by OpenCode-
# HTTP-runtime callers (deleted in Phase 7 of the Pattern D migration).
from airframe.cost import CostRecord  # noqa: E402


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
