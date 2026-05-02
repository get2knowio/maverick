"""T021: Validate quickstart.md scenarios.

Verifies that the code patterns described in quickstart.md work correctly
with the actual PythonWorkflow implementation.
"""

from __future__ import annotations

import contextlib
from typing import Any
from unittest.mock import MagicMock

import pytest

from maverick.events import (
    StepCompleted,
    StepOutput,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.workflows.base import PythonWorkflow

# ---------------------------------------------------------------------------
# Minimal workflow subclass as shown in quickstart.md Step 2
# ---------------------------------------------------------------------------


class _QuickstartWorkflow(PythonWorkflow):
    """Minimal concrete subclass matching the quickstart.md pattern."""

    async def _run(self, inputs: dict[str, Any]) -> Any:
        # Step 1: Do something (quickstart pattern)
        await self.emit_step_started("step_one")
        try:
            result = inputs["param"] + "_processed"
            await self.emit_step_completed("step_one", output=result)
        except Exception as e:
            await self.emit_step_failed("step_one", error=str(e))
            raise

        # Step 2: Do something else
        await self.emit_step_started("step_two")
        final = result.upper()
        await self.emit_step_completed("step_two", output=final)

        return {"result": final}


@pytest.fixture
def workflow(mock_config: MagicMock) -> _QuickstartWorkflow:
    """Create a quickstart workflow with mock dependencies."""
    return _QuickstartWorkflow(
        config=mock_config,
        workflow_name="test-workflow",
    )


class TestQuickstartHappyPath:
    """Verify the basic quickstart.md happy-path scenario."""

    async def test_happy_path(self, workflow: _QuickstartWorkflow) -> None:
        """Workflow completes successfully with expected events."""
        events = []
        async for event in workflow.execute({"param": "value"}):
            events.append(event)

        # Final event is WorkflowCompleted with success=True
        last = events[-1]
        assert isinstance(last, WorkflowCompleted)
        assert last.success is True

        # Workflow result is accessible
        assert workflow.result is not None
        assert workflow.result.success is True
        assert workflow.result.final_output == {"result": "VALUE_PROCESSED"}

    async def test_step_names_in_events(self, workflow: _QuickstartWorkflow) -> None:
        """Check step names from the quickstart code example appear in events."""
        events = []
        async for event in workflow.execute({"param": "value"}):
            events.append(event)

        step_names = [e.step_name for e in events if hasattr(e, "step_name")]
        assert "step_one" in step_names
        assert "step_two" in step_names

    async def test_workflow_started_first(self, workflow: _QuickstartWorkflow) -> None:
        """First event is WorkflowStarted as shown in quickstart."""
        events = []
        async for event in workflow.execute({"param": "value"}):
            events.append(event)

        assert isinstance(events[0], WorkflowStarted)
        assert events[0].workflow_name == "test-workflow"

    async def test_step_failure_emits_failed_event(
        self, mock_config: MagicMock
    ) -> None:
        """Step failure pattern from quickstart: emit_step_failed then raise."""

        class _FailingWorkflow(PythonWorkflow):
            async def _run(self, inputs: dict[str, Any]) -> Any:
                await self.emit_step_started("my_step")
                try:
                    raise ValueError("something broke")
                except Exception as e:
                    await self.emit_step_failed("my_step", error=str(e))
                    raise

        wf = _FailingWorkflow(
            config=mock_config,
            workflow_name="test-workflow",
        )
        events = []
        # execute() re-raises after WorkflowCompleted (R-012); suppress here
        # since this test focuses on the emitted events, not the re-raise.
        with contextlib.suppress(ValueError):
            async for event in wf.execute({}):
                events.append(event)

        # WorkflowCompleted with success=False
        last = events[-1]
        assert isinstance(last, WorkflowCompleted)
        assert last.success is False

        # StepCompleted(success=False) present
        failed_events = [e for e in events if isinstance(e, StepCompleted) and not e.success]
        assert len(failed_events) == 1
        assert failed_events[0].step_name == "my_step"


class TestQuickstartConfigResolution:
    """Verify resolve_step_config() as shown in quickstart.md."""

    def test_resolve_step_config_returns_step_config(self, workflow: _QuickstartWorkflow) -> None:
        """resolve_step_config() returns a StepConfig."""
        from maverick.executor.config import StepConfig

        config = workflow.resolve_step_config("review")
        assert isinstance(config, StepConfig)
        assert config.mode is not None

    def test_resolve_step_config_uses_project_overrides(
        self, mock_config: MagicMock
    ) -> None:
        """Config from maverick.yaml steps dict overrides defaults."""
        from maverick.executor.config import StepConfig

        override = StepConfig(timeout=999)
        mock_config.steps = {"implement": override}

        wf = _QuickstartWorkflow(
            config=mock_config,
            workflow_name="test-workflow",
        )
        config = wf.resolve_step_config("implement")
        assert config.timeout == 999


class TestQuickstartProgressEvents:
    """Verify emit_output() for informational messages."""

    async def test_emit_output_info(
        self, mock_config: MagicMock
    ) -> None:
        """emit_output() emits StepOutput at correct level."""

        class _OutputWorkflow(PythonWorkflow):
            async def _run(self, inputs: dict[str, Any]) -> Any:
                await self.emit_step_started("my_step")
                await self.emit_output("my_step", "Processing item 3/10...", level="info")
                await self.emit_output("my_step", "All items processed", level="success")
                await self.emit_output("my_step", "Skipping optional check", level="warning")
                await self.emit_step_completed("my_step")
                return None

        wf = _OutputWorkflow(
            config=mock_config,
            workflow_name="test-workflow",
        )
        events = []
        async for event in wf.execute({}):
            events.append(event)

        output_events = [e for e in events if isinstance(e, StepOutput)]
        assert len(output_events) == 3
        levels = [e.level for e in output_events]
        assert "info" in levels
        assert "success" in levels
        assert "warning" in levels


class TestQuickstartRollback:
    """Verify register_rollback() pattern from quickstart.md."""

    async def test_rollback_runs_on_failure(
        self, mock_config: MagicMock
    ) -> None:
        """Registered rollback executes when workflow fails."""
        rollback_called = False

        async def _teardown() -> None:
            nonlocal rollback_called
            rollback_called = True

        class _RollbackWorkflow(PythonWorkflow):
            async def _run(self, inputs: dict[str, Any]) -> Any:
                await self.emit_step_started("create_workspace")
                await self.emit_step_completed("create_workspace")
                # Register rollback (quickstart pattern)
                self.register_rollback("workspace_teardown", _teardown)
                # Now fail
                raise RuntimeError("implement failed")

        wf = _RollbackWorkflow(
            config=mock_config,
            workflow_name="test-workflow",
        )
        events = []
        # execute() re-raises after WorkflowCompleted (R-012); suppress here
        # since this test focuses on rollback execution and event stream.
        with contextlib.suppress(RuntimeError):
            async for event in wf.execute({}):
                events.append(event)

        assert rollback_called is True
        last = events[-1]
        assert isinstance(last, WorkflowCompleted)
        assert last.success is False
