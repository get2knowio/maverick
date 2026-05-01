"""Integration test: ``OpenCodeStepExecutor`` against a real OpenCode subprocess.

Spawns OpenCode, runs ``execute()`` and ``create_session/prompt_session``
without contacting any LLM provider — we use synthetic prompts and rely
only on the runtime's session-management surface. Live-LLM coverage
lives in ``tests/integration/actors/test_reviewer_opencode_e2e.py``,
gated on ``MAVERICK_E2E_LLM=1``.
"""

from __future__ import annotations

import os
import shutil

import pytest

from maverick.runtime.opencode import OpenCodeError, opencode_server
from maverick.runtime.opencode.executor import OpenCodeStepExecutor

pytestmark = [pytest.mark.integration, pytest.mark.slow]

if not shutil.which(os.environ.get("OPENCODE_BIN") or "opencode"):
    pytest.skip("opencode binary not on PATH", allow_module_level=True)


class _NoopAgent:
    instructions = ""
    allowed_tools: list[str] = []

    def build_prompt(self, _: object) -> str:
        return "smoke"


class _NoopRegistrySection:
    def has(self, name: str) -> bool:
        return name == "noop"

    def get(self, name: str) -> type:
        return _NoopAgent

    def list_names(self) -> list[str]:
        return ["noop"]


class _NoopRegistry:
    def __init__(self) -> None:
        self.agents = _NoopRegistrySection()


async def test_executor_create_and_close_session_round_trip() -> None:
    """Open a session, cancel it, close it. No model invocation."""
    async with opencode_server() as handle:
        executor = OpenCodeStepExecutor(
            agent_registry=_NoopRegistry(),
            server_handle=handle,
        )
        try:
            sid = await executor.create_session(step_name="rt", agent_name="noop")
            assert sid.startswith("ses_")
            # cancel is best-effort — should not raise even when nothing is in flight.
            await executor.cancel_session(sid)
            await executor.close_session(sid)
        finally:
            await executor.cleanup()


async def test_executor_lazy_spawn_when_no_handle_passed() -> None:
    """When no handle is supplied, the executor spawns its own opencode and
    tears it down on cleanup."""
    executor = OpenCodeStepExecutor(agent_registry=_NoopRegistry())
    try:
        sid = await executor.create_session(step_name="lazy", agent_name="noop")
        assert sid.startswith("ses_")
        await executor.close_session(sid)
    finally:
        await executor.cleanup()


async def test_executor_invalid_session_raises() -> None:
    """Calling prompt_session on an unknown id raises a clear AgentError."""
    from maverick.exceptions.agent import AgentError

    async with opencode_server() as handle:
        executor = OpenCodeStepExecutor(
            agent_registry=_NoopRegistry(),
            server_handle=handle,
        )
        try:
            with pytest.raises(AgentError):
                await executor.prompt_session(session_id="ses_nope", prompt_text="hi")
        finally:
            await executor.cleanup()


async def test_executor_cleanup_is_idempotent() -> None:
    async with opencode_server() as handle:
        executor = OpenCodeStepExecutor(
            agent_registry=_NoopRegistry(),
            server_handle=handle,
        )
        await executor.cleanup()
        # Second call should not raise.
        await executor.cleanup()


async def test_executor_does_not_kill_external_handle_on_cleanup() -> None:
    """When server_handle was supplied, cleanup must not stop the server."""
    async with opencode_server() as handle:
        executor = OpenCodeStepExecutor(
            agent_registry=_NoopRegistry(),
            server_handle=handle,
        )
        await executor.cleanup()
        # Health should still answer — we still own the handle.
        from maverick.runtime.opencode import client_for

        client = client_for(handle)
        try:
            health = await client.health()
            assert isinstance(health, dict)
        except OpenCodeError:
            pytest.fail("external handle was killed by executor.cleanup()")
        finally:
            await client.aclose()
