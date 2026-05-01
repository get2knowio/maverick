"""Unit tests for :class:`OpenCodeStepExecutor`.

Covers:

* ``execute()`` with plain text response.
* ``execute()`` with ``output_schema`` triggers ``format=json_schema``
  and validates the structured payload.
* ``execute()`` falls back to JSON-in-text extraction when the model
  produced text instead of a StructuredOutput tool call.
* ``execute()`` returns ``ExecutorResult.usage`` populated from
  ``info.tokens`` / ``info.cost``.
* Multi-turn ``create_session`` / ``prompt_session`` reuses the session.
* ``cleanup()`` deletes sessions and closes the client.
* Provider-resolution + model-validation runs before send.
* Errors classify (auth, model not found) propagate as
  :class:`OpenCodeError`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from pydantic import BaseModel

from maverick.executor.config import StepConfig
from maverick.executor.errors import OutputSchemaValidationError
from maverick.executor.result import ExecutorResult
from maverick.runtime.opencode import (
    OpenCodeAuthError,
    OpenCodeServerHandle,
    SendResult,
    invalidate_cache,
)
from maverick.runtime.opencode.executor import OpenCodeStepExecutor

# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeProcess:
    pid = 0
    returncode = 0

    def terminate(self) -> None:
        pass

    def kill(self) -> None:
        pass

    async def wait(self) -> int:
        return 0


def _fake_handle() -> OpenCodeServerHandle:
    return OpenCodeServerHandle(
        base_url="http://fake-opencode",
        password="fake",
        pid=0,
        _process=_FakeProcess(),  # type: ignore[arg-type]
    )


class _FakeClient:
    """Programmable stand-in for :class:`OpenCodeClient`."""

    def __init__(
        self,
        *,
        send_result: SendResult | None = None,
        send_error: BaseException | None = None,
    ) -> None:
        self._send_result = send_result
        self._send_error = send_error
        self.created_sessions: list[str | None] = []
        self.deleted_sessions: list[str] = []
        self.send_calls: list[dict[str, Any]] = []
        self.cancelled: list[str] = []
        self.list_provider_calls = 0
        self.closed = False

    @property
    def base_url(self) -> str:
        return "http://fake-opencode"

    async def list_providers(self) -> dict[str, Any]:
        self.list_provider_calls += 1
        return {
            "all": [
                {
                    "id": "openrouter",
                    "models": {"anthropic/claude-haiku-4.5": {}, "openai/gpt-4o-mini": {}},
                }
            ],
            "connected": ["openrouter"],
            "default": {"openrouter": "anthropic/claude-haiku-4.5"},
        }

    async def create_session(self, *, title: str | None = None, **_: Any) -> str:
        sid = f"ses_{len(self.created_sessions)}"
        self.created_sessions.append(title)
        return sid

    async def delete_session(self, session_id: str) -> bool:
        self.deleted_sessions.append(session_id)
        return True

    async def cancel(self, session_id: str) -> bool:
        self.cancelled.append(session_id)
        return True

    async def send_with_event_watch(
        self,
        session_id: str,
        content: str,
        *,
        model: dict[str, str] | None = None,
        format: dict[str, Any] | None = None,
        system: str | None = None,
        tools: dict[str, bool] | None = None,
        timeout: float | None = None,
        agent: str | None = None,
    ) -> SendResult:
        self.send_calls.append(
            {
                "session_id": session_id,
                "content": content,
                "model": model,
                "format": format,
                "timeout": timeout,
            }
        )
        if self._send_error is not None:
            raise self._send_error
        return self._send_result or SendResult(
            message={"info": {}},
            text="",
            structured=None,
            valid=False,
            info={},
        )

    async def aclose(self) -> None:
        self.closed = True


class _FakeAgent:
    """Minimal agent stub matching the executor's contract."""

    def __init__(self, *, instructions: str | None = None) -> None:
        self.instructions = instructions
        self.allowed_tools = ["Read"]

    def build_prompt(self, context: Any) -> str:
        if isinstance(context, dict):
            return context.get("prompt", "")
        return str(context)


class _FakeRegistrySection:
    def __init__(self, agents: dict[str, type]) -> None:
        self._agents = agents

    def has(self, name: str) -> bool:
        return name in self._agents

    def get(self, name: str) -> type:
        return self._agents[name]

    def list_names(self) -> list[str]:
        return list(self._agents)


class _FakeRegistry:
    def __init__(self, agents: dict[str, type]) -> None:
        self.agents = _FakeRegistrySection(agents)


class _PatchableExecutor(OpenCodeStepExecutor):
    """Executor with the client construction monkey-patched."""

    def __init__(
        self,
        client: _FakeClient,
        *,
        agents: dict[str, type] | None = None,
    ) -> None:
        super().__init__(
            agent_registry=_FakeRegistry(agents or {"agent": _FakeAgent}),
            server_handle=_fake_handle(),
        )
        self._fake_client = client

    async def _ensure_client(self) -> Any:  # type: ignore[override]
        if self._client is None:
            self._client = self._fake_client  # type: ignore[assignment]
        return self._fake_client


@pytest.fixture(autouse=True)
def _clean_validation_cache() -> AsyncIterator[None]:
    invalidate_cache()
    yield
    invalidate_cache()


def _text_send_result(text: str, *, info: dict[str, Any] | None = None) -> SendResult:
    msg_info = info or {"providerID": "openrouter", "modelID": "anthropic/claude-haiku-4.5"}
    return SendResult(
        message={"info": msg_info, "parts": [{"type": "text", "text": text}]},
        text=text,
        structured=None,
        valid=False,
        info=msg_info,
    )


def _structured_send_result(structured: dict[str, Any]) -> SendResult:
    info = {
        "providerID": "openrouter",
        "modelID": "anthropic/claude-haiku-4.5",
        "structured": structured,
        "tokens": {"input": 100, "output": 50, "cache": {"read": 0, "write": 0}},
        "cost": 0.001,
    }
    return SendResult(
        message={"info": info, "parts": []},
        text="",
        structured=structured,
        valid=True,
        info=info,
    )


# ---------------------------------------------------------------------------
# execute() — the StepExecutor Protocol method
# ---------------------------------------------------------------------------


async def test_execute_returns_text_for_plain_prompt() -> None:
    client = _FakeClient(send_result=_text_send_result("hello world"))
    executor = _PatchableExecutor(client)
    try:
        result = await executor.execute(
            step_name="ping",
            agent_name="agent",
            prompt={"prompt": "say hi"},
        )
        assert isinstance(result, ExecutorResult)
        assert result.success is True
        assert result.output == "hello world"
        # No format block when output_schema isn't set.
        assert client.send_calls[0]["format"] is None
    finally:
        await executor.cleanup()


async def test_execute_with_output_schema_validates_structured_payload() -> None:
    class Result(BaseModel):
        verdict: str
        score: int

    client = _FakeClient(send_result=_structured_send_result({"verdict": "green", "score": 95}))
    executor = _PatchableExecutor(client)
    try:
        result = await executor.execute(
            step_name="judge",
            agent_name="agent",
            prompt={"prompt": "evaluate"},
            output_schema=Result,
        )
        assert isinstance(result.output, Result)
        assert result.output.verdict == "green"
        assert result.output.score == 95
        # format=json_schema was passed through
        fmt = client.send_calls[0]["format"]
        assert fmt is not None and fmt["type"] == "json_schema"
    finally:
        await executor.cleanup()


async def test_execute_with_output_schema_falls_back_to_json_in_text() -> None:
    """When the model returns text instead of a StructuredOutput call, the
    executor falls back to JSON extraction — same defence-in-depth as the
    legacy executor."""

    class Result(BaseModel):
        ok: bool

    client = _FakeClient(
        send_result=_text_send_result(
            'Here you go:\n```json\n{"ok": true}\n```',
        )
    )
    executor = _PatchableExecutor(client)
    try:
        result = await executor.execute(
            step_name="probe",
            agent_name="agent",
            prompt={"prompt": "json please"},
            output_schema=Result,
        )
        assert isinstance(result.output, Result)
        assert result.output.ok is True
    finally:
        await executor.cleanup()


async def test_execute_with_output_schema_raises_validation_error_for_bad_payload() -> None:
    class Result(BaseModel):
        verdict: str
        score: int

    client = _FakeClient(
        send_result=_structured_send_result({"unexpected": "field"}),
    )
    executor = _PatchableExecutor(client)
    try:
        with pytest.raises(OutputSchemaValidationError):
            await executor.execute(
                step_name="judge",
                agent_name="agent",
                prompt={"prompt": "x"},
                output_schema=Result,
            )
    finally:
        await executor.cleanup()


async def test_execute_emits_usage_metadata_when_info_has_tokens() -> None:
    class Result(BaseModel):
        ok: bool

    client = _FakeClient(send_result=_structured_send_result({"ok": True}))
    executor = _PatchableExecutor(client)
    try:
        result = await executor.execute(
            step_name="probe",
            agent_name="agent",
            prompt={"prompt": "x"},
            output_schema=Result,
        )
        assert result.usage is not None
        assert result.usage.input_tokens == 100
        assert result.usage.output_tokens == 50
        assert result.usage.total_cost_usd == 0.001
        assert result.model_label == "openrouter/anthropic/claude-haiku-4.5"
    finally:
        await executor.cleanup()


async def test_execute_resolves_dashed_agent_name_to_underscored_alias() -> None:
    client = _FakeClient(send_result=_text_send_result("ok"))
    executor = _PatchableExecutor(client, agents={"my_agent": _FakeAgent})
    try:
        # Caller passes hyphenated form; executor finds the underscored one.
        result = await executor.execute(
            step_name="x",
            agent_name="my-agent",
            prompt={"prompt": "x"},
        )
        assert result.success
    finally:
        await executor.cleanup()


async def test_execute_validates_model_id_before_sending() -> None:
    """When config supplies provider+model_id, validate against /provider first."""
    client = _FakeClient(send_result=_text_send_result("ok"))
    executor = _PatchableExecutor(client)
    try:
        await executor.execute(
            step_name="x",
            agent_name="agent",
            prompt={"prompt": "x"},
            config=StepConfig(provider="openrouter", model_id="anthropic/claude-haiku-4.5"),
        )
        assert client.list_provider_calls == 1
        # Model block was passed through
        assert client.send_calls[0]["model"] == {
            "providerID": "openrouter",
            "modelID": "anthropic/claude-haiku-4.5",
        }
    finally:
        await executor.cleanup()


async def test_execute_propagates_classified_runtime_errors() -> None:
    client = _FakeClient(send_error=OpenCodeAuthError("bad key"))
    executor = _PatchableExecutor(client)
    try:
        with pytest.raises(OpenCodeAuthError):
            await executor.execute(
                step_name="x",
                agent_name="agent",
                prompt={"prompt": "x"},
            )
    finally:
        await executor.cleanup()


async def test_execute_deletes_per_step_session_after_completion() -> None:
    client = _FakeClient(send_result=_text_send_result("ok"))
    executor = _PatchableExecutor(client)
    try:
        await executor.execute(step_name="x", agent_name="agent", prompt={"prompt": "x"})
        # The one-shot session created for this execute() call should be
        # cleaned up immediately, not left dangling.
        assert client.created_sessions == ["step:x"]
        assert client.deleted_sessions == [client.created_sessions and "ses_0"]
    finally:
        await executor.cleanup()


# ---------------------------------------------------------------------------
# Multi-turn create_session / prompt_session
# ---------------------------------------------------------------------------


async def test_create_session_returns_id_and_caches_state() -> None:
    client = _FakeClient(send_result=_text_send_result("ok"))
    executor = _PatchableExecutor(client)
    try:
        sid = await executor.create_session(
            config=StepConfig(provider="openrouter", model_id="anthropic/claude-haiku-4.5"),
            cwd=None,
            step_name="multi",
            agent_name="agent",
        )
        assert sid == "ses_0"
        # Validation ran once at create_session time.
        assert client.list_provider_calls == 1
    finally:
        await executor.cleanup()


async def test_prompt_session_reuses_existing_session() -> None:
    client = _FakeClient(send_result=_text_send_result("first"))
    executor = _PatchableExecutor(client)
    try:
        sid = await executor.create_session(
            config=StepConfig(provider="openrouter", model_id="anthropic/claude-haiku-4.5"),
            step_name="multi",
        )
        # First prompt
        first = await executor.prompt_session(
            session_id=sid, prompt_text="initial", step_name="multi"
        )
        assert first.output == "first"
        # Second prompt — same session id
        client._send_result = _text_send_result("second")
        second = await executor.prompt_session(
            session_id=sid, prompt_text="follow up", step_name="multi"
        )
        assert second.output == "second"
        assert client.send_calls[0]["session_id"] == sid
        assert client.send_calls[1]["session_id"] == sid
    finally:
        await executor.cleanup()


async def test_prompt_session_raises_for_unknown_session() -> None:
    from maverick.exceptions.agent import AgentError

    client = _FakeClient()
    executor = _PatchableExecutor(client)
    try:
        with pytest.raises(AgentError):
            await executor.prompt_session(session_id="ses_missing", prompt_text="hi")
    finally:
        await executor.cleanup()


async def test_cancel_session_calls_client_cancel() -> None:
    client = _FakeClient(send_result=_text_send_result("ok"))
    executor = _PatchableExecutor(client)
    try:
        sid = await executor.create_session(step_name="x")
        await executor.cancel_session(sid)
        assert client.cancelled == [sid]
    finally:
        await executor.cleanup()


async def test_close_session_drops_state_and_calls_delete() -> None:
    client = _FakeClient(send_result=_text_send_result("ok"))
    executor = _PatchableExecutor(client)
    try:
        sid = await executor.create_session(step_name="x")
        await executor.close_session(sid)
        assert sid in client.deleted_sessions
        # close_session is idempotent
        await executor.close_session(sid)
    finally:
        await executor.cleanup()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


async def test_cleanup_deletes_sessions_and_closes_client() -> None:
    client = _FakeClient(send_result=_text_send_result("ok"))
    executor = _PatchableExecutor(client)
    sid = await executor.create_session(step_name="x")
    await executor.cleanup()
    assert sid in client.deleted_sessions
    assert client.closed is True


async def test_cleanup_for_eviction_invokes_session_invalidator() -> None:
    client = _FakeClient(send_result=_text_send_result("ok"))
    executor = _PatchableExecutor(client)
    invalidator_called = False

    async def invalidator() -> None:
        nonlocal invalidator_called
        invalidator_called = True

    executor.set_session_invalidator(invalidator)
    try:
        await executor.create_session(step_name="x")
        await executor.cleanup_for_eviction()
        assert invalidator_called is True
        assert client.closed is True
    finally:
        # Ensure the spawned-handle teardown still runs even though we
        # only called eviction (which should NOT touch the handle).
        await executor.cleanup()
