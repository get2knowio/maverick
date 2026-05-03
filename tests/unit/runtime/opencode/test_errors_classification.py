"""Error mapping from OpenCode session.error events and HTTP responses."""

from __future__ import annotations

import httpx
import pytest

from maverick.runtime.opencode.client import (
    _classify_http_error,
    classify_session_error,
)
from maverick.runtime.opencode.errors import (
    OpenCodeAuthError,
    OpenCodeContextOverflowError,
    OpenCodeError,
    OpenCodeModelNotFoundError,
    OpenCodeStructuredOutputError,
    OpenCodeTransientError,
)


def _resp(status: int, body: dict | None = None) -> httpx.Response:
    return httpx.Response(status, json=body or {})


# ---- session.error event classification ----------------------------------


def test_classify_provider_model_not_found() -> None:
    err = classify_session_error(
        {"name": "ProviderModelNotFoundError", "data": {"message": "no such model"}}
    )
    assert isinstance(err, OpenCodeModelNotFoundError)
    assert "no such model" in str(err)


def test_classify_provider_auth_error() -> None:
    err = classify_session_error({"name": "ProviderAuthError", "data": {"message": "bad key"}})
    assert isinstance(err, OpenCodeAuthError)


def test_classify_authentication_failure() -> None:
    err = classify_session_error({"name": "AuthenticationFailure", "data": {}})
    assert isinstance(err, OpenCodeAuthError)


def test_classify_context_overflow() -> None:
    err = classify_session_error({"name": "ContextOverflowError", "data": {"message": "too big"}})
    assert isinstance(err, OpenCodeContextOverflowError)


def test_classify_structured_output_error_carries_retries() -> None:
    err = classify_session_error(
        {"name": "StructuredOutputError", "data": {"message": "bad", "retries": 2}}
    )
    assert isinstance(err, OpenCodeStructuredOutputError)
    assert err.retries == 2


def test_classify_unknown_falls_back_to_base() -> None:
    err = classify_session_error({"name": "WhateverElse", "data": {}})
    assert isinstance(err, OpenCodeError)
    assert not isinstance(err, OpenCodeAuthError)
    assert not isinstance(err, OpenCodeModelNotFoundError)


def test_classify_ai_apicall_error_is_transient() -> None:
    """Vercel-AI-SDK's ``AI_APICallError`` (the wrapper opencode-go's
    Zen Go gateway uses for upstream provider failures) must classify
    as transient so the cascade falls over to the next binding instead
    of killing the whole call."""
    err = classify_session_error(
        {
            "name": "AI_APICallError",
            "data": {
                "type": "error",
                "error": {"type": "error", "message": "Internal server error"},
            },
        }
    )
    assert isinstance(err, OpenCodeTransientError)


def test_classify_internal_server_error_message_is_transient() -> None:
    """An unrecognized error name with an explicit ``Internal server error``
    message body still classifies as transient — same reasoning, cascade
    should fall over."""
    err = classify_session_error(
        {
            "name": "SomeUpstreamWrappingError",
            "data": {"message": "Internal server error"},
        }
    )
    assert isinstance(err, OpenCodeTransientError)


def test_classify_rate_limit_message_is_transient() -> None:
    err = classify_session_error(
        {
            "name": "WhateverError",
            "data": {"message": "Rate limit exceeded"},
        }
    )
    assert isinstance(err, OpenCodeTransientError)


def test_classify_unwraps_nested_error_message() -> None:
    """Some upstream errors bury the real message at
    ``data.error.message`` instead of ``data.message``. The classifier
    must look there too — without that, ``AI_APICallError`` events
    (whose message lives one level deeper) would skip the
    "internal server error" / "rate limit" matchers entirely."""
    err = classify_session_error(
        {
            "name": "GenericUpstream",
            "data": {
                "error": {"message": "Service unavailable"},
            },
        }
    )
    assert isinstance(err, OpenCodeTransientError)


def test_classify_unwraps_full_event_envelope() -> None:
    full_event = {
        "type": "session.error",
        "properties": {
            "error": {
                "name": "ProviderAuthError",
                "data": {"message": "401"},
            }
        },
    }
    err = classify_session_error(full_event)
    assert isinstance(err, OpenCodeAuthError)


def test_classify_handles_non_dict_input() -> None:
    err = classify_session_error("not a dict")
    assert isinstance(err, OpenCodeError)


# ---- HTTP response classification ----------------------------------------


def test_http_4xx_structured_output_with_retries() -> None:
    body = {"name": "StructuredOutputError", "data": {"message": "bad", "retries": 0}}
    err = _classify_http_error(_resp(400, body))
    assert isinstance(err, OpenCodeStructuredOutputError)
    assert err.status == 400
    assert err.retries == 0


def test_http_401_classifies_as_auth_error() -> None:
    err = _classify_http_error(_resp(401, {"name": "Unauthorized", "data": {}}))
    assert isinstance(err, OpenCodeAuthError)


def test_http_5xx_classifies_as_transient() -> None:
    err = _classify_http_error(_resp(503, {"name": "ServiceUnavailable", "data": {}}))
    assert isinstance(err, OpenCodeTransientError)


def test_http_429_classifies_as_transient() -> None:
    err = _classify_http_error(_resp(429, {"name": "RateLimit", "data": {}}))
    assert isinstance(err, OpenCodeTransientError)


def test_http_400_unknown_falls_back_to_base() -> None:
    err = _classify_http_error(_resp(400, {"name": "Whatever", "data": {}}))
    assert isinstance(err, OpenCodeError)
    assert not isinstance(err, OpenCodeTransientError)
    assert err.status == 400


@pytest.mark.parametrize(
    "name,expected",
    [
        ("ProviderModelNotFoundError", OpenCodeModelNotFoundError),
        ("ProviderAuthError", OpenCodeAuthError),
    ],
)
def test_http_4xx_provider_errors_classify(name: str, expected: type) -> None:
    err = _classify_http_error(_resp(400, {"name": name, "data": {}}))
    assert isinstance(err, expected)
