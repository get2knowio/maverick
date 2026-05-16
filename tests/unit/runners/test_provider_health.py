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

from maverick.config import AgentBindingConfig, AgentsConfig
from maverick.runners.provider_health import (
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
    """Patch :func:`airframe.runtime_for` to return a controllable stub."""
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
    _patch_airframe(monkeypatch, model_ids=["claude-haiku-4-5", "claude-sonnet-4-6"])
    check = ProviderHealthCheck(
        provider_name="claude",
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
    check = ProviderHealthCheck(provider_name="claude")
    result = await check.validate()
    assert result.success is False
    assert any("not installed" in m for m in result.errors)


@pytest.mark.asyncio
async def test_validate_fails_when_model_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_airframe(monkeypatch, model_ids=["claude-haiku-4-5"])
    check = ProviderHealthCheck(
        provider_name="claude",
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
    check = ProviderHealthCheck(provider_name="claude")
    result = await check.validate()
    assert result.success is True


@pytest.mark.asyncio
async def test_validate_surfaces_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """A vendor/auth failure surfaces in the result."""
    _patch_airframe(monkeypatch, raise_on_list=RuntimeAuthError("no credentials"))
    check = ProviderHealthCheck(provider_name="claude")
    result = await check.validate()
    assert result.success is False
    assert any("no credentials" in m for m in result.errors)


@pytest.mark.asyncio
async def test_validate_surfaces_generic_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_airframe(monkeypatch, raise_on_list=AgentRuntimeError("HTTP 502"))
    check = ProviderHealthCheck(provider_name="claude")
    result = await check.validate()
    assert result.success is False
    assert any("HTTP 502" in m for m in result.errors)


# ---------------------------------------------------------------------------
# Builder — reads providers from ``config.agents``
# ---------------------------------------------------------------------------


class _ConfigStub:
    def __init__(
        self,
        agents: AgentsConfig | None = None,
        actors: dict | None = None,
    ) -> None:
        self.agents = agents or AgentsConfig()
        self.actors = actors or {}


def _agents(**bindings: AgentBindingConfig) -> AgentsConfig:
    return AgentsConfig(**bindings)


def _binding(provider: str, model_id: str) -> AgentBindingConfig:
    return AgentBindingConfig(provider=provider, model_id=model_id)


def test_build_returns_one_check_per_unique_provider() -> None:
    """Two roles on the same provider collapse into one check."""
    config = _ConfigStub(
        agents=_agents(
            implement=_binding("claude", "claude-sonnet-4-6"),
            review=_binding("claude", "claude-haiku-4-5"),
            briefing=_binding("github-copilot", "gpt-5-mini"),
        ),
    )
    checks = build_provider_health_checks(config)
    assert {c.provider_name for c in checks} == {"claude", "github-copilot"}


def test_build_aggregates_model_ids_per_provider() -> None:
    """Each provider's ``models_to_validate`` is the union of its roles' model ids."""
    config = _ConfigStub(
        agents=_agents(
            implement=_binding("claude", "claude-sonnet-4-6"),
            review=_binding("claude", "claude-haiku-4-5"),
        ),
    )
    checks = build_provider_health_checks(config)
    by_name = {c.provider_name: c for c in checks}
    assert by_name["claude"].models_to_validate == frozenset(
        {"claude-sonnet-4-6", "claude-haiku-4-5"}
    )


def test_build_filters_to_provider_filter() -> None:
    config = _ConfigStub(
        agents=_agents(
            implement=_binding("claude", "claude-sonnet-4-6"),
            briefing=_binding("github-copilot", "gpt-5-mini"),
        ),
    )
    checks = build_provider_health_checks(config, provider_filter={"claude"})
    assert [c.provider_name for c in checks] == ["claude"]


def test_build_returns_empty_when_no_roles_bound() -> None:
    config = _ConfigStub()
    assert build_provider_health_checks(config) == []


# ---------------------------------------------------------------------------
# providers_for_fly extraction
# ---------------------------------------------------------------------------


def test_providers_for_fly_unions_agents_and_actor_overrides() -> None:
    config = _ConfigStub(
        agents=_agents(implement=_binding("claude", "claude-sonnet-4-6")),
        actors={
            "fly": {
                "implementer": {"provider": "github-copilot"},
                "reviewer": {"tiers": {"trivial": {"provider": "codex"}}},
            }
        },
    )
    seen = providers_for_fly(config)
    assert seen == {"claude", "github-copilot", "codex"}


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
            models_to_validate=frozenset({"m-1"}),
        )
        for name in ("claude", "github-copilot")
    ]
    results = await run_provider_health_checks(checks)
    assert len(results) == 2
    assert all(r.success for r in results)
