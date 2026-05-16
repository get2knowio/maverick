"""Airframe-backed provider discovery for ``maverick init``.

For each adapter the user has installed (via ``pip install
airframe-agents[<extra>]``), this module attempts to enumerate the
provider's live model catalogue via :meth:`AgentRuntime.list_models`.
A successful list means the user has working credentials for that
provider; a failure (no auth, vendor down) is reported as
"not connected" and the provider is excluded from the result.

Output drives the verbose console output during init; the generated
``maverick.yaml::agents`` block uses curated defaults independent of
discovery. Failures are non-fatal — init still writes the config when
discovery fails.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import airframe
from airframe.errors import AgentRuntimeError

from maverick.logging import get_logger

__all__ = [
    "DiscoveredProvider",
    "ProviderDiscoveryResult",
    "discover_providers",
]

logger = get_logger(__name__)


#: Conventional preference order — when multiple providers are
#: connected, the first match in this list becomes the default. The
#: ordering reflects "most useful first" for the typical Maverick user.
_PREFERENCE_ORDER: tuple[str, ...] = (
    "github-copilot",
    "claude",
    "codex",
    "opencode",
)


@dataclass(frozen=True, slots=True)
class DiscoveredProvider:
    """One adapter that successfully enumerated its catalogue.

    Attributes:
        provider_id: Airframe canonical provider id.
        display_name: Human-readable name — falls back to ``provider_id``.
        default_model_id: First model in the adapter's catalogue, used
            as a reasonable default for generated config. ``None`` when
            the catalogue came back empty.
        model_count: Number of models the adapter reported.
    """

    provider_id: str
    display_name: str
    default_model_id: str | None
    model_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "default_model_id": self.default_model_id,
            "model_count": self.model_count,
        }


@dataclass(frozen=True, slots=True)
class ProviderDiscoveryResult:
    """Aggregate discovery result. Name kept for source compatibility."""

    providers: tuple[DiscoveredProvider, ...]
    default_provider_id: str | None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "providers": [p.to_dict() for p in self.providers],
            "default_provider_id": self.default_provider_id,
            "duration_ms": self.duration_ms,
        }


async def discover_providers(
    *,
    timeout: float = 30.0,
) -> ProviderDiscoveryResult | None:
    """Probe every installed airframe adapter for live model listings.

    Returns ``None`` only when the discovery layer itself can't be
    walked (no adapters at all); per-provider failures get logged and
    the provider is skipped.
    """
    start = time.monotonic()
    try:
        installed = airframe.list_providers(installed_only=True)
    except Exception as exc:  # noqa: BLE001
        logger.debug("airframe_list_providers_failed", error=str(exc))
        return None

    if not installed:
        return ProviderDiscoveryResult(
            providers=(),
            default_provider_id=None,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    rows: list[DiscoveredProvider] = []
    for pid in installed:
        row = await _probe_provider(pid, timeout=timeout)
        if row is not None:
            rows.append(row)

    rows.sort(key=lambda r: (_preference_index(r.provider_id), r.provider_id))
    default_id = rows[0].provider_id if rows else None

    return ProviderDiscoveryResult(
        providers=tuple(rows),
        default_provider_id=default_id,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


async def _probe_provider(provider_id: str, *, timeout: float) -> DiscoveredProvider | None:
    """Instantiate the adapter and call ``list_models`` with a deadline.

    Returns ``None`` on any failure (auth missing, vendor down, SDK
    raised). Successful runs become one :class:`DiscoveredProvider`.
    """
    try:
        runtime_cls = airframe.runtime_for(provider_id)
        runtime = runtime_cls()
    except Exception as exc:  # noqa: BLE001
        logger.debug("airframe_runtime_init_failed", provider=provider_id, error=str(exc))
        return None

    try:
        models = await asyncio.wait_for(runtime.list_models(), timeout=timeout)
    except (TimeoutError, AgentRuntimeError) as exc:
        logger.debug("airframe_list_models_failed", provider=provider_id, error=str(exc))
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("airframe_list_models_failed", provider=provider_id, error=str(exc))
        return None
    finally:
        try:
            await runtime.close()
        except Exception:  # noqa: BLE001
            pass

    if not models:
        return None

    display = models[0].provider_id if hasattr(models[0], "provider_id") else provider_id
    return DiscoveredProvider(
        provider_id=provider_id,
        display_name=display or provider_id,
        default_model_id=models[0].id,
        model_count=len(models),
    )


def _preference_index(provider_id: str) -> int:
    try:
        return _PREFERENCE_ORDER.index(provider_id)
    except ValueError:
        return len(_PREFERENCE_ORDER)
