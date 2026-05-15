"""Unit tests for :class:`CodexRuntime`.

Mocks :mod:`openai_codex_sdk` at the boundary — no real ``codex`` CLI
subprocess, no real OpenAI calls. Validates:

* Binding validation (Codex bindings pass; non-Codex providers
  rejected; ``claude-*`` model IDs rejected even with an Openai/Codex
  provider).
* Structured-output happy path: JSON Schema passed via
  ``outputSchema``, ``Turn.final_response`` parsed as JSON.
* Empty / non-JSON final response → :class:`RuntimeStructuredOutputError`.
* SDK error classification: auth / install / exec / thread-run.
* Cost record populated from ``Turn.usage``.
* Lifecycle: ``reset()`` drops the thread; ``aclose()`` drops the client.
* Thread caching by model.
* Auth resolution chain: explicit key → env → opencode auth.json →
  fall-through.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from maverick.runtime.codex_adapter import (
    DEFAULT_CODEX_MODEL,
    CodexRuntime,
    _resolve_api_key,
)
from maverick.runtime.errors import (
    AgentRuntimeError,
    RuntimeAuthError,
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
    """Stand-in for ``openai_codex_sdk.Usage``."""

    def __init__(
        self,
        *,
        input_tokens: int = 120,
        output_tokens: int = 240,
        cached_input_tokens: int = 30,
    ) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cached_input_tokens = cached_input_tokens


_UNSET = object()


class _FakeTurn:
    """Stand-in for ``openai_codex_sdk.Turn``."""

    def __init__(
        self,
        *,
        final_response: str = '{"summary": "ok", "count": 42}',
        items: list[Any] | None = None,
        usage: Any = _UNSET,
    ) -> None:
        self.final_response = final_response
        self.items = items or []
        # Default to a populated _FakeUsage; pass usage=None to explicitly
        # exercise the cost-without-usage path.
        self.usage = _FakeUsage() if usage is _UNSET else usage


@pytest.fixture
def mock_sdk(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Mock the ``openai_codex_sdk`` symbols ``CodexRuntime`` imports lazily."""
    import openai_codex_sdk as sdk

    mock_thread = MagicMock()
    mock_thread.run = AsyncMock(return_value=_FakeTurn())
    mock_thread.id = None

    mock_client = MagicMock()
    mock_client.start_thread = MagicMock(return_value=mock_thread)

    captured_codex_options: dict[str, Any] = {}

    def fake_codex_factory(options: dict[str, Any] | None = None) -> Any:
        captured_codex_options.update(options or {})
        return mock_client

    monkeypatch.setattr(sdk, "Codex", fake_codex_factory)

    return {
        "client": mock_client,
        "thread": mock_thread,
        "codex_options": captured_codex_options,
    }


# ---------------------------------------------------------------------------
# Binding validation
# ---------------------------------------------------------------------------


def test_validate_binding_accepts_codex_providers() -> None:
    rt = CodexRuntime()
    assert rt.validate_binding(ProviderModel("openai", "gpt-5-codex"))
    assert rt.validate_binding(ProviderModel("codex", "gpt-5-codex"))
    assert rt.validate_binding(ProviderModel("openai", "o5-codex"))


def test_validate_binding_rejects_non_codex_providers() -> None:
    rt = CodexRuntime()
    assert not rt.validate_binding(ProviderModel("anthropic", "claude-haiku-4-5"))
    assert not rt.validate_binding(ProviderModel("copilot", "gpt-5-mini"))
    assert not rt.validate_binding(ProviderModel("opencode", "gpt-5-nano"))


def test_validate_binding_rejects_claude_models_on_codex() -> None:
    rt = CodexRuntime()
    assert not rt.validate_binding(ProviderModel("openai", "claude-sonnet-4.6"))
    assert not rt.validate_binding(ProviderModel("codex", "claude-opus-4.7"))


# ---------------------------------------------------------------------------
# execute() — shape checks before we hit the SDK
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_text_only_not_implemented() -> None:
    rt = CodexRuntime()
    with pytest.raises(NotImplementedError):
        await rt.execute("hello")


@pytest.mark.asyncio
async def test_execute_rejects_unsupported_binding() -> None:
    rt = CodexRuntime()
    with pytest.raises(UnsupportedBindingError):
        await rt.execute(
            "hi",
            schema=_Schema,
            model=ProviderModel("anthropic", "claude-haiku-4-5"),
        )


@pytest.mark.asyncio
async def test_execute_rejects_claude_on_codex() -> None:
    rt = CodexRuntime()
    with pytest.raises(UnsupportedBindingError):
        await rt.execute(
            "hi",
            schema=_Schema,
            model=ProviderModel("openai", "claude-sonnet-4.6"),
        )


# ---------------------------------------------------------------------------
# execute() — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_captures_structured_output(mock_sdk: dict[str, Any]) -> None:
    rt = CodexRuntime()

    result = await rt.execute(
        "What is 17 + 25?",
        schema=_Schema,
        model=ProviderModel("openai", "gpt-5-codex"),
    )

    assert result.structured == {"summary": "ok", "count": 42}
    assert result.finish == "stop"
    assert result.text == '{"summary": "ok", "count": 42}'
    assert result.cost.cost_usd is not None  # gpt-5-codex is in the pricing map
    assert result.cost.input_tokens == 120
    assert result.cost.output_tokens == 240
    assert result.cost.cache_read_tokens == 30
    assert result.cost.cache_write_tokens == 0
    assert result.cost.provider_id == "openai"
    assert result.cost.model_id == "gpt-5-codex"


@pytest.mark.asyncio
async def test_execute_passes_output_schema(mock_sdk: dict[str, Any]) -> None:
    rt = CodexRuntime()
    await rt.execute("hi", schema=_Schema)

    call_args = mock_sdk["thread"].run.call_args
    prompt_arg, turn_options = call_args.args
    assert prompt_arg == "hi"
    assert turn_options["outputSchema"] == _Schema.model_json_schema()


@pytest.mark.asyncio
async def test_execute_prepends_system_to_prompt(mock_sdk: dict[str, Any]) -> None:
    rt = CodexRuntime()
    await rt.execute("user prompt", schema=_Schema, system="You are the implementer.")

    call_args = mock_sdk["thread"].run.call_args
    prompt_arg, _opts = call_args.args
    assert prompt_arg == "You are the implementer.\n\nuser prompt"


@pytest.mark.asyncio
async def test_execute_uses_default_model_when_unspecified(mock_sdk: dict[str, Any]) -> None:
    rt = CodexRuntime(model="o5-codex")
    result = await rt.execute("hi", schema=_Schema)

    assert result.cost.model_id == "o5-codex"
    thread_opts = mock_sdk["client"].start_thread.call_args.args[0]
    assert thread_opts["model"] == "o5-codex"


@pytest.mark.asyncio
async def test_execute_falls_back_to_default_when_no_model_in_runtime(
    mock_sdk: dict[str, Any],
) -> None:
    rt = CodexRuntime()
    result = await rt.execute("hi", schema=_Schema)

    assert result.cost.model_id == DEFAULT_CODEX_MODEL


@pytest.mark.asyncio
async def test_execute_threads_sandbox_mode_and_skip_git(mock_sdk: dict[str, Any]) -> None:
    rt = CodexRuntime(sandbox_mode="workspace-write", skip_git_repo_check=False)
    await rt.execute("hi", schema=_Schema)

    thread_opts = mock_sdk["client"].start_thread.call_args.args[0]
    assert thread_opts["sandboxMode"] == "workspace-write"
    assert thread_opts["skipGitRepoCheck"] is False


# ---------------------------------------------------------------------------
# execute() — error paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_empty_final_response_raises_structured_output_error(
    mock_sdk: dict[str, Any],
) -> None:
    mock_sdk["thread"].run = AsyncMock(return_value=_FakeTurn(final_response=""))
    rt = CodexRuntime()

    with pytest.raises(RuntimeStructuredOutputError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_non_json_final_response_raises_structured_output_error(
    mock_sdk: dict[str, Any],
) -> None:
    mock_sdk["thread"].run = AsyncMock(
        return_value=_FakeTurn(final_response="here's your answer: maybe 42")
    )
    rt = CodexRuntime()

    with pytest.raises(RuntimeStructuredOutputError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_thread_run_auth_failure(mock_sdk: dict[str, Any]) -> None:
    from openai_codex_sdk.errors import ThreadRunError

    mock_sdk["thread"].run = AsyncMock(
        side_effect=ThreadRunError("401 unauthorized: missing credentials")
    )
    rt = CodexRuntime()

    with pytest.raises(RuntimeAuthError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_thread_run_rate_limit(mock_sdk: dict[str, Any]) -> None:
    from openai_codex_sdk.errors import ThreadRunError

    mock_sdk["thread"].run = AsyncMock(side_effect=ThreadRunError("rate limit: 429"))
    rt = CodexRuntime()

    with pytest.raises(RuntimeTransientError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_thread_run_schema_failure(mock_sdk: dict[str, Any]) -> None:
    from openai_codex_sdk.errors import ThreadRunError

    mock_sdk["thread"].run = AsyncMock(
        side_effect=ThreadRunError("output schema violation: missing required field")
    )
    rt = CodexRuntime()

    with pytest.raises(RuntimeStructuredOutputError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_thread_run_generic_failure(mock_sdk: dict[str, Any]) -> None:
    from openai_codex_sdk.errors import ThreadRunError

    mock_sdk["thread"].run = AsyncMock(side_effect=ThreadRunError("upstream meltdown"))
    rt = CodexRuntime()

    with pytest.raises(AgentRuntimeError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_codex_auth_error(mock_sdk: dict[str, Any]) -> None:
    from openai_codex_sdk.errors import CodexAuthError

    mock_sdk["thread"].run = AsyncMock(side_effect=CodexAuthError("no auth.json found"))
    rt = CodexRuntime()

    with pytest.raises(RuntimeAuthError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_codex_install_error(mock_sdk: dict[str, Any]) -> None:
    from openai_codex_sdk.errors import CodexInstallError

    mock_sdk["thread"].run = AsyncMock(side_effect=CodexInstallError("install missing"))
    rt = CodexRuntime()

    with pytest.raises(RuntimeServerStartError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_codex_exec_error(mock_sdk: dict[str, Any]) -> None:
    from openai_codex_sdk.errors import CodexExecError

    mock_sdk["thread"].run = AsyncMock(side_effect=CodexExecError("subprocess died"))
    rt = CodexRuntime()

    with pytest.raises(RuntimeTransientError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_cli_not_found_raises_server_start_error(
    mock_sdk: dict[str, Any],
) -> None:
    mock_sdk["thread"].run = AsyncMock(side_effect=FileNotFoundError("no codex CLI"))
    rt = CodexRuntime()

    with pytest.raises(RuntimeServerStartError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_timeout_raises_transient_error(mock_sdk: dict[str, Any]) -> None:
    rt = CodexRuntime()

    async def slow(*args: Any, **kwargs: Any) -> Any:
        import asyncio

        await asyncio.sleep(10)

    mock_sdk["thread"].run = slow

    with pytest.raises(RuntimeTransientError):
        await rt.execute("hi", schema=_Schema, timeout=0.05)


@pytest.mark.asyncio
async def test_execute_event_parse_error(mock_sdk: dict[str, Any]) -> None:
    from openai_codex_sdk.errors import EventParseError

    mock_sdk["thread"].run = AsyncMock(side_effect=EventParseError("bad event line"))
    rt = CodexRuntime()

    with pytest.raises(RuntimeStructuredOutputError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_unknown_exception_classifies_as_agent_error(
    mock_sdk: dict[str, Any],
) -> None:
    mock_sdk["thread"].run = AsyncMock(side_effect=ValueError("totally unexpected"))
    rt = CodexRuntime()

    with pytest.raises(AgentRuntimeError):
        await rt.execute("hi", schema=_Schema)


# ---------------------------------------------------------------------------
# Cost path when usage is missing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cost_record_returns_zero_when_no_usage(mock_sdk: dict[str, Any]) -> None:
    mock_sdk["thread"].run = AsyncMock(return_value=_FakeTurn(usage=None))
    rt = CodexRuntime()

    result = await rt.execute("hi", schema=_Schema)

    assert result.cost.cost_usd is None
    assert result.cost.input_tokens == 0
    assert result.cost.output_tokens == 0
    assert result.cost.provider_id == "openai"


@pytest.mark.asyncio
async def test_cost_usd_none_for_unknown_model(mock_sdk: dict[str, Any]) -> None:
    rt = CodexRuntime(model="some-future-codex-variant")
    result = await rt.execute("hi", schema=_Schema)
    assert result.cost.cost_usd is None
    assert result.cost.input_tokens == 120


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_drops_thread(mock_sdk: dict[str, Any]) -> None:
    rt = CodexRuntime()
    await rt.execute("hi", schema=_Schema)
    assert rt._thread is not None

    await rt.reset()
    assert rt._thread is None
    assert rt._thread_key is None


@pytest.mark.asyncio
async def test_aclose_drops_thread_and_client(mock_sdk: dict[str, Any]) -> None:
    rt = CodexRuntime()
    await rt.execute("hi", schema=_Schema)

    await rt.aclose()
    assert rt._thread is None
    assert rt._client is None


@pytest.mark.asyncio
async def test_reset_with_no_thread_is_noop() -> None:
    rt = CodexRuntime()
    await rt.reset()
    await rt.aclose()


@pytest.mark.asyncio
async def test_thread_reused_when_model_matches(mock_sdk: dict[str, Any]) -> None:
    rt = CodexRuntime(model="gpt-5-codex")
    await rt.execute("hi", schema=_Schema)
    await rt.execute("hi again", schema=_Schema)

    # start_thread called once across both executes.
    assert mock_sdk["client"].start_thread.call_count == 1


@pytest.mark.asyncio
async def test_thread_recreated_when_model_changes(mock_sdk: dict[str, Any]) -> None:
    rt = CodexRuntime()
    await rt.execute("hi", schema=_Schema, model=ProviderModel("openai", "gpt-5-codex"))
    await rt.execute("hi", schema=_Schema, model=ProviderModel("openai", "o5-codex"))

    assert mock_sdk["client"].start_thread.call_count == 2


# ---------------------------------------------------------------------------
# Auth resolution
# ---------------------------------------------------------------------------


def test_resolve_api_key_uses_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    assert _resolve_api_key("explicit-key") == "explicit-key"


def test_resolve_api_key_uses_openai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai-key")
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    assert _resolve_api_key(None) == "env-openai-key"


def test_resolve_api_key_uses_codex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("CODEX_API_KEY", "env-codex-key")
    assert _resolve_api_key(None) == "env-codex-key"


def test_resolve_api_key_uses_opencode_auth_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    auth_file = tmp_path / "auth.json"
    auth_file.write_text(json.dumps({"openai": {"key": "opencode-stored-key"}}))
    monkeypatch.setenv("OPENCODE_AUTH_PATH", str(auth_file))

    assert _resolve_api_key(None) == "opencode-stored-key"


def test_resolve_api_key_returns_none_when_nothing_resolves(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.setenv("OPENCODE_AUTH_PATH", str(tmp_path / "nonexistent.json"))

    assert _resolve_api_key(None) is None


def test_resolve_api_key_ignores_malformed_auth_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    bad = tmp_path / "auth.json"
    bad.write_text("not valid json {")
    monkeypatch.setenv("OPENCODE_AUTH_PATH", str(bad))

    assert _resolve_api_key(None) is None


@pytest.mark.asyncio
async def test_explicit_api_key_threaded_to_codex_options(
    mock_sdk: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_API_KEY", raising=False)
    monkeypatch.setenv("OPENCODE_AUTH_PATH", "/nonexistent/path")
    rt = CodexRuntime(api_key="sk-test-key")

    await rt.execute("hi", schema=_Schema)

    assert mock_sdk["codex_options"].get("apiKey") == "sk-test-key"


@pytest.mark.asyncio
async def test_codex_path_override_threaded_to_codex_options(
    mock_sdk: dict[str, Any],
) -> None:
    rt = CodexRuntime(codex_path="/opt/custom/codex")
    await rt.execute("hi", schema=_Schema)

    assert mock_sdk["codex_options"].get("codexPathOverride") == "/opt/custom/codex"
