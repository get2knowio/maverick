"""OpenCode-backed provider discovery for ``maverick init``.

Replaces the legacy PATH-based ``shutil.which("claude-agent-acp")``
probe — which made sense when each "provider" was an ACP bridge binary
on PATH but means nothing under the OpenCode HTTP runtime. The new
discovery spawns ``opencode serve`` once, hits ``GET /provider``, and
returns the provider IDs OpenCode reports as authenticated (the
``connected[]`` list) along with their default model IDs.

Output drives the generated ``maverick.yaml::agent_providers`` block
and is suggested in the verbose console output. Failures are
non-fatal; init still writes the config without an
``agent_providers`` block when discovery fails (the default tier
cascade still works as long as the runtime can reach OpenCode at
workflow time).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from maverick.logging import get_logger
from maverick.runtime.opencode import client_for, list_connected_providers, opencode_server

__all__ = [
    "ConnectedProvider",
    "OpenCodeDiscoveryResult",
    "discover_opencode_providers",
]

logger = get_logger(__name__)


#: Conventional preference order — when multiple providers are
#: connected and none are flagged ``default: true`` in an existing
#: config, the first match in this list becomes the default. Order
#: reflects "most useful first" for the typical Maverick user:
#: GitHub Copilot covers Claude + GPT + Gemini under one sub; the
#: OpenAI Codex sub covers the GPT-codex line; opencode-go is the
#: paid-per-token gateway; opencode (Zen) is the free fallback;
#: openrouter is per-token billed and lives at the bottom.
_PREFERENCE_ORDER: tuple[str, ...] = (
    "github-copilot",
    "openai",
    "opencode-go",
    "opencode",
    "openrouter",
)


@dataclass(frozen=True, slots=True)
class ConnectedProvider:
    """One connected provider as advertised by ``GET /provider``.

    Attributes:
        provider_id: OpenCode provider id (e.g. ``"github-copilot"``).
        display_name: Human-readable name (best-effort — falls back to
            ``provider_id`` when OpenCode doesn't supply one).
        default_model_id: The provider's default model id when the
            server registered one. ``None`` when no default is exposed.
        model_count: How many models the provider's catalogue carries.
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
class OpenCodeDiscoveryResult:
    """Aggregate result of probing OpenCode for connected providers.

    Attributes:
        providers: Probed providers, sorted by :data:`_PREFERENCE_ORDER`.
        default_provider_id: The provider id chosen as the conventional
            default (the highest-preference connected provider). ``None``
            when no providers are connected.
        duration_ms: Wall-clock time of the discovery call.
    """

    providers: tuple[ConnectedProvider, ...]
    default_provider_id: str | None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "providers": [p.to_dict() for p in self.providers],
            "default_provider_id": self.default_provider_id,
            "duration_ms": self.duration_ms,
        }


async def discover_opencode_providers(
    *,
    timeout: float = 30.0,
) -> OpenCodeDiscoveryResult | None:
    """Spawn an OpenCode server, query ``/provider``, return connected providers.

    Returns ``None`` when the server can't be spawned or the probe
    fails — discovery is best-effort during init, not a hard
    prerequisite.
    """
    start = time.monotonic()
    try:
        async with opencode_server() as handle:
            client = client_for(handle, timeout=timeout)
            try:
                connected = await list_connected_providers(client)
                # Pull the full /provider payload so we can extract the
                # default_model and the per-provider display name.
                raw = await client.list_providers()
            finally:
                await client.aclose()
    except Exception as exc:  # noqa: BLE001 — discovery failures are non-fatal
        logger.debug("opencode_discovery_failed", error=str(exc))
        return None

    elapsed_ms = int((time.monotonic() - start) * 1000)

    defaults_block = raw.get("default") if isinstance(raw, dict) else None
    if not isinstance(defaults_block, dict):
        defaults_block = {}
    all_block = raw.get("all") if isinstance(raw, dict) else None
    by_id: dict[str, dict[str, Any]] = {}
    if isinstance(all_block, list):
        for entry in all_block:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                by_id[entry["id"]] = entry

    rows: list[ConnectedProvider] = []
    for pid in connected:
        prov = by_id.get(pid, {})
        name = prov.get("name") if isinstance(prov.get("name"), str) else pid
        default_model = defaults_block.get(pid)
        if not isinstance(default_model, str):
            default_model = None
        rows.append(
            ConnectedProvider(
                provider_id=pid,
                display_name=name or pid,
                default_model_id=default_model,
                model_count=len(connected.get(pid, ())),
            )
        )

    rows.sort(key=lambda r: (_preference_index(r.provider_id), r.provider_id))
    default_id = rows[0].provider_id if rows else None

    return OpenCodeDiscoveryResult(
        providers=tuple(rows),
        default_provider_id=default_id,
        duration_ms=elapsed_ms,
    )


def _preference_index(provider_id: str) -> int:
    """Sort key — providers in :data:`_PREFERENCE_ORDER` come first."""
    try:
        return _PREFERENCE_ORDER.index(provider_id)
    except ValueError:
        return len(_PREFERENCE_ORDER)
