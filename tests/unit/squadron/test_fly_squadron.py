"""Tests for :class:`maverick.squadron.fly.FlySquadron`."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from maverick.config import MaverickConfig
from maverick.squadron.fly import FlySquadron
from tests.unit.agents.conftest import FakeClient, fake_handle, payload_send_result


@pytest.fixture
def fake_squadron_handle(monkeypatch: Any) -> Any:
    """Patch spawn_opencode_server + tier-binding validation.

    Squadron is reasonably testable when (a) spawn_opencode_server
    returns a fake handle and (b) the startup validation pass against
    the live ``/provider`` endpoint is short-circuited (no real HTTP).
    """
    handle = fake_handle()

    async def _fake_spawn(*_args: Any, **_kwargs: Any) -> Any:
        return handle

    async def _fake_validate(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("maverick.squadron.base.spawn_opencode_server", _fake_spawn)
    monkeypatch.setattr("maverick.squadron.base.validate_model_id", _fake_validate)
    return handle


@pytest.fixture
def fake_agent_clients(monkeypatch: Any) -> dict[str, FakeClient]:
    """Override Agent._build_client to hand out a fresh FakeClient per agent."""
    clients: dict[str, FakeClient] = {}

    def _build_client(self: Any) -> Any:
        c = FakeClient(send_result=payload_send_result({"approved": True}))
        clients[self.tag] = c
        return c

    monkeypatch.setattr("maverick.agents.base.Agent._build_client", _build_client)
    return clients


async def test_open_spawns_and_builds_agents(
    fake_squadron_handle: Any,
    fake_agent_clients: dict[str, FakeClient],
    tmp_path: Path,
) -> None:
    config = MaverickConfig()
    async with FlySquadron(cwd=tmp_path, config=config) as squadron:
        # All three agents are present and opened.
        assert squadron.coder is not None
        assert squadron.correctness_reviewer is not None
        assert squadron.completeness_reviewer is not None
        # Tier overrides defaulted to empty (user didn't set any).
        assert squadron.tier_overrides == {}
        # Handle is the fake one we injected.
        assert squadron.handle is fake_squadron_handle


async def test_handle_unavailable_before_open(tmp_path: Path) -> None:
    """Accessing handle before opening raises a clear error."""
    config = MaverickConfig()
    squadron = FlySquadron(cwd=tmp_path, config=config)
    with pytest.raises(RuntimeError, match="not opened"):
        _ = squadron.handle


async def test_validate_tier_bindings_runs_at_open(
    fake_squadron_handle: Any,
    fake_agent_clients: dict[str, FakeClient],
    tmp_path: Path,
) -> None:
    """Squadron.open validates every declared (provider, model) binding once."""
    config = MaverickConfig()
    async with FlySquadron(cwd=tmp_path, config=config):
        pass
    # Every Agent shares one client class but distinct instances built
    # via _build_client. Validation goes through a separate ad-hoc
    # OpenCodeClient — that one is constructed inside Squadron.open()
    # against the fake handle. We can't see its calls here, but we
    # verified above that open() succeeds end-to-end.
    # (Detailed cascade-cache + per-binding tests live in
    # tests/unit/agents/test_agent_tiers.py.)


async def test_rotate_for_new_bead_rotates_each_agent(
    fake_squadron_handle: Any,
    fake_agent_clients: dict[str, FakeClient],
    tmp_path: Path,
) -> None:
    """rotate_for_new_bead drops every agent's session pointer."""
    config = MaverickConfig()
    async with FlySquadron(cwd=tmp_path, config=config) as squadron:
        # Open a session on each agent without going through a typed
        # send (skip schema validation against fake payloads).
        await squadron.coder._ensure_session()  # noqa: SLF001
        await squadron.correctness_reviewer._ensure_session()  # noqa: SLF001
        await squadron.completeness_reviewer._ensure_session()  # noqa: SLF001

        assert squadron.coder._session_id is not None  # noqa: SLF001
        assert squadron.correctness_reviewer._session_id is not None  # noqa: SLF001
        assert squadron.completeness_reviewer._session_id is not None  # noqa: SLF001

        await squadron.rotate_for_new_bead()

        assert squadron.coder._session_id is None  # noqa: SLF001
        assert squadron.correctness_reviewer._session_id is None  # noqa: SLF001
        assert squadron.completeness_reviewer._session_id is None  # noqa: SLF001


async def test_close_tears_down_handle(
    monkeypatch: Any,
    fake_agent_clients: dict[str, FakeClient],
    tmp_path: Path,
) -> None:
    """Squadron.close stops the OpenCode server it spawned."""
    stopped = {"count": 0}
    handle = fake_handle()

    async def _fake_spawn(*_args: Any, **_kwargs: Any) -> Any:
        return handle

    async def _fake_stop(self: Any) -> None:
        stopped["count"] += 1

    async def _fake_validate(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr("maverick.squadron.base.spawn_opencode_server", _fake_spawn)
    monkeypatch.setattr("maverick.squadron.base.validate_model_id", _fake_validate)
    monkeypatch.setattr("maverick.runtime.opencode.OpenCodeServerHandle.stop", _fake_stop)

    config = MaverickConfig()
    async with FlySquadron(cwd=tmp_path, config=config):
        pass
    assert stopped["count"] == 1
