"""Shared test fixtures for Python workflow tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from maverick.checkpoint.store import MemoryCheckpointStore


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
    """Return a MagicMock with spec=MaverickConfig providing steps/model."""
    from maverick.config import MaverickConfig, ModelConfig

    cfg = MagicMock(spec=MaverickConfig)
    cfg.steps = {}
    cfg.agents = {}
    cfg.model = ModelConfig()
    return cfg


@pytest.fixture
def mock_registry() -> MagicMock:
    """Return a MagicMock ComponentRegistry."""
    from maverick.registry import ComponentRegistry

    return MagicMock(spec=ComponentRegistry)


@pytest.fixture
def memory_checkpoint_store() -> MemoryCheckpointStore:
    """Return a real MemoryCheckpointStore instance."""
    return MemoryCheckpointStore()


@pytest.fixture
def concrete_workflow(
    mock_config: MagicMock,
    mock_registry: MagicMock,
    memory_checkpoint_store: MemoryCheckpointStore,
) -> Any:
    """Return a ConcreteTestWorkflow with default no-op _run behaviour."""
    ConcreteTestWorkflow = _make_concrete_workflow_class()
    return ConcreteTestWorkflow(
        config=mock_config,
        registry=mock_registry,
        checkpoint_store=memory_checkpoint_store,
        workflow_name="test-workflow",
    )
