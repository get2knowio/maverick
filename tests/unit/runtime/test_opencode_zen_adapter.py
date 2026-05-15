"""Unit tests for :class:`OpenCodeZenRuntime`.

Mocks the ``openai`` SDK at the boundary — no real Zen calls. Validates:

* Binding validation (opencode/opencode-go/opencode-zen accepted, others rejected).
* API-key resolution (constructor arg > env > auth.json > error).
* Structured output: raw JSON, schema-shaped JSON, envelope-wrapped JSON.
* Plain text (schema=None).
* Error classification (auth, rate-limit, 5xx, bad-request).
* Cost record from response.usage.
* Cost computation against the stub pricing map.
* aclose() closes the underlying client.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from maverick.runtime.cost import CostRecord
from maverick.runtime.errors import (
    AgentRuntimeError,
    RuntimeAuthError,
    RuntimeModelNotFoundError,
    RuntimeProtocolError,
    RuntimeStructuredOutputError,
    RuntimeTransientError,
)
from maverick.runtime.opencode_zen_adapter import (
    OpenCodeZenRuntime,
    _compute_cost_usd,
    _resolve_api_key,
    _unwrap_envelope,
)
from maverick.runtime.protocol import UnsupportedBindingError
from maverick.runtime.tiers import ProviderModel


class _Schema(BaseModel):
    summary: str
    count: int


def _make_response(
    *,
    content: str = '{"summary": "ok", "count": 42}',
    finish_reason: str = "stop",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    cached_tokens: int = 0,
) -> Any:
    """Build a stand-in for ``openai`` ChatCompletion."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = finish_reason
    usage = MagicMock()
    usage.prompt_tokens = prompt_tokens
    usage.completion_tokens = completion_tokens
    if cached_tokens:
        details = MagicMock()
        details.cached_tokens = cached_tokens
        usage.prompt_tokens_details = details
    else:
        usage.prompt_tokens_details = None
    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


@pytest.fixture
def mock_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Replace ``openai.AsyncOpenAI`` with a programmable mock."""
    import openai

    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_make_response())
    client.close = AsyncMock()

    factory = MagicMock(return_value=client)
    monkeypatch.setattr(openai, "AsyncOpenAI", factory)
    return client


# --- _resolve_api_key ---------------------------------------------------------


def test_resolve_api_key_explicit() -> None:
    assert _resolve_api_key("sk-explicit") == "sk-explicit"


def test_resolve_api_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENCODE_API_KEY", "sk-env-key")
    monkeypatch.setenv("OPENCODE_AUTH_PATH", "/nonexistent")
    assert _resolve_api_key(None) == "sk-env-key"


def test_resolve_api_key_from_auth_file(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"opencode-go": {"key": "sk-file-key"}}))
    monkeypatch.setenv("OPENCODE_AUTH_PATH", str(auth))
    assert _resolve_api_key(None) == "sk-file-key"


def test_resolve_api_key_missing_raises(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)
    monkeypatch.setenv("OPENCODE_AUTH_PATH", str(tmp_path / "absent.json"))
    with pytest.raises(RuntimeAuthError):
        _resolve_api_key(None)


# --- _unwrap_envelope ---------------------------------------------------------


def test_unwrap_envelope_unwraps_input_key() -> None:
    assert _unwrap_envelope({"input": {"a": 1}}) == {"a": 1}


def test_unwrap_envelope_decodes_string_content() -> None:
    assert _unwrap_envelope({"content": '{"a": 1}'}) == {"a": 1}


def test_unwrap_envelope_passes_through_bare_dict() -> None:
    assert _unwrap_envelope({"a": 1, "b": 2}) == {"a": 1, "b": 2}


def test_unwrap_envelope_passes_through_non_dict() -> None:
    assert _unwrap_envelope(42) == 42
    assert _unwrap_envelope("hello") == "hello"


# --- _compute_cost_usd --------------------------------------------------------


def test_compute_cost_usd_known_model() -> None:
    cost = _compute_cost_usd("gpt-5-nano", input_tokens=1000, output_tokens=500)
    assert cost is not None
    # 1.0 * 0.0001 + 0.5 * 0.0002 = 0.0002
    assert cost == pytest.approx(0.0002, rel=1e-3)


def test_compute_cost_usd_free_tier_is_zero() -> None:
    cost = _compute_cost_usd("minimax-m2.5-free", input_tokens=999, output_tokens=999)
    assert cost == 0.0


def test_compute_cost_usd_unknown_model_is_none() -> None:
    assert _compute_cost_usd("not-in-table", input_tokens=1, output_tokens=1) is None


# --- validate_binding ---------------------------------------------------------


def test_validate_binding_accepts_opencode_variants() -> None:
    rt = OpenCodeZenRuntime()
    assert rt.validate_binding(ProviderModel("opencode", "gpt-5-nano"))
    assert rt.validate_binding(ProviderModel("opencode-go", "qwen3.6-plus"))
    assert rt.validate_binding(ProviderModel("opencode-zen", "big-pickle"))


def test_validate_binding_rejects_others() -> None:
    rt = OpenCodeZenRuntime()
    assert not rt.validate_binding(ProviderModel("anthropic", "claude-haiku-4-5"))
    assert not rt.validate_binding(ProviderModel("github-copilot", "gpt-5.3-codex"))


@pytest.mark.asyncio
async def test_execute_rejects_unsupported_binding() -> None:
    rt = OpenCodeZenRuntime(api_key="sk-test")
    with pytest.raises(UnsupportedBindingError):
        await rt.execute(
            "hi",
            schema=_Schema,
            model=ProviderModel("anthropic", "claude-haiku-4-5"),
        )


# --- execute(): structured output ---------------------------------------------


@pytest.mark.asyncio
async def test_execute_returns_typed_payload(mock_client: MagicMock) -> None:
    rt = OpenCodeZenRuntime(api_key="sk-test")
    result = await rt.execute("hi", schema=_Schema)
    assert result.structured == {"summary": "ok", "count": 42}
    assert result.finish == "stop"
    assert result.cost.input_tokens == 100
    assert result.cost.output_tokens == 50
    assert result.cost.cache_read_tokens == 0
    assert result.cost.cache_write_tokens == 0
    assert result.cost.provider_id == "opencode"
    assert result.cost.model_id == "gpt-5-nano"
    # gpt-5-nano is in the pricing map: 0.1 * 0.0001 + 0.05 * 0.0002 = 0.00002
    assert result.cost.cost_usd == pytest.approx(0.00002, rel=1e-3)


@pytest.mark.asyncio
async def test_execute_passes_response_format_json_schema(
    mock_client: MagicMock,
) -> None:
    rt = OpenCodeZenRuntime(api_key="sk-test")
    await rt.execute("hi", schema=_Schema)
    call = mock_client.chat.completions.create.await_args
    rf = call.kwargs["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["name"] == "_Schema"
    assert rf["json_schema"]["strict"] is False
    assert "summary" in rf["json_schema"]["schema"]["properties"]


@pytest.mark.asyncio
async def test_execute_unwraps_envelope(mock_client: MagicMock) -> None:
    mock_client.chat.completions.create.return_value = _make_response(
        content='{"input": {"summary": "wrapped", "count": 7}}'
    )
    rt = OpenCodeZenRuntime(api_key="sk-test")
    result = await rt.execute("hi", schema=_Schema)
    assert result.structured == {"summary": "wrapped", "count": 7}


@pytest.mark.asyncio
async def test_execute_invalid_json_raises_structured_output_error(
    mock_client: MagicMock,
) -> None:
    mock_client.chat.completions.create.return_value = _make_response(content="this is not JSON")
    rt = OpenCodeZenRuntime(api_key="sk-test")
    with pytest.raises(RuntimeStructuredOutputError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_execute_with_no_choices_raises_protocol_error(
    mock_client: MagicMock,
) -> None:
    bad_response = MagicMock()
    bad_response.choices = []
    bad_response.usage = MagicMock(prompt_tokens=0, completion_tokens=0)
    bad_response.usage.prompt_tokens_details = None
    mock_client.chat.completions.create.return_value = bad_response
    rt = OpenCodeZenRuntime(api_key="sk-test")
    with pytest.raises(RuntimeProtocolError):
        await rt.execute("hi", schema=_Schema)


# --- execute(): plain text (no schema) ---------------------------------------


@pytest.mark.asyncio
async def test_execute_plain_text(mock_client: MagicMock) -> None:
    mock_client.chat.completions.create.return_value = _make_response(content="just text, no JSON")
    rt = OpenCodeZenRuntime(api_key="sk-test")
    result = await rt.execute("hi")
    assert result.structured is None
    assert result.text == "just text, no JSON"


@pytest.mark.asyncio
async def test_execute_plain_text_does_not_set_response_format(
    mock_client: MagicMock,
) -> None:
    rt = OpenCodeZenRuntime(api_key="sk-test")
    await rt.execute("hi")
    call = mock_client.chat.completions.create.await_args
    assert call.kwargs["response_format"] is None


# --- execute(): cost telemetry -----------------------------------------------


@pytest.mark.asyncio
async def test_cache_read_tokens_propagated(mock_client: MagicMock) -> None:
    mock_client.chat.completions.create.return_value = _make_response(
        prompt_tokens=1000, completion_tokens=200, cached_tokens=800
    )
    rt = OpenCodeZenRuntime(api_key="sk-test")
    result = await rt.execute("hi", schema=_Schema)
    assert result.cost.input_tokens == 1000
    assert result.cost.output_tokens == 200
    assert result.cost.cache_read_tokens == 800


# --- execute(): error classification ------------------------------------------


@pytest.mark.asyncio
async def test_auth_error_classified(mock_client: MagicMock) -> None:
    from openai import AuthenticationError

    # AuthenticationError needs (message, response=, body=)
    fake_resp = MagicMock()
    fake_resp.status_code = 401
    fake_resp.headers = {}
    mock_client.chat.completions.create.side_effect = AuthenticationError(
        message="bad key", response=fake_resp, body=None
    )
    rt = OpenCodeZenRuntime(api_key="sk-bad")
    with pytest.raises(RuntimeAuthError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_model_not_found_classified(mock_client: MagicMock) -> None:
    from openai import NotFoundError

    fake_resp = MagicMock()
    fake_resp.status_code = 404
    fake_resp.headers = {}
    mock_client.chat.completions.create.side_effect = NotFoundError(
        message="no such model", response=fake_resp, body=None
    )
    rt = OpenCodeZenRuntime(api_key="sk-test")
    with pytest.raises(RuntimeModelNotFoundError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_rate_limit_classified(mock_client: MagicMock) -> None:
    from openai import RateLimitError

    fake_resp = MagicMock()
    fake_resp.status_code = 429
    fake_resp.headers = {}
    mock_client.chat.completions.create.side_effect = RateLimitError(
        message="slow down", response=fake_resp, body=None
    )
    rt = OpenCodeZenRuntime(api_key="sk-test")
    with pytest.raises(RuntimeTransientError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_bad_request_classified_as_structured_output(
    mock_client: MagicMock,
) -> None:
    from openai import BadRequestError

    fake_resp = MagicMock()
    fake_resp.status_code = 400
    fake_resp.headers = {}
    mock_client.chat.completions.create.side_effect = BadRequestError(
        message="bad schema", response=fake_resp, body=None
    )
    rt = OpenCodeZenRuntime(api_key="sk-test")
    with pytest.raises(RuntimeStructuredOutputError):
        await rt.execute("hi", schema=_Schema)


@pytest.mark.asyncio
async def test_unknown_error_classified_as_runtime_error(
    mock_client: MagicMock,
) -> None:
    mock_client.chat.completions.create.side_effect = RuntimeError("surprise")
    rt = OpenCodeZenRuntime(api_key="sk-test")
    with pytest.raises(AgentRuntimeError):
        await rt.execute("hi", schema=_Schema)


# --- Lifecycle ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_is_noop() -> None:
    """Zen is stateless HTTP — reset doesn't need to do anything."""
    rt = OpenCodeZenRuntime(api_key="sk-test")
    await rt.reset()  # Should not raise.


@pytest.mark.asyncio
async def test_aclose_closes_client(mock_client: MagicMock) -> None:
    rt = OpenCodeZenRuntime(api_key="sk-test")
    await rt.execute("hi", schema=_Schema)
    assert rt._client is not None  # noqa: SLF001
    await rt.aclose()
    assert rt._client is None  # noqa: SLF001
    mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_aclose_without_client_is_noop() -> None:
    rt = OpenCodeZenRuntime(api_key="sk-test")
    await rt.aclose()  # Should not raise.


# --- Sanity check on CostRecord shape ----------------------------------------


@pytest.mark.asyncio
async def test_cost_record_fields_match_protocol(mock_client: MagicMock) -> None:
    rt = OpenCodeZenRuntime(api_key="sk-test")
    result = await rt.execute("hi", schema=_Schema)
    assert isinstance(result.cost, CostRecord)
    # All fields populated (cost_usd may be None for unknown models — gpt-5-nano is known).
    assert result.cost.provider_id is not None
    assert result.cost.model_id is not None
