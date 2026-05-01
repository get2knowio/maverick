"""Tests for OpenCode-backed provider health checks.

The probe spawns an ``opencode serve`` subprocess in production; for
unit tests we inject a fake :class:`OpenCodeServerHandle` and patch
:func:`list_connected_providers` so the check runs synchronously
without touching the network.
"""

from __future__ import annotations

from typing import Any

import pytest

from maverick.config import AgentProviderConfig
from maverick.runners.provider_health import (
    AcpProviderHealthCheck,
    OpenCodeProviderHealthCheck,
    build_provider_health_checks,
    providers_for_fly,
    run_provider_health_checks,
)

# ---------------------------------------------------------------------------
# Fake handle (no actual subprocess)
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


def _fake_handle():
    from maverick.runtime.opencode import OpenCodeServerHandle

    return OpenCodeServerHandle(
        base_url="http://fake-opencode",
        password="fake",
        pid=0,
        _process=_FakeProcess(),  # type: ignore[arg-type]
    )


def _patch_providers(monkeypatch: pytest.MonkeyPatch, mapping: dict[str, set[str]]) -> None:
    """Patch ``list_connected_providers`` at the module-import site.

    The provider_health module imports the symbol locally, so we monkey-
    patch THAT binding (not the runtime module's binding).
    """

    async def fake(client: Any) -> dict[str, set[str]]:
        return {k: set(v) for k, v in mapping.items()}

    monkeypatch.setattr("maverick.runners.provider_health.list_connected_providers", fake)


# ---------------------------------------------------------------------------
# OpenCodeProviderHealthCheck.validate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_validate_passes_when_provider_connected_and_models_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_providers(
        monkeypatch,
        {"openrouter": {"anthropic/claude-haiku-4.5", "openai/gpt-4o-mini"}},
    )
    check = OpenCodeProviderHealthCheck(
        provider_name="openrouter",
        provider_config=AgentProviderConfig(),
        models_to_validate=frozenset({"anthropic/claude-haiku-4.5"}),
    )
    result = await check.validate(handle=_fake_handle())
    assert result.success is True
    assert result.component == "OpenCode:openrouter"


@pytest.mark.asyncio
async def test_validate_fails_when_provider_not_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_providers(monkeypatch, {"openrouter": {"x"}})
    check = OpenCodeProviderHealthCheck(
        provider_name="anthropic-direct",
        provider_config=AgentProviderConfig(),
    )
    result = await check.validate(handle=_fake_handle())
    assert result.success is False
    assert any("not connected" in m for m in result.errors)
    assert any("openrouter" in m for m in result.errors)


@pytest.mark.asyncio
async def test_validate_fails_when_model_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_providers(monkeypatch, {"openrouter": {"openai/gpt-4o-mini"}})
    check = OpenCodeProviderHealthCheck(
        provider_name="openrouter",
        provider_config=AgentProviderConfig(),
        models_to_validate=frozenset({"anthropic/claude-haiku-4.5"}),
    )
    result = await check.validate(handle=_fake_handle())
    assert result.success is False
    assert any("not available" in m for m in result.errors)


@pytest.mark.asyncio
async def test_validate_passes_with_no_models_when_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_providers(monkeypatch, {"openrouter": set()})
    check = OpenCodeProviderHealthCheck(
        provider_name="openrouter",
        provider_config=AgentProviderConfig(),
    )
    result = await check.validate(handle=_fake_handle())
    assert result.success is True


@pytest.mark.asyncio
async def test_validate_surfaces_handle_query_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the /provider query raises, surface it in the result."""

    async def boom(client: Any) -> dict[str, set[str]]:
        from maverick.runtime.opencode import OpenCodeError

        raise OpenCodeError("HTTP 502")

    monkeypatch.setattr("maverick.runners.provider_health.list_connected_providers", boom)
    check = OpenCodeProviderHealthCheck(
        provider_name="openrouter",
        provider_config=AgentProviderConfig(),
    )
    result = await check.validate(handle=_fake_handle())
    assert result.success is False
    assert any("HTTP 502" in m for m in result.errors)


def test_acp_alias_is_opencode_check() -> None:
    """Source-compat alias for the renamed class."""
    assert AcpProviderHealthCheck is OpenCodeProviderHealthCheck


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


class _AgentCfg:
    def __init__(self, model_id: str | None = None) -> None:
        self.model_id = model_id


class _ConfigStub:
    def __init__(
        self,
        agent_providers: dict[str, AgentProviderConfig] | None = None,
        actors: dict | None = None,
        agents: dict | None = None,
        model: _ModelStub | None = None,
    ) -> None:
        self.agent_providers = _ProvidersStub(agent_providers or {})
        self.actors = actors or {}
        self.agents = agents or {}
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


def test_build_includes_global_and_per_agent_models_for_default_provider() -> None:
    """Global ``model.model_id`` and per-agent overrides only apply to the
    default provider — a global Claude alias means nothing for openrouter."""
    config = _ConfigStub(
        agent_providers={
            "openrouter": _provider(default=True, default_model="x"),
            "anthropic-direct": _provider(),
        },
        agents={"reviewer": _AgentCfg(model_id="anthropic/claude-haiku-4.5")},
        model=_ModelStub(model_id="qwen/qwen3-coder", fields_set={"model_id"}),
    )
    checks = build_provider_health_checks(config)
    by_name = {c.provider_name: c for c in checks}
    assert by_name["openrouter"].models_to_validate == frozenset(
        {"x", "qwen/qwen3-coder", "anthropic/claude-haiku-4.5"}
    )
    # Non-default provider doesn't pick up the global / per-agent set.
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
