"""Landmine 1 mitigation: validate model IDs before sending."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from maverick.runtime.opencode.client import OpenCodeClient
from maverick.runtime.opencode.errors import OpenCodeModelNotFoundError
from maverick.runtime.opencode.validation import (
    invalidate_cache,
    list_connected_providers,
    validate_model_id,
)


@pytest.fixture(autouse=True)
def _clean_cache() -> None:
    invalidate_cache()


def _make_client(provider_response: dict[str, Any]) -> OpenCodeClient:
    """Build a client whose /provider call returns ``provider_response``."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/provider":
            return httpx.Response(200, json=provider_response)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = OpenCodeClient(base_url="http://test")
    client._http = httpx.AsyncClient(base_url="http://test", transport=transport)
    return client


async def test_validate_passes_when_model_listed() -> None:
    client = _make_client(
        {
            "providers": [
                {
                    "id": "openrouter",
                    "models": {
                        "anthropic/claude-haiku-4.5": {},
                        "openai/gpt-4o-mini": {},
                    },
                }
            ]
        }
    )
    try:
        await validate_model_id(client, "openrouter", "anthropic/claude-haiku-4.5")
    finally:
        await client.aclose()


async def test_validate_rejects_unknown_provider() -> None:
    client = _make_client({"providers": [{"id": "openrouter", "models": {"x": {}}}]})
    try:
        with pytest.raises(OpenCodeModelNotFoundError) as exc:
            await validate_model_id(client, "anthropic-direct", "x")
        assert "is not connected" in str(exc.value)
        assert "openrouter" in str(exc.value)
    finally:
        await client.aclose()


async def test_validate_rejects_unknown_model_under_known_provider() -> None:
    client = _make_client(
        {
            "providers": [
                {
                    "id": "openrouter",
                    "models": {"openai/gpt-4o-mini": {}, "anthropic/claude-haiku-4.5": {}},
                }
            ]
        }
    )
    try:
        with pytest.raises(OpenCodeModelNotFoundError) as exc:
            await validate_model_id(client, "openrouter", "anthropic/totally-fake")
        assert "totally-fake" in str(exc.value)
    finally:
        await client.aclose()


async def test_validate_handles_models_as_list() -> None:
    """Some endpoints return models as [{id: "..."}] instead of {id: {}}."""
    client = _make_client(
        {
            "providers": [
                {
                    "id": "openrouter",
                    "models": [
                        {"id": "openai/gpt-4o-mini"},
                        {"id": "qwen/qwen3-coder"},
                    ],
                }
            ]
        }
    )
    try:
        await validate_model_id(client, "openrouter", "qwen/qwen3-coder")
    finally:
        await client.aclose()


async def test_list_connected_providers_returns_snapshot() -> None:
    client = _make_client(
        {
            "providers": [
                {"id": "openrouter", "models": {"a": {}, "b": {}}},
                {"id": "anthropic-direct", "models": {"c": {}}},
            ]
        }
    )
    try:
        snap = await list_connected_providers(client)
        assert snap["openrouter"] == {"a", "b"}
        assert snap["anthropic-direct"] == {"c"}
    finally:
        await client.aclose()


async def test_validation_uses_cache_for_repeated_calls() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        if request.url.path == "/provider":
            call_count += 1
            return httpx.Response(
                200, json={"providers": [{"id": "openrouter", "models": {"x": {}}}]}
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = OpenCodeClient(base_url="http://cache-test")
    client._http = httpx.AsyncClient(base_url="http://cache-test", transport=transport)
    try:
        await validate_model_id(client, "openrouter", "x")
        await validate_model_id(client, "openrouter", "x")
        assert call_count == 1, "cache should prevent the second /provider call"
    finally:
        await client.aclose()


async def test_invalidate_cache_forces_fresh_fetch() -> None:
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        if request.url.path == "/provider":
            call_count += 1
            return httpx.Response(
                200, json={"providers": [{"id": "openrouter", "models": {"x": {}}}]}
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = OpenCodeClient(base_url="http://invalidate-test")
    client._http = httpx.AsyncClient(base_url="http://invalidate-test", transport=transport)
    try:
        await validate_model_id(client, "openrouter", "x")
        invalidate_cache(client.base_url)
        await validate_model_id(client, "openrouter", "x")
        assert call_count == 2
    finally:
        await client.aclose()
