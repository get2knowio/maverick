"""Unit tests for :class:`ClaudeCodeRuntime`.

Mocks :mod:`claude_agent_sdk` at the boundary — no real subprocess, no
real Anthropic calls. Validates:

* Binding validation (Claude bindings pass; non-Claude bindings rejected).
* Structured-output happy path captures the tool args.
* Missing tool call → :class:`RuntimeStructuredOutputError`.
* SDK auth failure → :class:`RuntimeAuthError`.
* SDK transient → :class:`RuntimeTransientError`.
* SDK CLI-not-found → :class:`RuntimeServerStartError`.
* Cost record populated from ``ResultMessage.usage`` + ``total_cost_usd``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from maverick.runtime.claude_code_adapter import (
    SUBMIT_RESULT_TOOL,
    ClaudeCodeRuntime,
)
from maverick.runtime.errors import (
    AgentRuntimeError,
    RuntimeAuthError,
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


class _FakeResultMessage:
    """Stand-in for ``claude_agent_sdk.ResultMessage``.

    A real class (not MagicMock) so the runtime's
    ``isinstance(msg, ResultMessage)`` check succeeds when the SDK
    symbol is monkeypatched to this type.
    """

    def __init__(
        self,
        *,
        is_error: bool = False,
        stop_reason: str | None = "end_turn",
        result: str | None = "",
        total_cost_usd: float | None = 0.05,
        usage: dict[str, Any] | None = None,
        subtype: str | None = None,
        errors: list[str] | None = None,
    ) -> None:
        self.is_error = is_error
        self.stop_reason = stop_reason
        self.result = result
        self.total_cost_usd = total_cost_usd
        self.usage = usage or {
            "input_tokens": 100,
            "output_tokens": 200,
            "cache_read_input_tokens": 50,
            "cache_creation_input_tokens": 10,
        }
        self.subtype = subtype
        self.errors = errors


@pytest.fixture
def mock_sdk(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Mock the ``claude_agent_sdk`` symbols ``ClaudeCodeRuntime`` imports lazily.

    Returns a dict of the mock objects so tests can program return values.
    """
    import claude_agent_sdk as sdk

    mock_client = MagicMock()
    mock_client.connect = AsyncMock()
    mock_client.disconnect = AsyncMock()
    mock_client.query = AsyncMock()
    mock_client_factory = MagicMock(return_value=mock_client)

    mock_server = MagicMock()

    def fake_tool(
        name: str,
        description: str,
        input_schema: Any,
    ) -> Any:
        """Stand-in ``@tool`` decorator that returns the wrapped function."""

        def decorator(fn: Any) -> Any:
            fn._tool_name = name
            return fn

        return decorator

    monkeypatch.setattr(sdk, "ClaudeSDKClient", mock_client_factory)
    monkeypatch.setattr(sdk, "ClaudeAgentOptions", MagicMock())
    monkeypatch.setattr(sdk, "create_sdk_mcp_server", MagicMock(return_value=mock_server))
    monkeypatch.setattr(sdk, "tool", fake_tool)
    monkeypatch.setattr(sdk, "ResultMessage", _FakeResultMessage)

    return {
        "ClaudeSDKClient": mock_client_factory,
        "client": mock_client,
        "ResultMessage": _FakeResultMessage,
    }


def test_validate_binding_accepts_claude_providers() -> None:
    rt = ClaudeCodeRuntime()
    assert rt.validate_binding(ProviderModel("anthropic", "claude-haiku-4-5"))
    assert rt.validate_binding(ProviderModel("claude-code", "claude-sonnet-4.6"))
    assert rt.validate_binding(ProviderModel("claude-sdk", "claude-opus-4.7"))


def test_validate_binding_rejects_non_claude_providers() -> None:
    rt = ClaudeCodeRuntime()
    assert not rt.validate_binding(ProviderModel("github-copilot", "gpt-5.3-codex"))
    assert not rt.validate_binding(ProviderModel("openai", "gpt-5.5"))


@pytest.mark.asyncio
async def test_execute_rejects_unsupported_binding() -> None:
    rt = ClaudeCodeRuntime()
    with pytest.raises(UnsupportedBindingError):
        await rt.execute(
            "hello",
            schema=_Schema,
            model=ProviderModel("github-copilot", "gpt-5.3-codex"),
        )


@pytest.mark.asyncio
async def test_execute_text_only_not_implemented() -> None:
    rt = ClaudeCodeRuntime()
    with pytest.raises(NotImplementedError):
        await rt.execute("hello")


@pytest.mark.asyncio
async def test_execute_captures_structured_output(mock_sdk: dict[str, MagicMock]) -> None:
    """Tool callback fires → captured args land in RuntimeResult.structured."""
    rt = ClaudeCodeRuntime()

    expected_args = {"summary": "ok", "count": 42}
    final = _FakeResultMessage()

    async def fake_receive() -> Any:
        # Simulate the SDK firing the @sdk_tool callback during the stream.
        # In production the SDK calls into the user-defined tool via MCP;
        # for the unit test we invoke the captured closure directly.
        assert rt._captured_args is None  # noqa: SLF001 — internal-state check
        rt._captured_args = dict(expected_args)
        yield final

    mock_sdk["client"].receive_response = fake_receive

    result = await rt.execute(
        "say hi",
        schema=_Schema,
        model=ProviderModel("anthropic", "claude-haiku-4-5"),
    )

    assert result.structured == expected_args
    assert result.finish == "end_turn"
    assert result.cost.cost_usd == 0.05
    assert result.cost.input_tokens == 100
    assert result.cost.output_tokens == 200
    assert result.cost.cache_read_tokens == 50
    assert result.cost.cache_write_tokens == 10
    assert result.cost.provider_id == "anthropic"
    assert result.cost.model_id == "claude-haiku-4-5"


@pytest.mark.asyncio
async def test_execute_missing_tool_call_raises_structured_output_error(
    mock_sdk: dict[str, MagicMock],
) -> None:
    """If the model finishes without calling submit_result, we raise."""
    rt = ClaudeCodeRuntime()

    final = _FakeResultMessage(stop_reason="end_turn", result="I refuse to call the tool")

    async def fake_receive() -> Any:
        yield final  # No tool callback fired — captured_args stays None.

    mock_sdk["client"].receive_response = fake_receive

    with pytest.raises(RuntimeStructuredOutputError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_is_error_result_raises_runtime_error(
    mock_sdk: dict[str, MagicMock],
) -> None:
    rt = ClaudeCodeRuntime()

    final = _FakeResultMessage(
        is_error=True,
        subtype="error_max_turns",
        errors=["Reached max turns"],
    )

    async def fake_receive() -> Any:
        yield final

    mock_sdk["client"].receive_response = fake_receive

    with pytest.raises(AgentRuntimeError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_empty_stream_raises_protocol_error(
    mock_sdk: dict[str, MagicMock],
) -> None:
    rt = ClaudeCodeRuntime()

    async def fake_receive() -> Any:
        # No ResultMessage in the stream at all.
        if False:
            yield  # type: ignore[unreachable] — make this an async generator

    mock_sdk["client"].receive_response = fake_receive

    with pytest.raises(RuntimeProtocolError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_cli_not_found_raises_server_start_error(
    mock_sdk: dict[str, MagicMock],
) -> None:
    from claude_agent_sdk import CLINotFoundError

    rt = ClaudeCodeRuntime()
    mock_sdk["client"].connect.side_effect = CLINotFoundError("no claude CLI")

    with pytest.raises(RuntimeServerStartError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_auth_failure_raises_runtime_auth_error(
    mock_sdk: dict[str, MagicMock],
) -> None:
    from claude_agent_sdk import ClaudeSDKError

    rt = ClaudeCodeRuntime()
    mock_sdk["client"].connect.side_effect = ClaudeSDKError("401 unauthorized")

    with pytest.raises(RuntimeAuthError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_timeout_raises_transient_error(
    mock_sdk: dict[str, MagicMock],
) -> None:
    rt = ClaudeCodeRuntime()

    async def slow_receive() -> Any:
        import asyncio

        await asyncio.sleep(10)
        if False:
            yield  # type: ignore[unreachable]

    mock_sdk["client"].receive_response = slow_receive

    with pytest.raises(RuntimeTransientError):
        await rt.execute("hi", schema=_Schema, timeout=0.05)


@pytest.mark.asyncio
async def test_reset_disconnects_client(mock_sdk: dict[str, MagicMock]) -> None:
    rt = ClaudeCodeRuntime()
    # Force a client to exist by running one execute.
    final = _FakeResultMessage()

    async def fake_receive() -> Any:
        rt._captured_args = {"summary": "x", "count": 1}  # noqa: SLF001
        yield final

    mock_sdk["client"].receive_response = fake_receive
    await rt.execute("hi", schema=_Schema)
    assert rt._client is not None  # noqa: SLF001

    await rt.reset()
    assert rt._client is None  # noqa: SLF001
    assert mock_sdk["client"].disconnect.await_count >= 1


@pytest.mark.asyncio
async def test_reset_with_no_client_is_noop() -> None:
    rt = ClaudeCodeRuntime()
    # Should not raise even with no client constructed yet.
    await rt.reset()
    await rt.aclose()


def test_api_key_override_passes_through_env(mock_sdk: dict[str, MagicMock]) -> None:
    """When api_key= is passed, it lands in ClaudeAgentOptions.env."""
    import claude_agent_sdk as sdk

    captured_kwargs: dict[str, Any] = {}

    def capturing_options(**kwargs: Any) -> MagicMock:
        captured_kwargs.update(kwargs)
        return MagicMock()

    with patch.object(sdk, "ClaudeAgentOptions", side_effect=capturing_options):
        rt = ClaudeCodeRuntime(api_key="sk-ant-test-key")
        # _ensure_client constructs ClaudeAgentOptions; the api_key
        # should land in env. Run it directly (sync slice of the path).
        import asyncio

        async def go() -> None:
            await rt._ensure_client(schema=_Schema, system=None, model="claude-haiku-4-5")  # noqa: SLF001

        asyncio.get_event_loop().run_until_complete(go())

    env = captured_kwargs.get("env", {})
    assert env.get("ANTHROPIC_API_KEY") == "sk-ant-test-key"


def test_submit_result_tool_name_canonical() -> None:
    """The MCP tool name is stable — referenced by allowed_tools wiring."""
    assert SUBMIT_RESULT_TOOL == "submit_result"
