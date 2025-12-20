"""Integration tests validating quickstart.md examples work correctly.

These tests verify that the code examples in quickstart.md are functional
with the implemented DSL.
"""

from __future__ import annotations

import pytest

from maverick.dsl import (
    ProgressEvent,
    StepCompleted,
    StepStarted,
    WorkflowCompleted,
    WorkflowEngine,
    WorkflowStarted,
    step,
    workflow,
)


class TestBasicWorkflowExample:
    """Test the basic workflow example from quickstart.md."""

    @pytest.mark.asyncio
    async def test_hello_workflow(self) -> None:
        """Test the hello-world workflow example."""

        @workflow(name="hello-world", description="A simple example workflow")
        def hello_workflow(name: str):
            """Greet someone with multiple steps."""
            # Step 1: Format greeting
            greeting = yield step("format_greeting").python(
                action=lambda n: f"Hello, {n}!",
                args=(name,),
            )

            # Step 2: Make uppercase
            uppercase = yield step("uppercase").python(
                action=str.upper,
                args=(greeting,),
            )

            # Return final result
            return {"greeting": greeting, "uppercase": uppercase}

        engine = WorkflowEngine()
        events: list[ProgressEvent] = []

        async for event in engine.execute(hello_workflow, name="Alice"):
            events.append(event)

        result = engine.get_result()

        # Verify success
        assert result.success is True
        assert result.final_output == {
            "greeting": "Hello, Alice!",
            "uppercase": "HELLO, ALICE!",
        }

        # Verify event sequence
        assert len(events) == 6
        assert isinstance(events[0], WorkflowStarted)
        assert events[0].workflow_name == "hello-world"
        assert isinstance(events[1], StepStarted)
        assert events[1].step_name == "format_greeting"
        assert isinstance(events[2], StepCompleted)
        assert events[2].step_name == "format_greeting"
        assert isinstance(events[3], StepStarted)
        assert events[3].step_name == "uppercase"
        assert isinstance(events[4], StepCompleted)
        assert events[4].step_name == "uppercase"
        assert isinstance(events[5], WorkflowCompleted)


class TestPythonStepExamples:
    """Test Python step examples from quickstart.md."""

    @pytest.mark.asyncio
    async def test_python_example_workflow(self) -> None:
        """Test the python-example workflow."""

        def process_data(data: str) -> dict:
            return {"processed": data.strip().lower()}

        @workflow(name="python-example", description="Python step example")
        def python_example(raw_data: str):
            # Sync function
            result = yield step("process").python(
                action=process_data,
                args=(raw_data,),
            )

            # Lambda
            length = yield step("count").python(
                action=lambda d: len(d["processed"]),
                args=(result,),
            )

            return {"result": result, "length": length}

        engine = WorkflowEngine()
        async for _ in engine.execute(python_example, raw_data="  HELLO WORLD  "):
            pass

        result = engine.get_result()
        assert result.success is True
        assert result.final_output == {
            "result": {"processed": "hello world"},
            "length": 11,
        }


class TestSubWorkflowExample:
    """Test sub-workflow examples from quickstart.md."""

    @pytest.mark.asyncio
    async def test_subworkflow_execution(self) -> None:
        """Test parent/sub-workflow pattern."""

        @workflow(name="sub-workflow", description="Helper workflow")
        def helper_workflow(data: str):
            result = yield step("process").python(action=str.upper, args=(data,))
            return result

        @workflow(name="parent-workflow", description="Parent workflow")
        def parent_workflow(input_data: str):
            # Execute sub-workflow
            sub_result = yield step("run_helper").subworkflow(
                workflow=helper_workflow,
                inputs={"data": input_data},
            )

            # sub_result is SubWorkflowInvocationResult
            return sub_result.final_output

        engine = WorkflowEngine()
        async for _ in engine.execute(parent_workflow, input_data="hello"):
            pass

        result = engine.get_result()
        assert result.success is True
        assert result.final_output == "HELLO"


class TestErrorHandlingExamples:
    """Test error handling examples from quickstart.md."""

    @pytest.mark.asyncio
    async def test_step_failure_stops_workflow(self) -> None:
        """Test that step failures stop the workflow immediately."""

        @workflow(name="error-example", description="Error handling example")
        def error_example():
            def failing_action():
                raise ValueError("Something went wrong!")

            # This step will fail
            yield step("will_fail").python(action=failing_action)

            # This step never executes
            yield step("never_reached").python(action=lambda: "success")

        engine = WorkflowEngine()
        async for _ in engine.execute(error_example):
            pass

        result = engine.get_result()
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
    async def test_progress_event_matching(self) -> None:
        """Test that progress events work with pattern matching."""

        @workflow(name="event-test", description="Event matching test")
        def event_workflow():
            yield step("step1").python(action=lambda: "result1")
            yield step("step2").python(action=lambda: "result2")

        engine = WorkflowEngine()

        # Track events using pattern matching as shown in quickstart.md
        workflow_started = False
        steps_started: list[str] = []
        steps_completed: list[tuple[str, bool]] = []
        workflow_completed = False

        async for event in engine.execute(event_workflow):
            match event:
                case WorkflowStarted(workflow_name=name):
                    workflow_started = True
                    assert name == "event-test"

                case StepStarted(step_name=name, step_type=stype):
                    steps_started.append(name)

                case StepCompleted(step_name=name, success=ok, duration_ms=ms):
                    steps_completed.append((name, ok))

                case WorkflowCompleted(success=ok, total_duration_ms=ms):
                    workflow_completed = True
                    assert ok is True

        assert workflow_started is True
        assert steps_started == ["step1", "step2"]
        assert steps_completed == [("step1", True), ("step2", True)]
        assert workflow_completed is True


class TestBestPracticesExamples:
    """Test best practices examples from quickstart.md."""

    @pytest.mark.asyncio
    async def test_explicit_return(self) -> None:
        """Test explicit return pattern."""

        @workflow(name="explicit", description="...")
        def explicit_workflow(data: str):
            result = yield step("process").python(
                action=str.upper,
                args=(data,),
            )
            return {"processed": result, "input": data}

        engine = WorkflowEngine()
        async for _ in engine.execute(explicit_workflow, data="hello"):
            pass

        result = engine.get_result()
        assert result.success is True
        assert result.final_output == {"processed": "HELLO", "input": "hello"}

    @pytest.mark.asyncio
    async def test_implicit_return(self) -> None:
        """Test implicit last step output pattern."""

        @workflow(name="implicit", description="...")
        def implicit_workflow(data: str):
            yield step("process").python(action=str.upper, args=(data,))
            # Returns last step's output implicitly

        engine = WorkflowEngine()
        async for _ in engine.execute(implicit_workflow, data="hello"):
            pass

        result = engine.get_result()
        assert result.success is True
        # Last step output is returned implicitly
        assert result.final_output == "HELLO"


class TestAccessingPriorResults:
    """Test accessing prior step results from quickstart.md."""

    @pytest.mark.asyncio
    async def test_context_builder_access(self) -> None:
        """Test context builder accessing prior results pattern."""
        # This tests the pattern but with python steps instead of agent steps
        # since we don't have real agents to test with

        context_received: dict = {}

        @workflow(name="access-results", description="Access prior results")
        def access_results_example(input_value: str):
            first = yield step("first").python(action=str.upper, args=(input_value,))

            # Simulate what a context builder would receive by using python step
            def capture_context(first_result: str, original: str) -> dict:
                nonlocal context_received
                context_received = {
                    "first_result": first_result,
                    "original": original,
                }
                return context_received

            second = yield step("second").python(
                action=capture_context,
                args=(first, input_value),
            )

            return second

        engine = WorkflowEngine()
        async for _ in engine.execute(access_results_example, input_value="hello"):
            pass

        result = engine.get_result()
        assert result.success is True
        assert context_received["first_result"] == "HELLO"
        assert context_received["original"] == "hello"
