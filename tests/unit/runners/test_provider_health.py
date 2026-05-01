"""Tests for the slimmed provider_health module.

The legacy ACP-spawn / MCP-gateway probes are gone (Phase 4 of the
OpenCode migration); the only check left is "binary on PATH + non-empty
command list". Phase 6 reconstitutes a real OpenCode probe.
"""

from __future__ import annotations

import pytest

from maverick.config import AgentProviderConfig
from maverick.runners.provider_health import (
    AcpProviderHealthCheck,
    build_provider_health_checks,
    providers_for_fly,
)

# ---------------------------------------------------------------------------
# AcpProviderHealthCheck stub
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_passes_when_binary_on_path(tmp_path) -> None:
    binary = tmp_path / "fake-bin"
    binary.write_text("")
    binary.chmod(0o755)

    check = AcpProviderHealthCheck(
        provider_name="claude",
        provider_config=AgentProviderConfig(command=[str(binary)]),
    )
    result = await check.validate()
    assert result.success is True
    assert result.component == "ACP:claude"


@pytest.mark.asyncio
async def test_health_check_fails_when_binary_missing() -> None:
    check = AcpProviderHealthCheck(
        provider_name="claude",
        provider_config=AgentProviderConfig(command=["/no/such/binary"]),
    )
    result = await check.validate()
    assert result.success is False
    assert any("not found on PATH" in msg for msg in result.errors)


@pytest.mark.asyncio
async def test_health_check_fails_when_command_empty() -> None:
    check = AcpProviderHealthCheck(
        provider_name="claude",
        provider_config=AgentProviderConfig(command=[]),
    )
    result = await check.validate()
    assert result.success is False
    assert any("empty command list" in msg for msg in result.errors)


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


class _ConfigStub:
    def __init__(
        self,
        agent_providers: dict[str, AgentProviderConfig] | None = None,
        actors: dict | None = None,
        agents: dict | None = None,
    ) -> None:
        self.agent_providers = _ProvidersStub(agent_providers or {})
        self.actors = actors or {}
        self.agents = agents or {}


def _provider(default: bool = False, command: list[str] | None = None) -> AgentProviderConfig:
    return AgentProviderConfig(
        command=command or ["/bin/true"],
        default=default,
    )


def test_build_returns_one_check_per_configured_provider() -> None:
    config = _ConfigStub(
        agent_providers={
            "claude": _provider(default=True),
            "copilot": _provider(),
        }
    )
    checks = build_provider_health_checks(config)
    assert {c.provider_name for c in checks} == {"claude", "copilot"}


def test_build_filters_to_provider_filter() -> None:
    config = _ConfigStub(
        agent_providers={
            "claude": _provider(default=True),
            "copilot": _provider(),
        }
    )
    checks = build_provider_health_checks(config, provider_filter={"copilot"})
    assert [c.provider_name for c in checks] == ["copilot"]


def test_build_ignores_test_mcp_tool_call_flag() -> None:
    """The legacy MCP probe flag is preserved on the dataclass for source
    compatibility, but ``build_provider_health_checks`` no longer threads
    it anywhere meaningful."""
    config = _ConfigStub(
        agent_providers={"claude": _provider(default=True)},
    )
    checks = build_provider_health_checks(config, test_mcp_tool_call=True)
    assert len(checks) == 1
    # Default value preserved.
    assert checks[0].test_mcp_tool_call is False


# ---------------------------------------------------------------------------
# providers_for_fly extraction
# ---------------------------------------------------------------------------


def test_providers_for_fly_includes_default_and_actor_overrides() -> None:
    config = _ConfigStub(
        agent_providers={
            "claude": _provider(default=True),
            "copilot": _provider(),
        },
        actors={
            "fly": {
                "implementer": {"provider": "copilot"},
                "reviewer": {"tiers": {"trivial": {"provider": "openrouter"}}},
            }
        },
    )
    seen = providers_for_fly(config)
    assert "claude" in seen
    assert "copilot" in seen
    assert "openrouter" in seen
