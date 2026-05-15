"""Unit tests for :class:`CopilotRuntime`.

Mocks :mod:`copilot` at the boundary — no real ``copilot`` CLI
subprocess, no real GitHub Copilot calls. Validates:

* Binding validation (Copilot bindings pass; non-Copilot bindings
  rejected; ``claude-*`` model IDs rejected even with a Copilot
  provider, per Phase 0 spike finding).
* Structured-output happy path captures the tool args.
* Missing tool call → :class:`RuntimeStructuredOutputError`.
* Session error events → classified into the runtime hierarchy
  (auth / model-not-found / transient / protocol).
* CLI-not-found → :class:`RuntimeServerStartError`.
* Cost record populated from :class:`AssistantUsageData` event.
* ``reset()`` destroys the session; ``aclose()`` also disconnects.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from maverick.runtime.copilot_adapter import (
    SUBMIT_RESULT_TOOL,
    CopilotRuntime,
)
from maverick.runtime.errors import (
    AgentRuntimeError,
    RuntimeAuthError,
    RuntimeModelNotFoundError,
    RuntimeProtocolError,
    RuntimeServerStartError,
    RuntimeStructuredOutputError,
    RuntimeTransientError,
)
from maverick.runtime.protocol import UnsupportedBindingError
from maverick.runtime.tiers import ProviderModel


class _Schema(BaseModel):
    summary: str
    count: int


class _FakeUsage:
    """Stand-in for ``AssistantUsageData``."""

    def __init__(
        self,
        *,
        cost: float | None = 0.0034,
        input_tokens: float | None = 120,
        output_tokens: float | None = 240,
        cache_read_tokens: float | None = 80,
        cache_write_tokens: float | None = 15,
        model: str = "gpt-5-mini",
    ) -> None:
        self.cost = cost
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_tokens = cache_read_tokens
        self.cache_write_tokens = cache_write_tokens
        self.model = model


class _FakeAssistantMessage:
    """Stand-in for ``AssistantMessageData``."""

    def __init__(self, content: str = "") -> None:
        self.content = content


class _FakeSessionError:
    """Stand-in for ``SessionErrorData``."""

    def __init__(
        self,
        *,
        message: str = "boom",
        error_type: str = "unknown",
        status_code: int | None = None,
    ) -> None:
        self.message = message
        self.error_type = error_type
        self.status_code = status_code


class _FakeEvent:
    def __init__(self, data: Any) -> None:
        self.data = data


@pytest.fixture
def mock_sdk(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Mock the ``copilot`` SDK symbols ``CopilotRuntime`` imports lazily.

    Patches the SDK modules that ``_ensure_client`` / ``_ensure_session``
    pull at runtime:

    * ``copilot.CopilotClient`` — factory that returns a mock client.
    * ``copilot.SubprocessConfig`` — passthrough (stores kwargs).
    * ``copilot.define_tool`` — returns a mock tool, captures handler.
    * ``copilot.session.PermissionHandler`` — exposes ``approve_all``.
    * ``copilot.generated.session_events`` types — substituted with our
      fake classes so the ``isinstance`` dispatch in ``_on_event`` fires.
    """
    import copilot
    from copilot import session as session_mod
    from copilot.generated import session_events as se_mod

    # --- Client + session mocks ---------------------------------------
    mock_session = MagicMock()
    mock_session.send_and_wait = AsyncMock()
    mock_session.destroy = AsyncMock()
    mock_session.on = MagicMock()

    mock_client = MagicMock()
    mock_client.create_session = AsyncMock(return_value=mock_session)
    mock_client.stop = AsyncMock()

    captured_subprocess_kwargs: dict[str, Any] = {}

    def fake_subprocess_config(**kwargs: Any) -> dict[str, Any]:
        captured_subprocess_kwargs.update(kwargs)
        return kwargs

    mock_client_factory = MagicMock(return_value=mock_client)

    # --- Tool capture --------------------------------------------------
    captured_tools: list[dict[str, Any]] = []

    def fake_define_tool(
        name: str,
        *,
        description: str,
        handler: Any,
        params_type: type[BaseModel],
        skip_permission: bool = False,
    ) -> Any:
        tool_obj = MagicMock()
        tool_obj.name = name
        captured_tools.append(
            {
                "name": name,
                "description": description,
                "handler": handler,
                "params_type": params_type,
                "skip_permission": skip_permission,
                "tool_obj": tool_obj,
            }
        )
        return tool_obj

    # --- Permission handler -------------------------------------------
    mock_perm_handler = MagicMock()
    mock_perm_handler.approve_all = lambda req, inv: MagicMock(kind="approve-once")

    monkeypatch.setattr(copilot, "CopilotClient", mock_client_factory)
    monkeypatch.setattr(copilot, "SubprocessConfig", fake_subprocess_config)
    monkeypatch.setattr(copilot, "define_tool", fake_define_tool)
    monkeypatch.setattr(session_mod, "PermissionHandler", mock_perm_handler)

    # Substitute the event-data classes so isinstance() in _on_event
    # matches our fakes.
    monkeypatch.setattr(se_mod, "AssistantUsageData", _FakeUsage)
    monkeypatch.setattr(se_mod, "AssistantMessageData", _FakeAssistantMessage)
    monkeypatch.setattr(se_mod, "SessionErrorData", _FakeSessionError)

    return {
        "client_factory": mock_client_factory,
        "client": mock_client,
        "session": mock_session,
        "subprocess_kwargs": captured_subprocess_kwargs,
        "captured_tools": captured_tools,
    }


# ---------------------------------------------------------------------------
# Binding validation
# ---------------------------------------------------------------------------


def test_validate_binding_accepts_copilot_providers() -> None:
    rt = CopilotRuntime()
    assert rt.validate_binding(ProviderModel("copilot", "gpt-5-mini"))
    assert rt.validate_binding(ProviderModel("github-copilot", "gpt-4o"))
    assert rt.validate_binding(ProviderModel("github", "o5"))


def test_validate_binding_rejects_non_copilot_providers() -> None:
    rt = CopilotRuntime()
    assert not rt.validate_binding(ProviderModel("anthropic", "claude-haiku-4-5"))
    assert not rt.validate_binding(ProviderModel("openai", "gpt-5-mini"))
    assert not rt.validate_binding(ProviderModel("opencode", "gpt-5-nano"))


def test_validate_binding_rejects_claude_models_on_copilot() -> None:
    """Phase 0 finding: Claude served via Copilot can't honour tool calls."""
    rt = CopilotRuntime()
    assert not rt.validate_binding(ProviderModel("copilot", "claude-sonnet-4.6"))
    assert not rt.validate_binding(ProviderModel("github-copilot", "claude-opus-4.7"))


# ---------------------------------------------------------------------------
# execute() — shape checks before we hit the SDK
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_text_only_not_implemented() -> None:
    rt = CopilotRuntime()
    with pytest.raises(NotImplementedError):
        await rt.execute("hello")


@pytest.mark.asyncio
async def test_execute_rejects_unsupported_binding() -> None:
    rt = CopilotRuntime()
    with pytest.raises(UnsupportedBindingError):
        await rt.execute(
            "hi",
            schema=_Schema,
            model=ProviderModel("anthropic", "claude-haiku-4-5"),
        )


@pytest.mark.asyncio
async def test_execute_rejects_claude_on_copilot() -> None:
    rt = CopilotRuntime()
    with pytest.raises(UnsupportedBindingError):
        await rt.execute(
            "hi",
            schema=_Schema,
            model=ProviderModel("copilot", "claude-opus-4.7"),
        )


# ---------------------------------------------------------------------------
# execute() — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_captures_structured_output(mock_sdk: dict[str, Any]) -> None:
    """submit_result tool handler fires → captured payload land in RuntimeResult."""
    rt = CopilotRuntime()

    expected_payload = _Schema(summary="ok", count=42)

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        # Simulate the SDK invoking our submit_result handler.
        rt._captured_payload = expected_payload
        # Simulate the SDK emitting an assistant-message + usage event.
        rt._on_event(_FakeEvent(_FakeAssistantMessage(content="see tool call")))
        rt._on_event(_FakeEvent(_FakeUsage()))
        return _FakeEvent(_FakeAssistantMessage(content="see tool call"))

    mock_sdk["session"].send_and_wait = fake_send_and_wait

    result = await rt.execute(
        "say hi",
        schema=_Schema,
        model=ProviderModel("copilot", "gpt-5-mini"),
    )

    assert result.structured == {"summary": "ok", "count": 42}
    assert result.finish == "stop"
    assert result.cost.cost_usd == pytest.approx(0.0034)
    assert result.cost.input_tokens == 120
    assert result.cost.output_tokens == 240
    assert result.cost.cache_read_tokens == 80
    assert result.cost.cache_write_tokens == 15
    assert result.cost.provider_id == "github-copilot"
    assert result.cost.model_id == "gpt-5-mini"


@pytest.mark.asyncio
async def test_execute_uses_default_model_when_unspecified(mock_sdk: dict[str, Any]) -> None:
    rt = CopilotRuntime(model="o5-pro")

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        rt._captured_payload = _Schema(summary="ok", count=1)

    mock_sdk["session"].send_and_wait = fake_send_and_wait

    result = await rt.execute("hi", schema=_Schema)

    assert result.cost.model_id == "o5-pro"
    # The model was passed to create_session via kwargs.
    create_kwargs = mock_sdk["client"].create_session.call_args.kwargs
    assert create_kwargs["model"] == "o5-pro"


@pytest.mark.asyncio
async def test_execute_registers_submit_result_tool(mock_sdk: dict[str, Any]) -> None:
    rt = CopilotRuntime()

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        rt._captured_payload = _Schema(summary="ok", count=1)

    mock_sdk["session"].send_and_wait = fake_send_and_wait
    await rt.execute("hi", schema=_Schema)

    tools = mock_sdk["captured_tools"]
    assert len(tools) == 1
    submit = tools[0]
    assert submit["name"] == SUBMIT_RESULT_TOOL
    assert submit["params_type"] is _Schema
    assert submit["skip_permission"] is True


@pytest.mark.asyncio
async def test_execute_system_message_includes_force_prefix(
    mock_sdk: dict[str, Any],
) -> None:
    rt = CopilotRuntime()

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        rt._captured_payload = _Schema(summary="ok", count=1)

    mock_sdk["session"].send_and_wait = fake_send_and_wait
    await rt.execute("hi", schema=_Schema, system="You are the navigator.")

    kwargs = mock_sdk["client"].create_session.call_args.kwargs
    sysmsg = kwargs["system_message"]
    assert sysmsg["mode"] == "append"
    assert SUBMIT_RESULT_TOOL in sysmsg["content"]
    assert "You are the navigator." in sysmsg["content"]


# ---------------------------------------------------------------------------
# execute() — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_missing_tool_call_raises_structured_output_error(
    mock_sdk: dict[str, Any],
) -> None:
    """If the model finishes without calling submit_result, we raise."""
    rt = CopilotRuntime()

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        # Assistant emits text but never calls submit_result.
        rt._on_event(_FakeEvent(_FakeAssistantMessage(content="here is your answer")))

    mock_sdk["session"].send_and_wait = fake_send_and_wait

    with pytest.raises(RuntimeStructuredOutputError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_session_error_auth(mock_sdk: dict[str, Any]) -> None:
    rt = CopilotRuntime()

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        rt._on_event(
            _FakeEvent(
                _FakeSessionError(message="unauthorized", error_type="auth", status_code=401)
            )
        )

    mock_sdk["session"].send_and_wait = fake_send_and_wait

    with pytest.raises(RuntimeAuthError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_session_error_model_not_found(mock_sdk: dict[str, Any]) -> None:
    rt = CopilotRuntime()

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        rt._on_event(
            _FakeEvent(
                _FakeSessionError(
                    message="no such model", error_type="model_not_found", status_code=404
                )
            )
        )

    mock_sdk["session"].send_and_wait = fake_send_and_wait

    with pytest.raises(RuntimeModelNotFoundError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_session_error_transient_429(mock_sdk: dict[str, Any]) -> None:
    rt = CopilotRuntime()

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        rt._on_event(
            _FakeEvent(
                _FakeSessionError(message="rate limited", error_type="rate_limit", status_code=429)
            )
        )

    mock_sdk["session"].send_and_wait = fake_send_and_wait

    with pytest.raises(RuntimeTransientError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_session_error_5xx_is_transient(mock_sdk: dict[str, Any]) -> None:
    rt = CopilotRuntime()

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        rt._on_event(
            _FakeEvent(
                _FakeSessionError(message="server hosed", error_type="upstream", status_code=502)
            )
        )

    mock_sdk["session"].send_and_wait = fake_send_and_wait

    with pytest.raises(RuntimeTransientError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_session_error_other_is_protocol(mock_sdk: dict[str, Any]) -> None:
    rt = CopilotRuntime()

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        rt._on_event(
            _FakeEvent(
                _FakeSessionError(message="weirdness", error_type="other", status_code=None)
            )
        )

    mock_sdk["session"].send_and_wait = fake_send_and_wait

    with pytest.raises(RuntimeProtocolError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_timeout_raises_transient_error(mock_sdk: dict[str, Any]) -> None:
    rt = CopilotRuntime()

    async def slow(prompt: str, *, timeout: float = 60.0) -> Any:
        import asyncio

        await asyncio.sleep(10)

    mock_sdk["session"].send_and_wait = slow

    with pytest.raises(RuntimeTransientError):
        await rt.execute("hi", schema=_Schema, timeout=0.05)


@pytest.mark.asyncio
async def test_execute_cli_not_found_raises_server_start_error(
    mock_sdk: dict[str, Any],
) -> None:
    rt = CopilotRuntime()
    mock_sdk["client_factory"].side_effect = FileNotFoundError("no copilot CLI on PATH")

    with pytest.raises(RuntimeServerStartError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_generic_sdk_failure_classifies_as_agent_error(
    mock_sdk: dict[str, Any],
) -> None:
    rt = CopilotRuntime()
    mock_sdk["client"].create_session.side_effect = RuntimeError("unknown failure")

    with pytest.raises(AgentRuntimeError):
        await rt.execute("hi", schema=_Schema)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_destroys_session(mock_sdk: dict[str, Any]) -> None:
    rt = CopilotRuntime()

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        rt._captured_payload = _Schema(summary="ok", count=1)

    mock_sdk["session"].send_and_wait = fake_send_and_wait
    await rt.execute("hi", schema=_Schema)
    assert rt._session is not None

    await rt.reset()
    assert rt._session is None
    assert mock_sdk["session"].destroy.await_count >= 1


@pytest.mark.asyncio
async def test_aclose_destroys_session_and_disconnects_client(
    mock_sdk: dict[str, Any],
) -> None:
    rt = CopilotRuntime()

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        rt._captured_payload = _Schema(summary="ok", count=1)

    mock_sdk["session"].send_and_wait = fake_send_and_wait
    await rt.execute("hi", schema=_Schema)

    await rt.aclose()
    assert rt._client is None
    assert rt._session is None
    assert mock_sdk["client"].stop.await_count >= 1


@pytest.mark.asyncio
async def test_reset_with_no_session_is_noop() -> None:
    rt = CopilotRuntime()
    await rt.reset()
    await rt.aclose()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explicit_github_token_threaded_to_subprocess_config(
    mock_sdk: dict[str, Any],
) -> None:
    rt = CopilotRuntime(github_token="ghu_test_token")

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        rt._captured_payload = _Schema(summary="ok", count=1)

    mock_sdk["session"].send_and_wait = fake_send_and_wait
    await rt.execute("hi", schema=_Schema)

    kwargs = mock_sdk["subprocess_kwargs"]
    assert kwargs.get("github_token") == "ghu_test_token"
    assert "use_logged_in_user" not in kwargs


@pytest.mark.asyncio
async def test_no_token_falls_back_to_logged_in_user(
    mock_sdk: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    rt = CopilotRuntime()

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        rt._captured_payload = _Schema(summary="ok", count=1)

    mock_sdk["session"].send_and_wait = fake_send_and_wait
    await rt.execute("hi", schema=_Schema)

    kwargs = mock_sdk["subprocess_kwargs"]
    assert kwargs.get("use_logged_in_user") is True
    assert "github_token" not in kwargs


@pytest.mark.asyncio
async def test_env_token_picked_up(
    mock_sdk: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")
    rt = CopilotRuntime()

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        rt._captured_payload = _Schema(summary="ok", count=1)

    mock_sdk["session"].send_and_wait = fake_send_and_wait
    await rt.execute("hi", schema=_Schema)

    kwargs = mock_sdk["subprocess_kwargs"]
    assert kwargs.get("github_token") == "ghp_from_env"


# ---------------------------------------------------------------------------
# Session caching
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_reused_when_schema_and_model_match(
    mock_sdk: dict[str, Any],
) -> None:
    rt = CopilotRuntime()

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        rt._captured_payload = _Schema(summary="ok", count=1)

    mock_sdk["session"].send_and_wait = fake_send_and_wait

    await rt.execute("hi", schema=_Schema)
    await rt.execute("hi again", schema=_Schema)

    # create_session should have been called exactly once across the two execute() calls.
    assert mock_sdk["client"].create_session.await_count == 1


@pytest.mark.asyncio
async def test_session_recreated_when_system_changes(mock_sdk: dict[str, Any]) -> None:
    rt = CopilotRuntime()

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        rt._captured_payload = _Schema(summary="ok", count=1)

    mock_sdk["session"].send_and_wait = fake_send_and_wait

    await rt.execute("hi", schema=_Schema, system="persona A")
    await rt.execute("hi again", schema=_Schema, system="persona B")

    assert mock_sdk["client"].create_session.await_count == 2
    assert mock_sdk["session"].destroy.await_count >= 1


# ---------------------------------------------------------------------------
# Cost path when usage is missing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_record_returns_zero_when_no_usage_event(
    mock_sdk: dict[str, Any],
) -> None:
    rt = CopilotRuntime()

    async def fake_send_and_wait(prompt: str, *, timeout: float = 60.0) -> Any:
        rt._captured_payload = _Schema(summary="ok", count=1)
        # Deliberately do not emit a usage event.

    mock_sdk["session"].send_and_wait = fake_send_and_wait
    result = await rt.execute("hi", schema=_Schema)

    assert result.cost.cost_usd is None
    assert result.cost.input_tokens == 0
    assert result.cost.output_tokens == 0
    assert result.cost.provider_id == "github-copilot"


def test_submit_result_tool_name_canonical() -> None:
    """The tool name is stable — referenced by the forced system prefix."""
    assert SUBMIT_RESULT_TOOL == "submit_result"
