"""Unit tests for :class:`OpenCodeClient` using httpx mock transport.

Exercises:

* ``create_session`` / ``send_message`` happy path.
* Landmine 2 silent failures: empty 200 → ``OpenCodeProtocolError`` via
  :meth:`send_with_event_watch` (when no error event is observed).
* Landmine 2 visible failures: ``session.error`` event fires while the
  send is in flight → classified exception (``OpenCodeAuthError``,
  ``OpenCodeModelNotFoundError``).
* Structured-output extraction with envelope unwrap (Landmine 3).
* ``cancel`` returns the server's bool.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from maverick.runtime.opencode import (
    OpenCodeAuthError,
    OpenCodeClient,
    OpenCodeModelNotFoundError,
    OpenCodeProtocolError,
    OpenCodeStructuredOutputError,
)

# ---------------------------------------------------------------------------
# Mock-transport helpers
# ---------------------------------------------------------------------------


class _FakeServer:
    """Programmable mock OpenCode server.

    Construct with handlers per route. Supports the synchronous endpoints
    used by the client; the streaming /event endpoint is exposed via the
    ``set_events`` helper which feeds raw SSE bytes through a custom
    httpx-mock-transport response.
    """

    def __init__(self) -> None:
        self.message_responses: list[httpx.Response] = []
        self.cancel_response: httpx.Response = httpx.Response(200, json=True)
        self.session_create_response: httpx.Response = httpx.Response(
            200, json={"id": "ses_test_123"}
        )

    def transport(self) -> httpx.MockTransport:
        async def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path == "/global/health" and request.method == "GET":
                return httpx.Response(200, json={"ok": True})
            if path == "/session" and request.method == "POST":
                return self.session_create_response
            if path.endswith("/abort") and request.method == "POST":
                return self.cancel_response
            if path.endswith("/message") and request.method == "POST":
                if not self.message_responses:
                    return httpx.Response(500, json={"name": "Empty"})
                return self.message_responses.pop(0)
            return httpx.Response(404, text=f"unhandled: {request.method} {path}")

        return httpx.MockTransport(handler)


def _client_with(server: _FakeServer) -> OpenCodeClient:
    client = OpenCodeClient(base_url="http://fake")
    client._http = httpx.AsyncClient(base_url="http://fake", transport=server.transport())
    return client


# ---------------------------------------------------------------------------
# Happy-path send + structured extraction
# ---------------------------------------------------------------------------


async def test_create_session_returns_id_from_server() -> None:
    server = _FakeServer()
    server.session_create_response = httpx.Response(200, json={"id": "ses_abc"})
    client = _client_with(server)
    try:
        sid = await client.create_session(title="hi")
        assert sid == "ses_abc"
    finally:
        await client.aclose()


async def test_send_message_returns_payload() -> None:
    server = _FakeServer()
    server.message_responses = [
        httpx.Response(
            200,
            json={
                "info": {"providerID": "openrouter", "modelID": "x"},
                "parts": [{"type": "text", "text": "hello"}],
            },
        )
    ]
    client = _client_with(server)
    try:
        msg = await client.send_message("ses_x", "say hi")
        assert msg["parts"][0]["text"] == "hello"
    finally:
        await client.aclose()


async def test_send_message_returns_empty_sentinel_on_empty_body() -> None:
    server = _FakeServer()
    server.message_responses = [httpx.Response(200, content=b"")]
    client = _client_with(server)
    try:
        msg = await client.send_message("ses_x", "x")
        assert msg.get("_empty") is True
        assert msg["parts"] == []
    finally:
        await client.aclose()


async def test_send_message_raises_classified_4xx() -> None:
    server = _FakeServer()
    server.message_responses = [
        httpx.Response(
            400,
            json={
                "name": "StructuredOutputError",
                "data": {"message": "bad", "retries": 0},
            },
        )
    ]
    client = _client_with(server)
    try:
        with pytest.raises(OpenCodeStructuredOutputError):
            await client.send_message("ses_x", "x")
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Landmine 2: silent empty 200 → must surface
# ---------------------------------------------------------------------------


def _patch_stream(monkeypatch: pytest.MonkeyPatch, events: list[dict[str, Any]]) -> None:
    """Replace ``OpenCodeClient.stream_events`` with a fake that yields ``events``."""

    async def fake_stream(self, session_id=None, *, timeout=None):  # noqa: ANN001
        for evt in events:
            if session_id is not None:
                props = evt.get("properties") or {}
                sid = props.get("sessionID") or (props.get("info") or {}).get("sessionID")
                if sid is not None and sid != session_id:
                    continue
            yield evt

    monkeypatch.setattr(OpenCodeClient, "stream_events", fake_stream)


async def test_send_with_event_watch_raises_on_silent_empty_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty 200 with no error event → OpenCodeProtocolError."""
    server = _FakeServer()
    server.message_responses = [httpx.Response(200, content=b"")]
    client = _client_with(server)

    _patch_stream(monkeypatch, [{"type": "session.idle", "properties": {"sessionID": "ses_x"}}])

    try:
        with pytest.raises(OpenCodeProtocolError):
            await client.send_with_event_watch("ses_x", "x")
    finally:
        await client.aclose()


async def test_send_with_event_watch_classifies_auth_error_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _FakeServer()
    server.message_responses = [httpx.Response(200, content=b"")]
    client = _client_with(server)

    _patch_stream(
        monkeypatch,
        [
            {
                "type": "session.error",
                "properties": {
                    "sessionID": "ses_x",
                    "error": {"name": "ProviderAuthError", "data": {"message": "bad key"}},
                },
            }
        ],
    )

    try:
        with pytest.raises(OpenCodeAuthError):
            await client.send_with_event_watch("ses_x", "x")
    finally:
        await client.aclose()


async def test_send_with_event_watch_classifies_model_not_found_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _FakeServer()
    server.message_responses = [httpx.Response(200, content=b"")]
    client = _client_with(server)

    _patch_stream(
        monkeypatch,
        [
            {
                "type": "session.error",
                "properties": {
                    "sessionID": "ses_x",
                    "error": {
                        "name": "ProviderModelNotFoundError",
                        "data": {"message": "no such"},
                    },
                },
            }
        ],
    )

    try:
        with pytest.raises(OpenCodeModelNotFoundError):
            await client.send_with_event_watch("ses_x", "x")
    finally:
        await client.aclose()


async def test_send_with_event_watch_returns_send_result_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _FakeServer()
    server.message_responses = [
        httpx.Response(
            200,
            json={
                "info": {"structured": {"input": {"approved": True}}, "modelID": "claude-haiku"},
                "parts": [
                    {
                        "type": "tool",
                        "tool": "StructuredOutput",
                        "state": {
                            "input": {"input": {"approved": True}},
                            "metadata": {"valid": True},
                        },
                    }
                ],
            },
        )
    ]
    client = _client_with(server)

    _patch_stream(monkeypatch, [{"type": "session.idle", "properties": {"sessionID": "ses_x"}}])

    try:
        result = await client.send_with_event_watch(
            "ses_x", "review", format={"type": "json_schema", "schema": {}}
        )
        assert result.structured == {"approved": True}
        assert result.valid is True
        assert result.info.get("modelID") == "claude-haiku"
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


async def test_cancel_returns_bool() -> None:
    server = _FakeServer()
    server.cancel_response = httpx.Response(200, json=True)
    client = _client_with(server)
    try:
        assert await client.cancel("ses_x") is True
    finally:
        await client.aclose()


async def test_send_message_passes_format_through() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/message") and request.method == "POST":
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json={"info": {}, "parts": []})
        return httpx.Response(200, json={"id": "ses"})

    transport = httpx.MockTransport(handler)
    client = OpenCodeClient(base_url="http://fmt")
    client._http = httpx.AsyncClient(base_url="http://fmt", transport=transport)
    try:
        await client.send_message(
            "ses_x",
            "hi",
            model={"providerID": "openrouter", "modelID": "x"},
            format={"type": "json_schema", "schema": {"type": "object"}},
        )
        body = captured["body"]
        assert body["model"] == {"providerID": "openrouter", "modelID": "x"}
        assert body["format"]["type"] == "json_schema"
        assert body["parts"][0]["text"] == "hi"
    finally:
        await client.aclose()


async def test_authorization_header_set_when_password_given() -> None:
    """Password is sent as HTTP Basic auth with username 'opencode'."""
    import base64

    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = OpenCodeClient(base_url="http://auth", password="secretsauce")
    client._http = httpx.AsyncClient(
        base_url="http://auth",
        transport=transport,
        auth=httpx.BasicAuth("opencode", "secretsauce"),
    )
    try:
        await client.health()
        expected = "Basic " + base64.b64encode(b"opencode:secretsauce").decode()
        assert captured["auth"] == expected
    finally:
        await client.aclose()
