"""Tests for the :class:`AcpStepExecutor` ↔ :class:`SubprocessQuota` wiring.

Validates that:
* The executor acquires a quota slot before its first subprocess spawn.
* ``cleanup()`` releases the slot.
* Eviction tears down the subprocess pool without re-releasing
  (the quota already popped the lease).
* The session-invalidation hook fires before subprocess shutdown.

The end-to-end "real subprocess + real ACP handshake" path is covered
by the higher-level integration suite (run by hand against the sample
project). These tests stub the spawn side with mocks.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.config import AgentProviderConfig, PermissionMode
from maverick.executor.acp import AcpStepExecutor
from maverick.executor.acp_client import MaverickAcpClient
from maverick.executor.provider_registry import AgentProviderRegistry
from maverick.registry import ComponentRegistry
from maverick.tools.agent_inbox.subprocess_quota import SubprocessQuota

# ---------------------------------------------------------------------------
# Test scaffolding — tiny stubs adapted from test_acp_executor.py.
# ---------------------------------------------------------------------------


class _FakeCM:
    def __init__(self, conn: Any, proc: Any) -> None:
        self._conn = conn
        self._proc = proc

    async def __aenter__(self) -> tuple[Any, Any]:
        return self._conn, self._proc

    async def __aexit__(self, *_args: Any) -> None:
        return None


def _mock_conn_proc() -> tuple[MagicMock, MagicMock]:
    conn = MagicMock()
    conn.initialize = AsyncMock(return_value=None)
    conn.close = AsyncMock(return_value=None)
    sess = MagicMock()
    sess.session_id = "sess-1"
    conn.new_session = AsyncMock(return_value=sess)
    conn.prompt = AsyncMock(return_value=None)
    proc = MagicMock()
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=0)
    proc.pid = 12345
    return conn, proc


def _make_provider_registry() -> AgentProviderRegistry:
    return AgentProviderRegistry(
        {
            "claude": AgentProviderConfig(
                command=["fake-agent", "--acp"],
                permission_mode=PermissionMode.AUTO_APPROVE,
                default=True,
                default_model="sonnet",
            )
        }
    )


def _make_executor_with_quota(
    quota: SubprocessQuota | None,
    actor_uid: str = "actor-1",
) -> AcpStepExecutor:
    return AcpStepExecutor(
        provider_registry=_make_provider_registry(),
        agent_registry=ComponentRegistry(),
        subprocess_quota=quota,
        actor_uid=actor_uid,
    )


# ---------------------------------------------------------------------------
# Acquire on first spawn / release on cleanup.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_spawn_acquires_quota_slot() -> None:
    quota = SubprocessQuota(max_subprocesses=2)
    executor = _make_executor_with_quota(quota, actor_uid="actor-A")
    conn, proc = _mock_conn_proc()
    with (
        patch(
            "maverick.executor._connection_pool.spawn_agent_process",
            return_value=_FakeCM(conn, proc),
        ),
        patch.object(MaverickAcpClient, "get_accumulated_text", return_value=""),
    ):
        await executor.create_session()
        assert "actor-A" in quota.held_uids()


@pytest.mark.asyncio
async def test_repeated_spawns_share_one_slot() -> None:
    """The quota lease covers the entire executor — additional provider
    subprocesses inside the same pool MUST NOT consume extra slots."""
    quota = SubprocessQuota(max_subprocesses=1)
    executor = _make_executor_with_quota(quota, actor_uid="actor-A")
    conn, proc = _mock_conn_proc()
    with (
        patch(
            "maverick.executor._connection_pool.spawn_agent_process",
            return_value=_FakeCM(conn, proc),
        ),
        patch.object(MaverickAcpClient, "get_accumulated_text", return_value=""),
    ):
        await executor.create_session()
        # Re-acquire by issuing another create_session — same provider,
        # cached connection — no new spawn, but acquire is idempotent.
        await executor.create_session()
        assert quota.snapshot().held == 1


@pytest.mark.asyncio
async def test_cleanup_releases_slot() -> None:
    quota = SubprocessQuota(max_subprocesses=1)
    executor = _make_executor_with_quota(quota, actor_uid="actor-A")
    conn, proc = _mock_conn_proc()
    with (
        patch(
            "maverick.executor._connection_pool.spawn_agent_process",
            return_value=_FakeCM(conn, proc),
        ),
        patch.object(MaverickAcpClient, "get_accumulated_text", return_value=""),
    ):
        await executor.create_session()
        assert quota.snapshot().held == 1
        await executor.cleanup()
        assert quota.snapshot().held == 0


@pytest.mark.asyncio
async def test_cleanup_without_spawn_is_noop() -> None:
    """A cleanup before any spawn must not double-release or crash."""
    quota = SubprocessQuota(max_subprocesses=1)
    executor = _make_executor_with_quota(quota, actor_uid="actor-A")
    await executor.cleanup()
    assert quota.snapshot().held == 0


# ---------------------------------------------------------------------------
# Eviction path: quota → executor.cleanup_for_eviction → session invalidator.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_for_eviction_invokes_session_invalidator() -> None:
    quota = SubprocessQuota(max_subprocesses=1)
    executor = _make_executor_with_quota(quota, actor_uid="actor-A")
    conn, proc = _mock_conn_proc()
    invalidate_calls: list[str] = []

    async def invalidator() -> None:
        invalidate_calls.append("called")

    executor.set_session_invalidator(invalidator)

    with (
        patch(
            "maverick.executor._connection_pool.spawn_agent_process",
            return_value=_FakeCM(conn, proc),
        ),
        patch.object(MaverickAcpClient, "get_accumulated_text", return_value=""),
    ):
        await executor.create_session()
        await executor.cleanup_for_eviction()

    assert invalidate_calls == ["called"]


@pytest.mark.asyncio
async def test_eviction_via_quota_full_triggers_executor_cleanup() -> None:
    """When a fresh actor acquires under a full quota, the LRU
    executor's ``cleanup_for_eviction`` MUST be invoked via the
    eviction callback wired through the connection pool."""
    quota = SubprocessQuota(max_subprocesses=1)
    executor_a = _make_executor_with_quota(quota, actor_uid="actor-A")
    executor_b = _make_executor_with_quota(quota, actor_uid="actor-B")

    invalidate_calls: list[str] = []

    async def invalidator_a() -> None:
        invalidate_calls.append("A")

    executor_a.set_session_invalidator(invalidator_a)

    conn_a, proc_a = _mock_conn_proc()
    conn_b, proc_b = _mock_conn_proc()

    # Track which spawn call we're on so we can return the right
    # mock per executor.
    spawn_calls = [0]

    def spawn_side_effect(*_args: Any, **_kwargs: Any) -> _FakeCM:
        spawn_calls[0] += 1
        if spawn_calls[0] == 1:
            return _FakeCM(conn_a, proc_a)
        return _FakeCM(conn_b, proc_b)

    with (
        patch(
            "maverick.executor._connection_pool.spawn_agent_process",
            side_effect=spawn_side_effect,
        ),
        patch.object(MaverickAcpClient, "get_accumulated_text", return_value=""),
    ):
        await executor_a.create_session()
        # B spawning forces eviction of A.
        await executor_b.create_session()

    # A was evicted, so its session invalidator fired and its slot is gone.
    assert invalidate_calls == ["A"]
    held = set(quota.held_uids())
    assert held == {"actor-B"}


# ---------------------------------------------------------------------------
# No quota → executor behaves as legacy (no acquire, no eviction).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_without_quota_does_not_track_slots() -> None:
    """Legacy callers (no quota wired) MUST behave identically to before:
    no slot bookkeeping, no eviction hook fired."""
    executor = _make_executor_with_quota(quota=None, actor_uid="actor-A")
    conn, proc = _mock_conn_proc()
    with (
        patch(
            "maverick.executor._connection_pool.spawn_agent_process",
            return_value=_FakeCM(conn, proc),
        ),
        patch.object(MaverickAcpClient, "get_accumulated_text", return_value=""),
    ):
        await executor.create_session()
        await executor.cleanup()  # must not raise
