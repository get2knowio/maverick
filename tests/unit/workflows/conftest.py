"""Shared test fixtures for Python workflow tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from contextlib import ExitStack, contextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@contextmanager
def stub_squadron_io() -> Any:
    """Bypass real OpenCode spawn/validate for unit-level workflow tests.

    Workflows now wrap ``actor_pool`` with a ``Squadron`` that spawns
    one ``opencode serve`` and validates every tier binding against
    ``GET /provider`` at startup. Pure-unit workflow tests don't want
    that — they care about supervisor inputs, not substrate. This
    helper short-circuits both calls.
    """
    fake_handle = MagicMock(base_url="http://fake-opencode", password="x")
    fake_handle.stop = AsyncMock(return_value=None)
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "maverick.squadron.base.spawn_opencode_server",
                new=AsyncMock(return_value=fake_handle),
            )
        )
        stack.enter_context(
            patch(
                "maverick.squadron.base.validate_model_id",
                new=AsyncMock(return_value=None),
            )
        )
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
    """Return a MagicMock with spec=MaverickConfig providing steps/model/parallel."""
    from maverick.config import MaverickConfig, ModelConfig, ParallelConfig

    cfg = MagicMock(spec=MaverickConfig)
    cfg.steps = {}
    cfg.agents = {}
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
