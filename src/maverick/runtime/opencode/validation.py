"""Provider/model validation against a live OpenCode server.

Mitigates Landmine 1 (server-killing async dispatch with bad ``modelID``)
by rejecting unknown models at the maverick layer *before* they reach the
HTTP transport. Synchronous ``send_message`` is also affected (silent
empty 200 — Landmine 2), so every send path should validate first.

The validation cache is keyed on the client's ``base_url`` so multiple
servers in one process don't share entries. Cache entries are TTL-bound
so a freshly-authenticated provider is picked up without needing a process
restart.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from maverick.logging import get_logger
from maverick.runtime.opencode.client import OpenCodeClient
from maverick.runtime.opencode.errors import OpenCodeModelNotFoundError

logger = get_logger(__name__)

DEFAULT_CACHE_TTL_SECONDS = 60.0


@dataclass
class _CacheEntry:
    """One server's provider/model snapshot."""

    fetched_at: float
    # provider_id -> set of model ids
    providers: dict[str, set[str]] = field(default_factory=dict)


_CACHE: dict[str, _CacheEntry] = {}


async def _get_provider_snapshot(
    client: OpenCodeClient, *, ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS
) -> _CacheEntry:
    now = time.monotonic()
    entry = _CACHE.get(client.base_url)
    if entry is not None and (now - entry.fetched_at) < ttl_seconds:
        return entry

    raw = await client.list_providers()
    providers: dict[str, set[str]] = {}
    # OpenCode's /provider response shape:
    #   { "providers": [ { "id": "...", "models": { "<modelId>": {...}, ... } }, ... ] }
    for prov in raw.get("providers", []) or []:
        pid = prov.get("id")
        if not pid:
            continue
        models = prov.get("models") or {}
        if isinstance(models, dict):
            providers[pid] = set(models.keys())
        elif isinstance(models, list):
            providers[pid] = {m.get("id") or m.get("name") or "" for m in models if m}
            providers[pid].discard("")
        else:
            providers[pid] = set()
    fresh = _CacheEntry(fetched_at=now, providers=providers)
    _CACHE[client.base_url] = fresh
    return fresh


def invalidate_cache(base_url: str | None = None) -> None:
    """Drop cached provider snapshots.

    Pass ``base_url=None`` to clear every entry.
    """
    if base_url is None:
        _CACHE.clear()
    else:
        _CACHE.pop(base_url, None)


async def list_connected_providers(client: OpenCodeClient) -> dict[str, set[str]]:
    """Return ``{provider_id: {model_ids...}}`` for every connected provider."""
    entry = await _get_provider_snapshot(client)
    return {pid: set(models) for pid, models in entry.providers.items()}


async def validate_model_id(
    client: OpenCodeClient,
    provider_id: str,
    model_id: str,
    *,
    ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
) -> None:
    """Reject unknown ``(provider_id, model_id)`` against the live server.

    Args:
        client: The OpenCode client whose server to probe.
        provider_id: Provider identifier (e.g. ``"openrouter"``).
        model_id: Model identifier (e.g. ``"anthropic/claude-haiku-4.5"``).
        ttl_seconds: Cache TTL. Pass ``0`` to force a fresh fetch.

    Raises:
        OpenCodeModelNotFoundError: When the provider isn't connected or
            the model isn't listed under it.
    """
    entry = await _get_provider_snapshot(client, ttl_seconds=ttl_seconds)
    if provider_id not in entry.providers:
        connected = sorted(entry.providers.keys())
        raise OpenCodeModelNotFoundError(
            f"provider '{provider_id}' is not connected on {client.base_url}; "
            f"connected providers: {connected}",
            body={"provider_id": provider_id, "connected": connected},
        )
    models = entry.providers[provider_id]
    if model_id not in models:
        # Don't dump the full model list in the message (some providers
        # ship hundreds). Suggest similar ids if any are obviously close.
        sample = sorted(models)[:8]
        raise OpenCodeModelNotFoundError(
            f"model '{model_id}' not available on provider "
            f"'{provider_id}'. Sample of available models: {sample}",
            body={"provider_id": provider_id, "model_id": model_id, "sample": sample},
        )
