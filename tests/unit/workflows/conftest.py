"""Shared test fixtures for Python workflow tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import ExitStack, contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@contextmanager
def stub_squadron_io() -> Any:
    """Bypass real airframe runtime construction for unit-level workflow tests.

    Pattern D squadrons construct one :class:`airframe.AgentRuntime` per
    agent role via :func:`airframe.runtime_for`. Pure-unit workflow
    tests don't want to pull in real adapter SDKs — they care about
    supervisor inputs, not substrate. This helper substitutes a
    minimal stub class for whatever provider the factory dispatches to.
    """

    class _StubRuntime:
        label = "stub"

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def reset(self) -> None:
            return None

        async def close(self) -> None:
            return None

        async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
            raise NotImplementedError("stub")

    def _stub_runtime_for(_provider_id: str) -> type[_StubRuntime]:
        return _StubRuntime

    with ExitStack() as stack:
        stack.enter_context(patch("airframe.runtime_for", new=_stub_runtime_for))
        yield


def _make_concrete_workflow_class() -> type:
    """Lazily import PythonWorkflow and return a concrete test subclass.

    Importing PythonWorkflow at module level would fail when base.py doesn't
    exist yet (pre-TDD failure phase). The factory defers the import until
    fixture invocation time, so test collection itself always succeeds.
    """
    from maverick.workflows.base import PythonWorkflow

    class ConcreteTestWorkflow(PythonWorkflow):
        """Minimal concrete subclass used exclusively in unit tests.

        The ``run_fn`` injected at construction time drives ``_run()``,
        allowing each test to control workflow behaviour without subclassing.
        """

        def __init__(
            self,
            *,
            run_fn: Callable[[dict[str, Any]], Awaitable[Any]] | None = None,
            **kwargs: Any,
        ) -> None:
            super().__init__(**kwargs)
            self._run_fn = run_fn

        async def _run(self, inputs: dict[str, Any]) -> Any:
            """Delegate to the injected run_fn if provided, otherwise no-op."""
            if self._run_fn is not None:
                return await self._run_fn(inputs)
            return None

    return ConcreteTestWorkflow


@pytest.fixture
def mock_config() -> MagicMock:
    """Return a MagicMock with spec=MaverickConfig providing steps/model/parallel.

    The ``agents:`` field is a real :class:`AgentsConfig` with every role
    populated — the squadron's :meth:`open` requires bindings to construct
    airframe runtimes via :func:`runtime_for_agent`.
    """
    from maverick.config import (
        AgentBindingConfig,
        AgentsConfig,
        MaverickConfig,
        ModelConfig,
        ParallelConfig,
    )

    cfg = MagicMock(spec=MaverickConfig)
    cfg.steps = {}
    binding = AgentBindingConfig(provider="claude", model_id="claude-sonnet-4-6")
    cfg.agents = AgentsConfig(
        implement=binding,
        review=binding,
        briefing=binding,
        decompose=binding,
        generate=binding,
    )
    cfg.actors = {}
    cfg.agent_providers = {}
    cfg.model = ModelConfig()
    # Real ParallelConfig — workflows now read parallel.* knobs at runtime
    # (decomposer_pool_size, max_briefing_agents, max_parallel_reviewers).
    cfg.parallel = ParallelConfig()
    return cfg


@pytest.fixture
def concrete_workflow(
    mock_config: MagicMock,
) -> Any:
    """Return a ConcreteTestWorkflow with default no-op _run behaviour."""
    ConcreteTestWorkflow = _make_concrete_workflow_class()
    return ConcreteTestWorkflow(
        config=mock_config,
        workflow_name="test-workflow",
    )
