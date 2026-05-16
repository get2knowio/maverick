"""Shared fixtures for squadron tests.

The Pattern D squadrons construct agents via :func:`runtime_for_agent`,
which dispatches through :func:`airframe.runtime_for`. Without
intervention, every squadron unit test would either pull in a real
adapter SDK or hit a vendor endpoint.

These fixtures keep squadron tests fast and hermetic:

* :func:`stub_airframe_runtime` patches :func:`airframe.runtime_for` so
  the factory returns a tiny stub class. The stub records its
  construction kwargs (``model=`` etc.) so tests can assert per-tier
  bindings landed on the right runtime.
* :func:`full_agents_config` returns a ``MaverickConfig`` with every
  agent role populated — the squadron's minimum viable input.
"""

from __future__ import annotations

from typing import Any

import pytest

from maverick.config import AgentBindingConfig, AgentsConfig, MaverickConfig


class StubAirframeRuntime:
    """In-memory stand-in for an :class:`airframe.AgentRuntime`.

    The squadrons' ``_build_agents`` path constructs one of these per
    agent. Tracks ``model`` + ``label`` + tag pattern so tests can spot
    the squadron handed the right binding to the right agent.
    """

    label: str = "stub"

    def __init__(self, *, model: str | None = None, **kwargs: Any) -> None:
        self.model = model
        self.kwargs = kwargs
        self.execute_calls: list[dict[str, Any]] = []
        self.reset_calls = 0
        self.close_calls = 0

    async def execute(self, prompt: str, **kwargs: Any) -> Any:  # pragma: no cover
        self.execute_calls.append({"prompt": prompt, **kwargs})
        raise NotImplementedError("StubAirframeRuntime is not meant to execute prompts")

    async def reset(self) -> None:
        self.reset_calls += 1

    async def close(self) -> None:
        self.close_calls += 1

    def validate_binding(self, _binding: Any) -> bool:
        return True


@pytest.fixture
def stub_airframe_runtime(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch :func:`airframe.runtime_for` so the factory returns a stub.

    Returns a dict with ``constructed`` (list of every
    :class:`StubAirframeRuntime` the factory built) so tests can inspect
    the resolved bindings.
    """
    constructed: list[StubAirframeRuntime] = []

    def stub_factory(provider_id: str) -> type[StubAirframeRuntime]:
        # Wrap StubAirframeRuntime so each `runtime_for_agent` call yields
        # a fresh instance and the constructor records the provider too.
        class _BoundStub(StubAirframeRuntime):
            def __init__(self, *, model: str | None = None, **kwargs: Any) -> None:
                super().__init__(model=model, **kwargs)
                self.provider_id = provider_id
                constructed.append(self)

        return _BoundStub

    monkeypatch.setattr("airframe.runtime_for", stub_factory)
    return {"constructed": constructed}


@pytest.fixture
def full_agents_config() -> AgentsConfig:
    """A complete ``agents:`` block — every role populated.

    Squadron tests need bindings for every role they construct; one
    missing entry would surface as a ``ValueError`` from the factory.
    """
    return AgentsConfig(
        implement=AgentBindingConfig(provider="claude", model_id="claude-sonnet-4-6"),
        review=AgentBindingConfig(provider="claude", model_id="claude-haiku-4-5"),
        briefing=AgentBindingConfig(provider="github-copilot", model_id="gpt-5-mini"),
        decompose=AgentBindingConfig(provider="claude", model_id="claude-sonnet-4-6"),
        generate=AgentBindingConfig(provider="codex", model_id="gpt-5-codex"),
    )


@pytest.fixture
def config_with_agents(full_agents_config: AgentsConfig) -> MaverickConfig:
    """``MaverickConfig`` with every agent role bound — squadron-ready."""
    return MaverickConfig(agents=full_agents_config)
