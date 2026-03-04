"""Unit tests for PythonWorkflow abstract base class.

Tests are organised into class groups matching the behaviour being verified.
All async tests rely on the project-wide ``asyncio_mode = "auto"`` setting in
pyproject.toml — no ``@pytest.mark.asyncio`` decorator is needed.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import MagicMock

import pytest

from maverick.checkpoint.store import MemoryCheckpointStore
from maverick.events import (
    CheckpointSaved,
    RollbackCompleted,
    RollbackStarted,
    StepCompleted,
    StepOutput,
    StepStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.results import WorkflowResult
from maverick.types import StepType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workflow(
    run_fn: Callable[[dict[str, Any]], Awaitable[Any]] | None = None,
    *,
    workflow_name: str = "test-workflow",
    checkpoint_store: MemoryCheckpointStore | None = None,
    steps_override: dict[str, Any] | None = None,
) -> Any:
    """Instantiate a ConcreteTestWorkflow with injected dependencies.

    Reuses the shared ``_make_concrete_workflow_class`` factory from conftest
    to avoid duplicating the ``ConcreteTestWorkflow`` class definition.
    """
    from maverick.config import MaverickConfig, ModelConfig
    from maverick.registry import ComponentRegistry
    from tests.unit.workflows.conftest import _make_concrete_workflow_class

    ConcreteTestWorkflow = _make_concrete_workflow_class()

    mock_config = MagicMock(spec=MaverickConfig)
    mock_config.model = ModelConfig()
    mock_config.steps = steps_override or {}

    mock_registry = MagicMock(spec=ComponentRegistry)

    return ConcreteTestWorkflow(
        run_fn=run_fn,
        config=mock_config,
        registry=mock_registry,
        checkpoint_store=checkpoint_store or MemoryCheckpointStore(),
        workflow_name=workflow_name,
    )


async def _collect_events(
    workflow: Any,
    inputs: dict[str, Any],
    *,
    ignore_exception: bool = False,
) -> list[Any]:
    """Drive execute() to completion and return all emitted events.

    When ignore_exception=True, swallows any exception re-raised by execute()
    after WorkflowCompleted (R-012 behaviour). Use this in tests that only need
    to verify the event stream and result, not the re-raise itself.
    """
    events: list[Any] = []
    try:
        async for event in workflow.execute(inputs):
            events.append(event)
    except Exception:
        if not ignore_exception:
            raise
    return events


# ---------------------------------------------------------------------------
# T005-a: Constructor validation
# ---------------------------------------------------------------------------


class TestConstructor:
    """PythonWorkflow constructor validation."""

    def test_constructor_requires_config(self) -> None:
        """TypeError raised when config=None."""
        from maverick.workflows.base import PythonWorkflow

        class _Impl(PythonWorkflow):
            async def _run(self, inputs: dict[str, Any]) -> Any:
                return None

        with pytest.raises(TypeError):
            _Impl(
                config=None,  # type: ignore[arg-type]
                registry=MagicMock(),
                workflow_name="wf",
            )

    def test_constructor_requires_registry(self) -> None:
        """TypeError raised when registry=None."""
        from maverick.config import MaverickConfig
        from maverick.workflows.base import PythonWorkflow

        class _Impl(PythonWorkflow):
            async def _run(self, inputs: dict[str, Any]) -> Any:
                return None

        with pytest.raises(TypeError):
            _Impl(
                config=MagicMock(spec=MaverickConfig),
                registry=None,  # type: ignore[arg-type]
                workflow_name="wf",
            )

    def test_constructor_stores_workflow_name(self) -> None:
        """workflow_name is accessible on the instance."""
        wf = _make_workflow(workflow_name="my-workflow")
        assert wf._workflow_name == "my-workflow"

    def test_result_initially_none(self) -> None:
        """result attribute starts as None before execute() is called."""
        wf = _make_workflow()
        assert wf.result is None


# ---------------------------------------------------------------------------
# T005-b: execute() template method — top-level events
# ---------------------------------------------------------------------------


class TestExecuteTemplateMethod:
    """execute() yields the correct framing events."""

    async def test_execute_yields_workflow_started_first(self) -> None:
        """First event yielded is WorkflowStarted."""
        wf = _make_workflow()
        events = await _collect_events(wf, {"key": "value"})
        assert isinstance(events[0], WorkflowStarted)
        assert events[0].workflow_name == "test-workflow"
        assert events[0].inputs == {"key": "value"}

    async def test_execute_yields_workflow_completed_last(self) -> None:
        """Last event yielded is WorkflowCompleted."""
        wf = _make_workflow()
        events = await _collect_events(wf, {})
        assert isinstance(events[-1], WorkflowCompleted)
        assert events[-1].workflow_name == "test-workflow"
        assert events[-1].success is True

    async def test_execute_stores_result_on_self(self) -> None:
        """workflow.result is populated after iteration completes."""
        wf = _make_workflow()
        await _collect_events(wf, {})
        assert wf.result is not None
        assert isinstance(wf.result, WorkflowResult)
        assert wf.result.success is True
        assert wf.result.workflow_name == "test-workflow"

    async def test_workflow_completed_has_duration(self) -> None:
        """WorkflowCompleted event includes a non-negative total_duration_ms."""
        wf = _make_workflow()
        events = await _collect_events(wf, {})
        completed = events[-1]
        assert isinstance(completed, WorkflowCompleted)
        assert completed.total_duration_ms >= 0

    async def test_workflow_completed_success_false_on_error(self) -> None:
        """WorkflowCompleted.success=False when _run raises an exception."""

        async def _failing_run(inputs: dict[str, Any]) -> Any:
            raise RuntimeError("boom")

        wf = _make_workflow(run_fn=_failing_run)
        events = await _collect_events(wf, {}, ignore_exception=True)
        completed = events[-1]
        assert isinstance(completed, WorkflowCompleted)
        assert completed.success is False

    async def test_execute_stores_failure_result_on_self(self) -> None:
        """workflow.result.success=False after _run raises."""

        async def _failing_run(inputs: dict[str, Any]) -> Any:
            raise RuntimeError("boom")

        wf = _make_workflow(run_fn=_failing_run)
        await _collect_events(wf, {}, ignore_exception=True)
        assert wf.result is not None
        assert wf.result.success is False

    async def test_execute_reraises_exception_after_workflow_completed(self) -> None:
        """execute() re-raises _run's exception after yielding WorkflowCompleted.

        Verifies R-012 behaviour.
        """

        async def _failing_run(inputs: dict[str, Any]) -> Any:
            raise RuntimeError("re-raise-me")

        wf = _make_workflow(run_fn=_failing_run)
        events: list[Any] = []
        with pytest.raises(RuntimeError, match="re-raise-me"):
            async for event in wf.execute({}):
                events.append(event)

        # WorkflowCompleted must have been yielded before the re-raise
        completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert completed.success is False

    async def test_final_output_stored_in_result(self) -> None:
        """The return value of _run() is stored in workflow.result.final_output."""

        async def _run(inputs: dict[str, Any]) -> dict[str, Any]:
            return {"status": "done"}

        wf = _make_workflow(run_fn=_run)
        await _collect_events(wf, {})
        assert wf.result is not None
        assert wf.result.final_output == {"status": "done"}


# ---------------------------------------------------------------------------
# T005-c: emit_step_started / emit_step_completed / emit_step_failed
# ---------------------------------------------------------------------------


class TestStepEvents:
    """Step-level event emission helpers."""

    async def test_execute_step_started_event(self) -> None:
        """emit_step_started puts a StepStarted event in the stream."""

        async def _run(inputs: dict[str, Any]) -> None:
            # wf is captured via closure
            await wf.emit_step_started("my-step")

        wf = _make_workflow(run_fn=_run)
        events = await _collect_events(wf, {})
        step_started = [e for e in events if isinstance(e, StepStarted)]
        assert len(step_started) == 1
        assert step_started[0].step_name == "my-step"
        assert step_started[0].step_type == StepType.PYTHON

    async def test_execute_step_completed_event(self) -> None:
        """emit_step_completed puts a StepCompleted(success=True) event."""

        async def _run(inputs: dict[str, Any]) -> None:
            await wf.emit_step_started("step-a")
            await wf.emit_step_completed("step-a", output=42)

        wf = _make_workflow(run_fn=_run)
        events = await _collect_events(wf, {})
        step_completed = [e for e in events if isinstance(e, StepCompleted)]
        assert len(step_completed) == 1
        assert step_completed[0].step_name == "step-a"
        assert step_completed[0].success is True
        assert step_completed[0].duration_ms >= 0

    async def test_execute_step_failed_event(self) -> None:
        """emit_step_failed puts a StepCompleted(success=False) event."""

        async def _run(inputs: dict[str, Any]) -> None:
            await wf.emit_step_started("step-b")
            await wf.emit_step_failed("step-b", error="something went wrong")

        wf = _make_workflow(run_fn=_run)
        events = await _collect_events(wf, {})
        step_completed = [e for e in events if isinstance(e, StepCompleted)]
        assert len(step_completed) == 1
        assert step_completed[0].step_name == "step-b"
        assert step_completed[0].success is False
        assert "something went wrong" in (step_completed[0].error or "")

    async def test_execute_step_output_event(self) -> None:
        """emit_output puts a StepOutput event in the stream."""

        async def _run(inputs: dict[str, Any]) -> None:
            await wf.emit_output("step-c", message="hello", level="info")

        wf = _make_workflow(run_fn=_run)
        events = await _collect_events(wf, {})
        outputs = [e for e in events if isinstance(e, StepOutput)]
        assert len(outputs) == 1
        assert outputs[0].step_name == "step-c"
        assert outputs[0].message == "hello"
        assert outputs[0].level == "info"

    async def test_step_result_tracking(self) -> None:
        """Step results are accumulated and reflected in workflow.result."""

        async def _run(inputs: dict[str, Any]) -> None:
            await wf.emit_step_started("step-1")
            await wf.emit_step_completed("step-1", output="out1")
            await wf.emit_step_started("step-2")
            await wf.emit_step_completed("step-2", output="out2")

        wf = _make_workflow(run_fn=_run)
        await _collect_events(wf, {})
        assert wf.result is not None
        assert len(wf.result.step_results) == 2
        names = [r.name for r in wf.result.step_results]
        assert "step-1" in names
        assert "step-2" in names

    async def test_step_path_format(self) -> None:
        """step_path on StepStarted is '{workflow_name}.{step_name}'."""

        async def _run(inputs: dict[str, Any]) -> None:
            await wf.emit_step_started("my-step")

        wf = _make_workflow(run_fn=_run, workflow_name="my-wf")
        events = await _collect_events(wf, {})
        started = next(e for e in events if isinstance(e, StepStarted))
        assert started.step_path == "my-wf.my-step"

    async def test_step_completed_path_format(self) -> None:
        """step_path on StepCompleted is '{workflow_name}.{step_name}'."""

        async def _run(inputs: dict[str, Any]) -> None:
            await wf.emit_step_started("step-x")
            await wf.emit_step_completed("step-x")

        wf = _make_workflow(run_fn=_run, workflow_name="wf-name")
        events = await _collect_events(wf, {})
        completed = next(e for e in events if isinstance(e, StepCompleted))
        assert completed.step_path == "wf-name.step-x"


# ---------------------------------------------------------------------------
# T005-d: resolve_step_config
# ---------------------------------------------------------------------------


class TestResolveStepConfig:
    """resolve_step_config delegation behaviour."""

    def test_resolve_step_config_returns_step_config(self) -> None:
        """resolve_step_config() returns a StepConfig instance."""
        from maverick.executor.config import StepConfig

        wf = _make_workflow()
        cfg = wf.resolve_step_config("some-step")
        assert isinstance(cfg, StepConfig)

    def test_resolve_step_config_uses_project_steps(self) -> None:
        """resolve_step_config() picks up per-step overrides from config.steps."""
        from maverick.executor.config import StepConfig

        override = StepConfig(model_id="claude-opus-4-6")
        wf = _make_workflow(steps_override={"my-step": override})
        cfg = wf.resolve_step_config("my-step")
        assert cfg.model_id == "claude-opus-4-6"

    def test_resolve_step_config_defaults_to_python_step_type(self) -> None:
        """Default step_type for resolve_step_config is PYTHON (deterministic mode)."""
        from maverick.types import StepMode

        wf = _make_workflow()
        cfg = wf.resolve_step_config("any-step")
        assert cfg.mode == StepMode.DETERMINISTIC


# ---------------------------------------------------------------------------
# T005-e: register_rollback / rollback execution
# ---------------------------------------------------------------------------


class TestRollback:
    """Rollback registration and execution on workflow failure."""

    async def test_register_rollback_executes_on_failure(self) -> None:
        """Registered rollback actions are called when _run raises."""
        rollback_called = []

        async def _rollback() -> None:
            rollback_called.append(True)

        async def _failing_run(inputs: dict[str, Any]) -> None:
            wf.register_rollback("cleanup", _rollback)
            raise RuntimeError("failure")

        wf = _make_workflow(run_fn=_failing_run)
        await _collect_events(wf, {}, ignore_exception=True)
        assert rollback_called == [True]

    async def test_rollback_reverse_order(self) -> None:
        """Multiple rollbacks execute in reverse registration order."""
        order: list[str] = []

        async def _rb1() -> None:
            order.append("rb1")

        async def _rb2() -> None:
            order.append("rb2")

        async def _rb3() -> None:
            order.append("rb3")

        async def _run(inputs: dict[str, Any]) -> None:
            wf.register_rollback("rb1", _rb1)
            wf.register_rollback("rb2", _rb2)
            wf.register_rollback("rb3", _rb3)
            raise RuntimeError("fail")

        wf = _make_workflow(run_fn=_run)
        await _collect_events(wf, {}, ignore_exception=True)
        assert order == ["rb3", "rb2", "rb1"]

    async def test_rollback_not_called_on_success(self) -> None:
        """Rollback actions are NOT called when _run succeeds."""
        rollback_called = []

        async def _rollback() -> None:
            rollback_called.append(True)

        async def _successful_run(inputs: dict[str, Any]) -> None:
            wf.register_rollback("cleanup", _rollback)

        wf = _make_workflow(run_fn=_successful_run)
        await _collect_events(wf, {})
        assert rollback_called == []

    async def test_rollback_emits_rollback_events(self) -> None:
        """RollbackStarted and RollbackCompleted events are emitted during rollback."""

        async def _rb() -> None:
            pass

        async def _run(inputs: dict[str, Any]) -> None:
            wf.register_rollback("my-rb", _rb)
            raise RuntimeError("fail")

        wf = _make_workflow(run_fn=_run)
        events = await _collect_events(wf, {}, ignore_exception=True)
        rb_started = [e for e in events if isinstance(e, RollbackStarted)]
        rb_completed = [e for e in events if isinstance(e, RollbackCompleted)]
        assert len(rb_started) == 1
        assert rb_started[0].step_name == "my-rb"
        assert len(rb_completed) == 1
        assert rb_completed[0].success is True

    async def test_cancellation_triggers_rollback(self) -> None:
        """asyncio.CancelledError triggers rollback execution."""
        rollback_called = []

        async def _rb() -> None:
            rollback_called.append(True)

        async def _run(inputs: dict[str, Any]) -> None:
            wf.register_rollback("cleanup", _rb)
            raise asyncio.CancelledError()

        wf = _make_workflow(run_fn=_run)
        # CancelledError should not propagate through execute() uncaught —
        # the ABC must handle it; we just verify rollback ran.
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await _collect_events(wf, {})
        assert rollback_called == [True]


# ---------------------------------------------------------------------------
# T005-f: save_checkpoint / load_checkpoint
# ---------------------------------------------------------------------------


class TestCheckpointing:
    """Checkpoint delegation to CheckpointStore."""

    async def test_save_checkpoint_delegates_to_store(self) -> None:
        """save_checkpoint stores data via the checkpoint store."""
        store = MemoryCheckpointStore()

        async def _run(inputs: dict[str, Any]) -> None:
            await wf.save_checkpoint({"progress": 1})

        wf = _make_workflow(run_fn=_run, checkpoint_store=store)
        await _collect_events(wf, {})
        loaded = await store.load_latest("test-workflow")
        assert loaded is not None

    async def test_save_checkpoint_emits_event(self) -> None:
        """save_checkpoint emits a CheckpointSaved event."""

        async def _run(inputs: dict[str, Any]) -> None:
            await wf.save_checkpoint({"step": "one"})

        wf = _make_workflow(run_fn=_run)
        events = await _collect_events(wf, {})
        cp_events = [e for e in events if isinstance(e, CheckpointSaved)]
        assert len(cp_events) == 1
        assert cp_events[0].workflow_id == "test-workflow"

    async def test_load_checkpoint_returns_data(self) -> None:
        """load_checkpoint returns previously saved checkpoint data."""
        store = MemoryCheckpointStore()

        async def _run(inputs: dict[str, Any]) -> dict[str, Any] | None:
            await wf.save_checkpoint({"progress": 42})
            return await wf.load_checkpoint()

        wf = _make_workflow(run_fn=_run, checkpoint_store=store)
        await _collect_events(wf, {})
        assert wf.result is not None
        # The return value of _run (the loaded checkpoint) is stored in final_output
        loaded = wf.result.final_output
        assert loaded is not None

    async def test_load_checkpoint_returns_none_when_no_checkpoint(self) -> None:
        """load_checkpoint returns None when no checkpoint has been saved."""

        async def _run(inputs: dict[str, Any]) -> Any:
            return await wf.load_checkpoint()

        wf = _make_workflow(run_fn=_run)
        await _collect_events(wf, {})
        assert wf.result is not None
        assert wf.result.final_output is None

    async def test_save_checkpoint_noop_without_store(self) -> None:
        """save_checkpoint is a no-op when checkpoint_store is None."""
        from maverick.config import MaverickConfig, ModelConfig
        from maverick.registry import ComponentRegistry
        from maverick.workflows.base import PythonWorkflow

        class _Impl(PythonWorkflow):
            async def _run(self, inputs: dict[str, Any]) -> None:
                await self.save_checkpoint({"x": 1})

        mock_cfg = MagicMock(spec=MaverickConfig)
        mock_cfg.model = ModelConfig()
        mock_cfg.steps = {}

        wf = _Impl(
            config=mock_cfg,
            registry=MagicMock(spec=ComponentRegistry),
            checkpoint_store=None,
            workflow_name="wf-no-store",
        )
        # Must not raise
        events = await _collect_events(wf, {})
        completed = events[-1]
        assert isinstance(completed, WorkflowCompleted)
        assert completed.success is True
