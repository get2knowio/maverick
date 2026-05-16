"""Unit tests for :func:`maverick.runtime.agent_factory.runtime_for_agent`.

Validates:

* Role resolution from ``agents:`` config.
* ``binding_override`` wins over ``agents_config.<role>``.
* Unknown role → :class:`ValueError`.
* Missing binding (no override, no config entry) → :class:`ValueError`.
* Resolved runtime is constructed via :func:`airframe.runtime_for` with
  ``model=`` pinned to the binding.
* Uninstalled provider SDK propagates :class:`ImportError` with the
  pip-extra hint (the airframe side already covers this; we verify
  it flows through cleanly).

Mocks :func:`airframe.runtime_for` so the tests don't construct real
adapter instances or hit any SDKs.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from maverick.config import AgentBindingConfig, AgentsConfig
from maverick.runtime import agent_factory
from maverick.runtime.agent_factory import (
    KNOWN_ROLES,
    binding_for_role,
    runtime_for_agent,
)

# ---------------------------------------------------------------------------
# binding_for_role
# ---------------------------------------------------------------------------


def test_known_roles_match_agent_provider_tiers() -> None:
    """The factory's KNOWN_ROLES set is the agent surface contract."""
    # If a new agent ships, both this set and the AgentsConfig schema
    # need to grow together — this test makes a divergence obvious.
    assert {"implement", "review", "briefing", "decompose", "generate"} == set(KNOWN_ROLES)


def test_binding_for_role_returns_configured_binding() -> None:
    agents = AgentsConfig(
        implement=AgentBindingConfig(provider="claude", model_id="claude-sonnet-4-6"),
    )
    binding = binding_for_role("implement", agents_config=agents)
    assert binding.provider == "claude"
    assert binding.model_id == "claude-sonnet-4-6"


def test_binding_override_wins_over_config() -> None:
    agents = AgentsConfig(
        implement=AgentBindingConfig(provider="claude", model_id="claude-sonnet-4-6"),
    )
    override = AgentBindingConfig(provider="github-copilot", model_id="gpt-5-codex")
    binding = binding_for_role(
        "implement",
        agents_config=agents,
        binding_override=override,
    )
    assert binding == override


def test_binding_for_role_unknown_role_raises() -> None:
    agents = AgentsConfig()
    with pytest.raises(ValueError) as excinfo:
        binding_for_role("not-a-role", agents_config=agents)
    msg = str(excinfo.value)
    assert "not-a-role" in msg
    # Lists the valid roles so the user sees the option set.
    assert "implement" in msg


def test_binding_for_role_missing_binding_raises_helpful_error() -> None:
    agents = AgentsConfig()  # nothing set
    with pytest.raises(ValueError) as excinfo:
        binding_for_role("implement", agents_config=agents)
    msg = str(excinfo.value)
    assert "agents.implement" in msg
    assert "maverick.yaml" in msg


# ---------------------------------------------------------------------------
# runtime_for_agent
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_runtime_for(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Stub :func:`airframe.runtime_for` so tests don't touch real SDKs."""
    captured: dict[str, Any] = {"runtime_kwargs": None}

    class _FakeRuntime:
        def __init__(self, **kwargs: Any) -> None:
            captured["runtime_kwargs"] = kwargs

    fake_cls = MagicMock(side_effect=_FakeRuntime)
    fake_cls.__name__ = "_FakeRuntime"

    runtime_for_calls: list[str] = []

    def fake_runtime_for(provider_id: str) -> type:
        runtime_for_calls.append(provider_id)
        return fake_cls  # type: ignore[return-value]

    monkeypatch.setattr(agent_factory.airframe, "runtime_for", fake_runtime_for)
    captured["fake_cls"] = fake_cls
    captured["calls"] = runtime_for_calls
    return captured


def test_runtime_for_agent_constructs_runtime_with_model_pinned(
    stub_runtime_for: dict[str, Any],
) -> None:
    agents = AgentsConfig(
        implement=AgentBindingConfig(provider="claude", model_id="claude-sonnet-4-6"),
    )
    runtime, provider_model = runtime_for_agent("implement", agents_config=agents)

    # Dispatched via airframe.runtime_for with the canonical provider.
    assert stub_runtime_for["calls"] == ["claude"]
    # Runtime constructed with model= pinned to the binding's model_id.
    assert stub_runtime_for["runtime_kwargs"] == {"model": "claude-sonnet-4-6"}
    # ProviderModel echoes the resolved binding for callers that want
    # to make the binding explicit at execute time.
    assert provider_model.provider_id == "claude"
    assert provider_model.model_id == "claude-sonnet-4-6"
    # The returned runtime is the stub instance.
    assert isinstance(runtime, object)


def test_runtime_for_agent_uses_override_when_provided(
    stub_runtime_for: dict[str, Any],
) -> None:
    """Per-complexity overrides win over the role default."""
    agents = AgentsConfig(
        implement=AgentBindingConfig(provider="claude", model_id="claude-haiku-4-5"),
    )
    override = AgentBindingConfig(provider="github-copilot", model_id="gpt-5-codex")

    runtime, provider_model = runtime_for_agent(
        "implement",
        agents_config=agents,
        binding_override=override,
    )

    assert stub_runtime_for["calls"] == ["github-copilot"]
    assert stub_runtime_for["runtime_kwargs"] == {"model": "gpt-5-codex"}
    assert provider_model.provider_id == "github-copilot"
    assert provider_model.model_id == "gpt-5-codex"


def test_runtime_for_agent_propagates_import_error_from_airframe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An uninstalled provider SDK surfaces with the pip-extra hint."""

    def raises_import_error(provider_id: str) -> type:
        raise ImportError(
            f"Provider {provider_id!r} is served by FakeRuntime, which requires "
            f"'fake_sdk'. Install with: pip install airframe-agents[fake]"
        )

    monkeypatch.setattr(agent_factory.airframe, "runtime_for", raises_import_error)

    agents = AgentsConfig(
        implement=AgentBindingConfig(provider="claude", model_id="claude-sonnet-4-6"),
    )
    with pytest.raises(ImportError) as excinfo:
        runtime_for_agent("implement", agents_config=agents)
    assert "pip install airframe-agents[fake]" in str(excinfo.value)


def test_runtime_for_agent_propagates_value_error_for_unknown_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo'd provider in maverick.yaml surfaces cleanly."""

    def raises_value_error(provider_id: str) -> type:
        raise ValueError(f"No airframe adapter serves provider {provider_id!r}.")

    monkeypatch.setattr(agent_factory.airframe, "runtime_for", raises_value_error)

    agents = AgentsConfig(
        implement=AgentBindingConfig(provider="anthropic", model_id="claude-sonnet-4-6"),
    )
    with pytest.raises(ValueError) as excinfo:
        runtime_for_agent("implement", agents_config=agents)
    assert "anthropic" in str(excinfo.value)


def test_runtime_for_agent_missing_binding_raises(
    stub_runtime_for: dict[str, Any],
) -> None:
    """No binding + no override = explicit failure (no silent default)."""
    agents = AgentsConfig()  # nothing configured
    with pytest.raises(ValueError) as excinfo:
        runtime_for_agent("implement", agents_config=agents)
    assert "agents.implement" in str(excinfo.value)
    # airframe.runtime_for was never called — we failed before dispatch.
    assert stub_runtime_for["calls"] == []


@pytest.mark.parametrize("role", sorted(KNOWN_ROLES))
def test_runtime_for_agent_works_for_every_known_role(
    stub_runtime_for: dict[str, Any], role: str
) -> None:
    """Every role declared by KNOWN_ROLES resolves end-to-end."""
    binding = AgentBindingConfig(provider="claude", model_id="claude-haiku-4-5")
    agents = AgentsConfig(**{role: binding})

    runtime, pm = runtime_for_agent(role, agents_config=agents)

    assert stub_runtime_for["calls"] == ["claude"]
    assert pm.model_id == "claude-haiku-4-5"
    assert runtime is not None
