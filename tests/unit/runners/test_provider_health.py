"""Tests for airframe-backed provider health checks.

The probe instantiates an :class:`airframe.AgentRuntime` and calls
``list_models``; tests patch :func:`airframe.runtime_for` with a fake
adapter class so the check runs synchronously without touching the
network.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from airframe.errors import AgentRuntimeError, RuntimeAuthError

from maverick.config import AgentProviderConfig
from maverick.runners.provider_health import (
    AcpProviderHealthCheck,
    OpenCodeProviderHealthCheck,
    ProviderHealthCheck,
    build_provider_health_checks,
    providers_for_fly,
    run_provider_health_checks,
)

# ---------------------------------------------------------------------------
# Fake airframe runtime
# ---------------------------------------------------------------------------


def _model(model_id: str) -> Any:
    info = MagicMock()
    info.id = model_id
    return info


def _patch_airframe(
    monkeypatch: pytest.MonkeyPatch,
    *,
    model_ids: list[str] | None = None,
    raise_on_list: BaseException | None = None,
    runtime_for_error: BaseException | None = None,
) -> MagicMock:
    """Patch :func:`airframe.runtime_for` to return a controllable stub.

    The provider_health module imports ``airframe`` at module-load and
    refers to it by attribute, so we patch ``airframe.runtime_for``
    directly.
    """
    runtime = MagicMock()
    runtime.label = "stub"
    if raise_on_list is not None:
        runtime.list_models = AsyncMock(side_effect=raise_on_list)
    else:
        runtime.list_models = AsyncMock(return_value=[_model(m) for m in (model_ids or [])])
    runtime.close = AsyncMock()

    def fake_runtime_for(_pid: str) -> type[Any]:
        if runtime_for_error is not None:
            raise runtime_for_error
        return lambda: runtime

    monkeypatch.setattr("airframe.runtime_for", fake_runtime_for)
    return runtime


# ---------------------------------------------------------------------------
# ProviderHealthCheck.validate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_passes_when_models_match(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_airframe(
        monkeypatch,
        model_ids=["claude-haiku-4-5", "claude-sonnet-4-6"],
    )
    check = ProviderHealthCheck(
        provider_name="claude",
        provider_config=AgentProviderConfig(),
        models_to_validate=frozenset({"claude-haiku-4-5"}),
    )
    result = await check.validate()
    assert result.success is True
    assert result.component == "airframe:claude"


@pytest.mark.asyncio
async def test_validate_fails_when_adapter_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_airframe(
        monkeypatch,
        runtime_for_error=ImportError("install airframe-agents[claude]"),
    )
    check = ProviderHealthCheck(
        provider_name="claude",
        provider_config=AgentProviderConfig(),
    )
    result = await check.validate()
    assert result.success is False
    assert any("not installed" in m for m in result.errors)


@pytest.mark.asyncio
async def test_validate_fails_when_model_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_airframe(monkeypatch, model_ids=["claude-haiku-4-5"])
    check = ProviderHealthCheck(
        provider_name="claude",
        provider_config=AgentProviderConfig(),
        models_to_validate=frozenset({"claude-opus-4-5"}),
    )
    result = await check.validate()
    assert result.success is False
    assert any("not available" in m for m in result.errors)


@pytest.mark.asyncio
async def test_validate_passes_with_no_models_when_listable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_airframe(monkeypatch, model_ids=[])
    check = ProviderHealthCheck(
        provider_name="claude",
        provider_config=AgentProviderConfig(),
    )
    result = await check.validate()
    assert result.success is True


@pytest.mark.asyncio
async def test_validate_surfaces_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A vendor/auth failure surfaces in the result."""
    _patch_airframe(monkeypatch, raise_on_list=RuntimeAuthError("no credentials"))
    check = ProviderHealthCheck(
        provider_name="claude",
        provider_config=AgentProviderConfig(),
    )
    result = await check.validate()
    assert result.success is False
    assert any("no credentials" in m for m in result.errors)


@pytest.mark.asyncio
async def test_validate_surfaces_generic_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_airframe(monkeypatch, raise_on_list=AgentRuntimeError("HTTP 502"))
    check = ProviderHealthCheck(
        provider_name="claude",
        provider_config=AgentProviderConfig(),
    )
    result = await check.validate()
    assert result.success is False
    assert any("HTTP 502" in m for m in result.errors)


def test_opencode_alias_is_provider_health_check() -> None:
    """Source-compat aliases for the renamed class."""
    assert OpenCodeProviderHealthCheck is ProviderHealthCheck
    assert AcpProviderHealthCheck is ProviderHealthCheck


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


class _ProvidersStub:
    def __init__(self, mapping: dict[str, AgentProviderConfig]) -> None:
        self._mapping = mapping

    def items(self) -> list[tuple[str, AgentProviderConfig]]:
        return list(self._mapping.items())

    def __iter__(self):
        return iter(self._mapping)

    def __bool__(self) -> bool:
        return bool(self._mapping)

    def get(self, key: str, default=None):
        return self._mapping.get(key, default)

    def values(self):
        return self._mapping.values()


class _ModelStub:
    def __init__(self, model_id: str | None = None, fields_set: set[str] | None = None) -> None:
        self.model_id = model_id
        self.model_fields_set = fields_set or set()


class _ConfigStub:
    def __init__(
        self,
        agent_providers: dict[str, AgentProviderConfig] | None = None,
        actors: dict | None = None,
        model: _ModelStub | None = None,
    ) -> None:
        self.agent_providers = _ProvidersStub(agent_providers or {})
        self.actors = actors or {}
        self.model = model or _ModelStub()


def _provider(default: bool = False, default_model: str | None = None) -> AgentProviderConfig:
    return AgentProviderConfig(
        command=["/bin/true"],
        default=default,
        default_model=default_model,
    )


def test_build_returns_one_check_per_configured_provider() -> None:
    config = _ConfigStub(
        agent_providers={
            "openrouter": _provider(default=True),
            "anthropic-direct": _provider(),
        }
    )
    checks = build_provider_health_checks(config)
    assert {c.provider_name for c in checks} == {"openrouter", "anthropic-direct"}


def test_build_filters_to_provider_filter() -> None:
    config = _ConfigStub(
        agent_providers={
            "openrouter": _provider(default=True),
            "anthropic-direct": _provider(),
        }
    )
    checks = build_provider_health_checks(config, provider_filter={"openrouter"})
    assert [c.provider_name for c in checks] == ["openrouter"]


def test_build_includes_provider_default_model() -> None:
    config = _ConfigStub(
        agent_providers={
            "openrouter": _provider(default=True, default_model="openai/gpt-4o-mini"),
        }
    )
    checks = build_provider_health_checks(config)
    assert checks[0].models_to_validate == frozenset({"openai/gpt-4o-mini"})


def test_build_includes_global_model_for_default_provider() -> None:
    """Global ``model.model_id`` applies to the default provider only —
    a global Claude alias means nothing for openrouter."""
    config = _ConfigStub(
        agent_providers={
            "openrouter": _provider(default=True, default_model="x"),
            "anthropic-direct": _provider(),
        },
        model=_ModelStub(model_id="qwen/qwen3-coder", fields_set={"model_id"}),
    )
    checks = build_provider_health_checks(config)
    by_name = {c.provider_name: c for c in checks}
    assert by_name["openrouter"].models_to_validate == frozenset({"x", "qwen/qwen3-coder"})
    # Non-default provider doesn't pick up the global set.
    assert by_name["anthropic-direct"].models_to_validate == frozenset()


def test_build_ignores_test_mcp_tool_call_flag() -> None:
    """Legacy doctor flag — preserved on the dataclass, no-op here."""
    config = _ConfigStub(agent_providers={"openrouter": _provider(default=True)})
    checks = build_provider_health_checks(config, test_mcp_tool_call=True)
    assert len(checks) == 1
    assert checks[0].test_mcp_tool_call is False


# ---------------------------------------------------------------------------
# providers_for_fly extraction
# ---------------------------------------------------------------------------


def test_providers_for_fly_includes_default_and_actor_overrides() -> None:
    config = _ConfigStub(
        agent_providers={
            "openrouter": _provider(default=True),
            "anthropic-direct": _provider(),
        },
        actors={
            "fly": {
                "implementer": {"provider": "anthropic-direct"},
                "reviewer": {"tiers": {"trivial": {"provider": "openrouter"}}},
            }
        },
    )
    seen = providers_for_fly(config)
    assert seen == {"openrouter", "anthropic-direct"}


# ---------------------------------------------------------------------------
# run_provider_health_checks (multi-check helper)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_provider_health_checks_empty_returns_empty() -> None:
    assert await run_provider_health_checks([]) == []


@pytest.mark.asyncio
async def test_run_provider_health_checks_runs_each(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_airframe(monkeypatch, model_ids=["m-1"])
    checks = [
        ProviderHealthCheck(
            provider_name=name,
            provider_config=AgentProviderConfig(),
            models_to_validate=frozenset({"m-1"}),
        )
        for name in ("claude", "github-copilot")
    ]
    results = await run_provider_health_checks(checks)
    assert len(results) == 2
    assert all(r.success for r in results)
