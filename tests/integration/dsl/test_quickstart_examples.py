"""Integration tests validating quickstart.md examples work correctly.

These tests verify that the code examples in quickstart.md are functional
with the implemented DSL using YAML-based workflows.
"""

from __future__ import annotations

import pytest

from maverick.dsl.events import (
    ProgressEvent,
    StepCompleted,
    StepStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.dsl.serialization import (
    ComponentRegistry,
    PythonStepRecord,
    SubWorkflowStepRecord,
    WorkflowFile,
    WorkflowFileExecutor,
)
from maverick.dsl.types import StepType


@pytest.fixture
def registry():
    """Create a component registry with test actions."""
    reg = ComponentRegistry()

    # Register actions used in tests
    @reg.actions.register("format_greeting")
    def format_greeting(n: str) -> str:
        return f"Hello, {n}!"

    @reg.actions.register("str_upper")
    def str_upper(s: str) -> str:
        return s.upper()

    @reg.actions.register("process_data")
    def process_data(data: str) -> dict:
        return {"processed": data.strip().lower()}

    @reg.actions.register("count_length")
    def count_length(d: dict) -> int:
        return len(d["processed"])

    @reg.actions.register("failing_action")
    def failing_action():
        raise ValueError("Something went wrong!")

    @reg.actions.register("capture_context")
    def capture_context(first_result: str, original: str) -> dict:
        return {
            "first_result": first_result,
            "original": original,
        }

    return reg


class TestBasicWorkflowExample:
    """Test the basic workflow example from quickstart.md."""

    @pytest.mark.asyncio
    async def test_hello_workflow(self, registry) -> None:
        """Test the hello-world workflow example."""
        # Create YAML-based workflow
        workflow = WorkflowFile(
            version="1.0",
            name="hello-world",
            description="A simple example workflow",
            inputs={"name": {"type": "string"}},
            steps=[
                PythonStepRecord(
                    name="format_greeting",
                    type=StepType.PYTHON,
                    action="format_greeting",
                    kwargs={"n": "${{ inputs.name }}"},
                ),
                PythonStepRecord(
                    name="uppercase",
                    type=StepType.PYTHON,
                    action="str_upper",
                    kwargs={"s": "${{ steps.format_greeting.output }}"},
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        events: list[ProgressEvent] = []

        async for event in executor.execute(workflow, inputs={"name": "Alice"}):
            events.append(event)

        result = executor.get_result()

        # Verify success
        assert result.success is True
        assert result.final_output == "HELLO, ALICE!"

        # Verify key events are present
        workflow_started_events = [e for e in events if isinstance(e, WorkflowStarted)]
        assert len(workflow_started_events) == 1
        assert workflow_started_events[0].workflow_name == "hello-world"

        step_started_events = [e for e in events if isinstance(e, StepStarted)]
        assert len(step_started_events) == 2
        assert step_started_events[0].step_name == "format_greeting"
        assert step_started_events[1].step_name == "uppercase"

        step_completed_events = [e for e in events if isinstance(e, StepCompleted)]
        assert len(step_completed_events) == 2
        assert step_completed_events[0].step_name == "format_greeting"
        assert step_completed_events[1].step_name == "uppercase"

        workflow_completed_events = [
            e for e in events if isinstance(e, WorkflowCompleted)
        ]
        assert len(workflow_completed_events) == 1


class TestPythonStepExamples:
    """Test Python step examples from quickstart.md."""

    @pytest.mark.asyncio
    async def test_python_example_workflow(self, registry) -> None:
        """Test the python-example workflow."""
        workflow = WorkflowFile(
            version="1.0",
            name="python-example",
            description="Python step example",
            inputs={"raw_data": {"type": "string"}},
            steps=[
                PythonStepRecord(
                    name="process",
                    type=StepType.PYTHON,
                    action="process_data",
                    kwargs={"data": "${{ inputs.raw_data }}"},
                ),
                PythonStepRecord(
                    name="count",
                    type=StepType.PYTHON,
                    action="count_length",
                    kwargs={"d": "${{ steps.process.output }}"},
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(
            workflow, inputs={"raw_data": "  HELLO WORLD  "}
        ):
            pass

        result = executor.get_result()
        assert result.success is True
        # Last step's output is the final output
        assert result.final_output == 11


class TestSubWorkflowExample:
    """Test sub-workflow examples from quickstart.md."""

    @pytest.mark.asyncio
    async def test_subworkflow_execution(self, registry) -> None:
        """Test parent/sub-workflow pattern."""
        # Register helper workflow
        helper_workflow = WorkflowFile(
            version="1.0",
            name="sub-workflow",
            description="Helper workflow",
            inputs={"data": {"type": "string"}},
            steps=[
                PythonStepRecord(
                    name="process",
                    type=StepType.PYTHON,
                    action="str_upper",
                    kwargs={"s": "${{ inputs.data }}"},
                )
            ],
        )
        registry.workflows.register("helper_workflow", helper_workflow)

        # Parent workflow
        parent_workflow = WorkflowFile(
            version="1.0",
            name="parent-workflow",
            description="Parent workflow",
            inputs={"input_data": {"type": "string"}},
            steps=[
                SubWorkflowStepRecord(
                    name="run_helper",
                    type=StepType.SUBWORKFLOW,
                    workflow="helper_workflow",
                    inputs={"data": "${{ inputs.input_data }}"},
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(
            parent_workflow, inputs={"input_data": "hello"}
        ):
            pass

        result = executor.get_result()
        assert result.success is True
        # For YAML workflows, the subworkflow step output is accessible
        # through step results. The final_output is the last step's output,
        # which may be None for subworkflow steps. We verify the workflow
        # succeeded and check step results
        assert len(result.step_results) == 1
        assert result.step_results[0].name == "run_helper"
        assert result.step_results[0].success is True


class TestErrorHandlingExamples:
    """Test error handling examples from quickstart.md."""

    @pytest.mark.asyncio
    async def test_step_failure_stops_workflow(self, registry) -> None:
        """Test that step failures stop the workflow immediately."""

        @registry.actions.register("success_action")
        def success_action():
            return "success"

        workflow = WorkflowFile(
            version="1.0",
            name="error-example",
            description="Error handling example",
            steps=[
                PythonStepRecord(
                    name="will_fail",
                    type=StepType.PYTHON,
                    action="failing_action",
                    kwargs={},
                ),
                PythonStepRecord(
                    name="never_reached",
                    type=StepType.PYTHON,
                    action="success_action",
                    kwargs={},
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is False
        assert result.failed_step is not None
        assert result.failed_step.name == "will_fail"
        assert "Something went wrong!" in result.failed_step.error

        # Verify never_reached step didn't execute
        step_names = [sr.name for sr in result.step_results]
        assert "will_fail" in step_names
        assert "never_reached" not in step_names


class TestProgressEventsForTUI:
    """Test progress event pattern matching from quickstart.md."""

    @pytest.mark.asyncio
    async def test_progress_event_matching(self, registry) -> None:
        """Test that progress events work with pattern matching."""

        @registry.actions.register("result1")
        def result1():
            return "result1"

        @registry.actions.register("result2")
        def result2():
            return "result2"

        workflow = WorkflowFile(
            version="1.0",
            name="event-test",
            description="Event matching test",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="result1",
                    kwargs={},
                ),
                PythonStepRecord(
                    name="step2",
                    type=StepType.PYTHON,
                    action="result2",
                    kwargs={},
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)

        # Track events using pattern matching as shown in quickstart.md
        workflow_started = False
        steps_started: list[str] = []
        steps_completed: list[tuple[str, bool]] = []
        workflow_completed = False

        async for event in executor.execute(workflow):
            match event:
                case WorkflowStarted(workflow_name=name):
                    workflow_started = True
                    assert name == "event-test"

                case StepStarted(step_name=name, step_type=_):
                    steps_started.append(name)

                case StepCompleted(step_name=name, success=ok, duration_ms=_):
                    steps_completed.append((name, ok))

                case WorkflowCompleted(success=ok, total_duration_ms=_):
                    workflow_completed = True
                    assert ok is True

        assert workflow_started is True
        assert steps_started == ["step1", "step2"]
        assert steps_completed == [("step1", True), ("step2", True)]
        assert workflow_completed is True


class TestBestPracticesExamples:
    """Test best practices examples from quickstart.md."""

    @pytest.mark.asyncio
    async def test_explicit_return(self, registry) -> None:
        """Test explicit return pattern (last step output is used)."""
        workflow = WorkflowFile(
            version="1.0",
            name="explicit",
            description="...",
            inputs={"data": {"type": "string"}},
            steps=[
                PythonStepRecord(
                    name="process",
                    type=StepType.PYTHON,
                    action="str_upper",
                    kwargs={"s": "${{ inputs.data }}"},
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow, inputs={"data": "hello"}):
            pass

        result = executor.get_result()
        assert result.success is True
        # In YAML workflows, final_output is the last step's output
        assert result.final_output == "HELLO"

    @pytest.mark.asyncio
    async def test_implicit_return(self, registry) -> None:
        """Test implicit last step output pattern."""
        workflow = WorkflowFile(
            version="1.0",
            name="implicit",
            description="...",
            inputs={"data": {"type": "string"}},
            steps=[
                PythonStepRecord(
                    name="process",
                    type=StepType.PYTHON,
                    action="str_upper",
                    kwargs={"s": "${{ inputs.data }}"},
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow, inputs={"data": "hello"}):
            pass

        result = executor.get_result()
        assert result.success is True
        # Last step output is returned implicitly
        assert result.final_output == "HELLO"


class TestAccessingPriorResults:
    """Test accessing prior step results from quickstart.md."""

    @pytest.mark.asyncio
    async def test_context_builder_access(self, registry) -> None:
        """Test context builder accessing prior results pattern."""
        workflow = WorkflowFile(
            version="1.0",
            name="access-results",
            description="Access prior results",
            inputs={"input_value": {"type": "string"}},
            steps=[
                PythonStepRecord(
                    name="first",
                    type=StepType.PYTHON,
                    action="str_upper",
                    kwargs={"s": "${{ inputs.input_value }}"},
                ),
                PythonStepRecord(
                    name="second",
                    type=StepType.PYTHON,
                    action="capture_context",
                    kwargs={
                        "first_result": "${{ steps.first.output }}",
                        "original": "${{ inputs.input_value }}",
                    },
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow, inputs={"input_value": "hello"}):
            pass

        result = executor.get_result()
        assert result.success is True
        # Final output is the last step's output
        assert result.final_output["first_result"] == "HELLO"
        assert result.final_output["original"] == "hello"
