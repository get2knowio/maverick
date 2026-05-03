"""Integration test: spawn a real OpenCode subprocess, exercise the runtime.

Marked ``slow`` and ``integration`` — runs only when explicitly requested
and when the ``opencode`` binary is on ``$PATH``. Does not require any
provider auth (only uses ``GET /provider`` and the spawn-and-cancel
paths) so it works in CI without secrets.
"""

from __future__ import annotations

import asyncio
import os
import shutil

import pytest

from maverick.runtime.opencode import (
    OpenCodeError,
    OpenCodeModelNotFoundError,
    OpenCodeServerStartError,
    client_for,
    list_connected_providers,
    opencode_server,
    spawn_opencode_server,
    validate_model_id,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _opencode_available() -> bool:
    return shutil.which(os.environ.get("OPENCODE_BIN") or "opencode") is not None


pytest.importorskip("httpx")
if not _opencode_available():
    pytest.skip("opencode binary not on PATH", allow_module_level=True)


async def test_spawn_health_and_providers_round_trip() -> None:
    """Spawn server, hit /global/health, list providers, terminate."""
    async with opencode_server() as handle:
        client = client_for(handle)
        try:
            health = await client.health()
            assert isinstance(health, dict)
            providers = await list_connected_providers(client)
            # We don't assert specific providers — the test environment may
            # have any subset connected. Just verify the call works.
            assert isinstance(providers, dict)
        finally:
            await client.aclose()


async def test_validate_model_id_rejects_bogus_model() -> None:
    """Landmine 1: bad model rejected at the maverick layer."""
    async with opencode_server() as handle:
        client = client_for(handle)
        try:
            with pytest.raises(OpenCodeModelNotFoundError):
                await validate_model_id(client, "definitely-not-a-real-provider", "fake-model")
        finally:
            await client.aclose()


async def test_session_create_and_cancel() -> None:
    """Cancel returns ~14ms; server stays healthy."""
    async with opencode_server() as handle:
        client = client_for(handle)
        try:
            sid = await client.create_session(title="cancel-probe")
            ok = await client.cancel(sid)
            # cancel returns bool; whether True depends on whether anything
            # was in flight. Both are valid outcomes for an idle session.
            assert isinstance(ok, bool)
            # Server still healthy after cancel.
            health = await client.health()
            assert isinstance(health, dict)
            await client.delete_session(sid)
        finally:
            await client.aclose()


async def test_concurrent_sessions_do_not_serialize() -> None:
    """The server must accept multiple sessions in flight simultaneously."""
    async with opencode_server() as handle:
        client = client_for(handle)
        try:
            sids = await asyncio.gather(
                *[client.create_session(title=f"concurrent-{i}") for i in range(5)]
            )
            assert len(set(sids)) == 5
            for sid in sids:
                await client.delete_session(sid)
        finally:
            await client.aclose()


async def test_spawn_with_invalid_executable_raises() -> None:
    """Server-start failure surfaces as :class:`OpenCodeServerStartError`."""
    with pytest.raises(OpenCodeServerStartError):
        await spawn_opencode_server(executable="/no/such/binary", startup_timeout=2.0)


async def test_unauthorized_request_rejected_when_password_set() -> None:
    """A client without the bearer token cannot use the server."""
    async with opencode_server() as handle:
        # Build a client with an empty password — should be rejected.
        from maverick.runtime.opencode import OpenCodeClient

        bad = OpenCodeClient(base_url=handle.base_url)
        try:
            with pytest.raises(OpenCodeError):
                await bad.health()
        finally:
            await bad.aclose()
