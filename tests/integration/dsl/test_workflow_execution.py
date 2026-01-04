"""Integration tests for workflow execution.

These tests verify end-to-end workflow execution with the DSL,
testing real-world scenarios across multiple user stories using YAML-based workflows.
"""

from __future__ import annotations

import asyncio

import pytest

from maverick.dsl.events import (
    StepCompleted,
    StepStarted,
    ValidationCompleted,
    ValidationStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.dsl.serialization import (
    AgentStepRecord,
    ComponentRegistry,
    GenerateStepRecord,
    PythonStepRecord,
    SubWorkflowStepRecord,
    ValidateStepRecord,
    WorkflowFile,
    WorkflowFileExecutor,
)
from maverick.dsl.types import StepType


@pytest.fixture
def registry():
    """Create a component registry with test actions and components."""
    reg = ComponentRegistry()

    # Register actions
    @reg.actions.register("str_upper")
    def str_upper(s: str) -> str:
        return s.upper()

    @reg.actions.register("format_result")
    def format_result(x: str) -> str:
        return f"Result: {x}"

    @reg.actions.register("str_strip")
    def str_strip(s: str) -> str:
        return s.strip()

    @reg.actions.register("multiply_by_two")
    async def multiply_by_two(value: int) -> int:
        await asyncio.sleep(0.01)
        return value * 2

    @reg.actions.register("failing_step")
    def failing_step():
        raise RuntimeError("Step failed")

    @reg.actions.register("create_data")
    def create_data():
        return {"items": [1, 2, 3], "metadata": {"count": 3}}

    @reg.actions.register("transform_data")
    def transform_data(d: dict) -> dict:
        return {
            "items": [x * 2 for x in d["items"]],
            "metadata": {**d["metadata"], "transformed": True},
        }

    @reg.actions.register("identity")
    def identity(x):
        return x

    @reg.actions.register("combine")
    def combine(r1: str, r2: str) -> str:
        return f"{r1}-{r2}"

    @reg.actions.register("add_ten")
    def add_ten(x: int) -> int:
        return x + 10

    @reg.actions.register("add_one")
    def add_one(x: int) -> int:
        return x + 1

    @reg.actions.register("create_code_data")
    def create_code_data():
        return {"code": "def foo(): pass"}

    # Register mock agents as instances (agent registry expects instances, not classes)
    from maverick.agents.base import MaverickAgent

    class MockReviewAgent(MaverickAgent):
        """Mock agent for testing."""

        def __init__(self):
            super().__init__(
                name="mock-reviewer",
                model="test",
                system_prompt="Test reviewer",
                allowed_tools=[],
            )

        async def execute(self, context: dict) -> dict:
            return {
                "review": f"Reviewed {len(context.get('files', []))} files",
                "approved": True,
            }

    class MockAgent(MaverickAgent):
        def __init__(self):
            super().__init__(
                name="mock-agent",
                model="test",
                system_prompt="Test agent",
                allowed_tools=[],
            )

        async def execute(self, context: dict) -> str:
            return f"Processed: {context.get('data', '')}"

    class AnalyzerAgent(MaverickAgent):
        def __init__(self):
            super().__init__(
                name="analyzer",
                model="test",
                system_prompt="Analyzer",
                allowed_tools=[],
            )

        async def execute(self, context: dict) -> dict:
            return {"analysis": f"Found {len(context['code'])} chars"}

    class FailingAgent(MaverickAgent):
        def __init__(self):
            super().__init__(
                name="failing-agent",
                model="test",
                system_prompt="Failing agent",
                allowed_tools=[],
            )

        async def execute(self, context: dict) -> None:
            raise RuntimeError("Agent execution failed")

    reg.agents.register("mock_reviewer", MockReviewAgent)
    reg.agents.register("mock_agent", MockAgent)
    reg.agents.register("analyzer", AnalyzerAgent)
    reg.agents.register("failing_agent", FailingAgent)

    # Register mock generators
    from maverick.agents.generators.base import GeneratorAgent

    class MockGenerator(GeneratorAgent):
        def __init__(self):
            super().__init__(
                name="mock-generator",
                model="test",
                system_prompt="Mock generator",
            )

        async def generate(self, context: dict) -> str:
            topic = context.get("topic", "unknown")
            return f"Generated content about {topic}"

    class SummaryGenerator(GeneratorAgent):
        def __init__(self):
            super().__init__(
                name="summarizer",
                model="test",
                system_prompt="Summarizer",
            )

        async def generate(self, context: dict) -> str:
            return f"Summary: {context['analysis']['analysis']}"

    reg.generators.register("mock_generator", MockGenerator)
    reg.generators.register("summarizer", SummaryGenerator)

    # Register context builders
    @reg.context_builders.register("parse_context_builder")
    async def parse_context_builder(inputs: dict, step_results: dict):
        # step_results format: {"step_name": {"output": value}}
        parse_result = step_results.get("parse", {})
        return {"data": parse_result.get("output")}

    return reg


class TestUserStory1TwoStepWorkflow:
    """Integration tests for User Story 1: Define and run a workflow."""

    @pytest.mark.asyncio
    async def test_two_step_workflow_execution(self, registry) -> None:
        """Test executing a workflow with two Python steps."""
        workflow = WorkflowFile(
            version="1.0",
            name="two-step-workflow",
            description="Process and format data",
            inputs={"input_data": {"type": "string"}},
            steps=[
                PythonStepRecord(
                    name="parse",
                    type=StepType.PYTHON,
                    action="str_upper",
                    kwargs={"s": "${{ inputs.input_data }}"},
                ),
                PythonStepRecord(
                    name="format",
                    type=StepType.PYTHON,
                    action="format_result",
                    kwargs={"x": "${{ steps.parse.output }}"},
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        events: list = []

        async for event in executor.execute(
            workflow, inputs={"input_data": "hello world"}
        ):
            events.append(event)

        # Verify event sequence (includes validation events at start)
        assert len(events) == 8

        # Validation events
        assert isinstance(events[0], ValidationStarted)
        assert isinstance(events[1], ValidationCompleted)

        assert isinstance(events[2], WorkflowStarted)
        assert events[2].workflow_name == "two-step-workflow"
        assert events[2].inputs == {"input_data": "hello world"}

        assert isinstance(events[3], StepStarted)
        assert events[3].step_name == "parse"
        assert events[3].step_type == StepType.PYTHON

        assert isinstance(events[4], StepCompleted)
        assert events[4].step_name == "parse"
        assert events[4].success is True

        assert isinstance(events[5], StepStarted)
        assert events[5].step_name == "format"

        assert isinstance(events[6], StepCompleted)
        assert events[6].step_name == "format"
        assert events[6].success is True

        assert isinstance(events[7], WorkflowCompleted)
        assert events[7].workflow_name == "two-step-workflow"
        assert events[7].success is True

        # Verify WorkflowResult
        result = executor.get_result()
        assert result.workflow_name == "two-step-workflow"
        assert result.success is True
        assert len(result.step_results) == 2

        assert result.step_results[0].name == "parse"
        assert result.step_results[0].output == "HELLO WORLD"

        assert result.step_results[1].name == "format"
        assert result.step_results[1].output == "Result: HELLO WORLD"

        assert result.final_output == "Result: HELLO WORLD"

    @pytest.mark.asyncio
    async def test_workflow_with_async_steps(self, registry) -> None:
        """Test workflow with async Python steps."""
        workflow = WorkflowFile(
            version="1.0",
            name="async-workflow",
            inputs={"start": {"type": "integer"}},
            steps=[
                PythonStepRecord(
                    name="double1",
                    type=StepType.PYTHON,
                    action="multiply_by_two",
                    kwargs={"value": "${{ inputs.start }}"},
                ),
                PythonStepRecord(
                    name="double2",
                    type=StepType.PYTHON,
                    action="multiply_by_two",
                    kwargs={"value": "${{ steps.double1.output }}"},
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow, inputs={"start": 5}):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == 20  # 5 * 2 * 2

    @pytest.mark.asyncio
    async def test_workflow_step_failure_propagation(self, registry) -> None:
        """Test that step failures are properly captured and propagated."""

        @registry.actions.register("ok_action")
        def ok_action():
            return "ok"

        @registry.actions.register("never_action")
        def never_action():
            return "never"

        workflow = WorkflowFile(
            version="1.0",
            name="failing-workflow",
            steps=[
                PythonStepRecord(
                    name="good-step",
                    type=StepType.PYTHON,
                    action="ok_action",
                    kwargs={},
                ),
                PythonStepRecord(
                    name="bad-step",
                    type=StepType.PYTHON,
                    action="failing_step",
                    kwargs={},
                ),
                PythonStepRecord(
                    name="never-runs",
                    type=StepType.PYTHON,
                    action="never_action",
                    kwargs={},
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        events = []

        async for event in executor.execute(workflow):
            events.append(event)

        result = executor.get_result()
        assert result.success is False
        assert result.failed_step is not None
        assert result.failed_step.name == "bad-step"
        assert "Step failed" in result.failed_step.error

        assert len(result.step_results) == 2

        assert isinstance(events[-1], WorkflowCompleted)
        assert events[-1].success is False

    @pytest.mark.asyncio
    async def test_workflow_with_complex_data_types(self, registry) -> None:
        """Test workflow with complex data structures passed between steps."""
        workflow = WorkflowFile(
            version="1.0",
            name="complex-data-workflow",
            steps=[
                PythonStepRecord(
                    name="create",
                    type=StepType.PYTHON,
                    action="create_data",
                    kwargs={},
                ),
                PythonStepRecord(
                    name="transform",
                    type=StepType.PYTHON,
                    action="transform_data",
                    kwargs={"d": "${{ steps.create.output }}"},
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == {
            "items": [2, 4, 6],
            "metadata": {"count": 3, "transformed": True},
        }

    @pytest.mark.asyncio
    async def test_workflow_serialization(self, registry) -> None:
        """Test that WorkflowResult can be serialized to dict."""

        @registry.actions.register("done_action")
        def done_action():
            return "done"

        workflow = WorkflowFile(
            version="1.0",
            name="serialization-test",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="done_action",
                    kwargs={},
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        result_dict = result.to_dict()

        assert result_dict["workflow_name"] == "serialization-test"
        assert result_dict["success"] is True
        assert len(result_dict["step_results"]) == 1
        assert result_dict["step_results"][0]["name"] == "step1"
        assert result_dict["final_output"] == "done"


class TestUserStory2AgentWorkflow:
    """Integration tests for User Story 2: Invoke agents with context."""

    @pytest.mark.asyncio
    async def test_agent_step_with_static_context(self, registry) -> None:
        """Test workflow with agent step using static context."""
        workflow = WorkflowFile(
            version="1.0",
            name="agent-workflow",
            steps=[
                AgentStepRecord(
                    name="review",
                    type=StepType.AGENT,
                    agent="mock_reviewer",
                    context={"files": ["main.py", "utils.py"]},
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        events = []

        async for event in executor.execute(workflow):
            events.append(event)

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == {
            "review": "Reviewed 2 files",
            "approved": True,
        }

        step_started = [e for e in events if isinstance(e, StepStarted)][0]
        assert step_started.step_type == StepType.AGENT

    @pytest.mark.asyncio
    async def test_agent_step_with_callable_context(self, registry) -> None:
        """Test workflow with agent step using callable context builder."""
        workflow = WorkflowFile(
            version="1.0",
            name="context-builder-workflow",
            inputs={"input_text": {"type": "string"}},
            steps=[
                PythonStepRecord(
                    name="parse",
                    type=StepType.PYTHON,
                    action="str_upper",
                    kwargs={"s": "${{ inputs.input_text }}"},
                ),
                AgentStepRecord(
                    name="process",
                    type=StepType.AGENT,
                    agent="mock_agent",
                    context="parse_context_builder",
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow, inputs={"input_text": "hello"}):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == "Processed: HELLO"

    @pytest.mark.asyncio
    async def test_generate_step_execution(self, registry) -> None:
        """Test workflow with generate step."""
        workflow = WorkflowFile(
            version="1.0",
            name="generate-workflow",
            steps=[
                GenerateStepRecord(
                    name="generate",
                    type=StepType.GENERATE,
                    generator="mock_generator",
                    context={"topic": "Python DSLs"},
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        events = []

        async for event in executor.execute(workflow):
            events.append(event)

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == "Generated content about Python DSLs"

        step_started = [e for e in events if isinstance(e, StepStarted)][0]
        assert step_started.step_type == StepType.GENERATE

    @pytest.mark.asyncio
    async def test_mixed_step_types_workflow(self, registry) -> None:
        """Test workflow combining Python, agent, and generate steps."""
        workflow = WorkflowFile(
            version="1.0",
            name="mixed-workflow",
            inputs={"code": {"type": "string"}},
            steps=[
                PythonStepRecord(
                    name="preprocess",
                    type=StepType.PYTHON,
                    action="str_strip",
                    kwargs={"s": "${{ inputs.code }}"},
                ),
                AgentStepRecord(
                    name="analyze",
                    type=StepType.AGENT,
                    agent="analyzer",
                    context={"code": "${{ steps.preprocess.output }}"},
                ),
                GenerateStepRecord(
                    name="summarize",
                    type=StepType.GENERATE,
                    generator="summarizer",
                    context={"analysis": "${{ steps.analyze.output }}"},
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(
            workflow, inputs={"code": "  def foo(): pass  "}
        ):
            pass

        result = executor.get_result()
        assert result.success is True
        # Final output is the last step (summarize)
        assert result.final_output == "Summary: Found 15 chars"

    @pytest.mark.asyncio
    async def test_agent_failure_handling(self, registry) -> None:
        """Test workflow handles agent step failure gracefully."""
        workflow = WorkflowFile(
            version="1.0",
            name="failing-agent-workflow",
            steps=[
                AgentStepRecord(
                    name="will-fail",
                    type=StepType.AGENT,
                    agent="failing_agent",
                    context={},
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is False
        assert result.failed_step is not None
        assert result.failed_step.name == "will-fail"
        assert "Agent execution failed" in result.failed_step.error


class TestUserStory3ValidateWorkflow:
    """Integration tests for User Story 3: Validate with retry and fix."""

    @pytest.fixture
    def mock_validation_runner(self):
        """Mock ValidationRunner to return success without running real commands."""
        from unittest.mock import AsyncMock, patch

        from maverick.runners.models import StageResult, ValidationOutput

        mock_output = ValidationOutput(
            success=True,
            stages=(
                StageResult(
                    stage_name="format",
                    passed=True,
                    output="OK",
                    duration_ms=10,
                    fix_attempts=0,
                    errors=(),
                ),
                StageResult(
                    stage_name="lint",
                    passed=True,
                    output="OK",
                    duration_ms=10,
                    fix_attempts=0,
                    errors=(),
                ),
            ),
            total_duration_ms=20,
        )

        mock_runner = AsyncMock()
        mock_runner.run.return_value = mock_output

        with patch(
            "maverick.dsl.serialization.executor.handlers.validate_step.ValidationRunner",
            return_value=mock_runner,
        ):
            yield mock_runner

    @pytest.mark.asyncio
    async def test_validate_step_passes_first_try(self, registry) -> None:
        """Test validation that passes on first attempt."""

        @registry.actions.register("process_value")
        def process_value():
            return {"value": 42}

        workflow = WorkflowFile(
            version="1.0",
            name="validate-workflow",
            steps=[
                PythonStepRecord(
                    name="process",
                    type=StepType.PYTHON,
                    action="process_value",
                    kwargs={},
                ),
                ValidateStepRecord(
                    name="validate",
                    type=StepType.VALIDATE,
                    stages=["format", "lint"],
                    retry=2,
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        # Without config, validation passes by default
        assert result.success is True

    @pytest.mark.asyncio
    async def test_subworkflow_step_execution(self, registry) -> None:
        """Test executing a sub-workflow."""
        # Create helper workflow
        helper_workflow = WorkflowFile(
            version="1.0",
            name="helper-workflow",
            inputs={"multiplier": {"type": "integer"}},
            steps=[
                PythonStepRecord(
                    name="multiply",
                    type=StepType.PYTHON,
                    action="multiply_by_two",
                    kwargs={"value": "${{ inputs.multiplier }}"},
                )
            ],
        )
        registry.workflows.register("helper_workflow", helper_workflow)

        # Main workflow
        workflow = WorkflowFile(
            version="1.0",
            name="main-workflow",
            inputs={"input_value": {"type": "integer"}},
            steps=[
                SubWorkflowStepRecord(
                    name="run_helper",
                    type=StepType.SUBWORKFLOW,
                    workflow="helper_workflow",
                    inputs={"multiplier": "${{ inputs.input_value }}"},
                ),
                PythonStepRecord(
                    name="finalize",
                    type=StepType.PYTHON,
                    action="add_ten",
                    kwargs={"x": "${{ steps.run_helper.output }}"},
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        events = []

        async for event in executor.execute(workflow, inputs={"input_value": 5}):
            events.append(event)

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == 20  # (5 * 2) + 10

        step_started = [e for e in events if isinstance(e, StepStarted)]
        assert any(e.step_type == StepType.SUBWORKFLOW for e in step_started)

    @pytest.mark.asyncio
    async def test_nested_subworkflows(self, registry) -> None:
        """Test nested sub-workflow execution."""
        # Inner workflow
        inner_workflow = WorkflowFile(
            version="1.0",
            name="inner-workflow",
            inputs={"value": {"type": "integer"}},
            steps=[
                PythonStepRecord(
                    name="inner_step",
                    type=StepType.PYTHON,
                    action="add_one",
                    kwargs={"x": "${{ inputs.value }}"},
                )
            ],
        )
        registry.workflows.register("inner_workflow", inner_workflow)

        # Middle workflow
        middle_workflow = WorkflowFile(
            version="1.0",
            name="middle-workflow",
            inputs={"value": {"type": "integer"}},
            steps=[
                SubWorkflowStepRecord(
                    name="call_inner",
                    type=StepType.SUBWORKFLOW,
                    workflow="inner_workflow",
                    inputs={"value": "${{ inputs.value }}"},
                ),
                PythonStepRecord(
                    name="add_ten",
                    type=StepType.PYTHON,
                    action="add_ten",
                    kwargs={"x": "${{ steps.call_inner.output }}"},
                ),
            ],
        )
        registry.workflows.register("middle_workflow", middle_workflow)

        # Outer workflow
        outer_workflow = WorkflowFile(
            version="1.0",
            name="outer-workflow",
            inputs={"start": {"type": "integer"}},
            steps=[
                SubWorkflowStepRecord(
                    name="call_middle",
                    type=StepType.SUBWORKFLOW,
                    workflow="middle_workflow",
                    inputs={"value": "${{ inputs.start }}"},
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(outer_workflow, inputs={"start": 5}):
            pass

        result = executor.get_result()
        assert result.success is True
        # 5 + 1 (inner) + 10 (middle) = 16
        assert result.final_output == 16

    @pytest.mark.asyncio
    async def test_subworkflow_failure_propagation(self, registry) -> None:
        """Test that sub-workflow failures propagate correctly."""
        # Failing sub-workflow
        failing_sub = WorkflowFile(
            version="1.0",
            name="failing-sub",
            steps=[
                PythonStepRecord(
                    name="fail",
                    type=StepType.PYTHON,
                    action="failing_step",
                    kwargs={},
                )
            ],
        )
        registry.workflows.register("failing_sub", failing_sub)

        @registry.actions.register("ok_step_action")
        def ok_step_action():
            return "ok"

        @registry.actions.register("never_step_action")
        def never_step_action():
            return "never"

        # Parent workflow
        parent_workflow = WorkflowFile(
            version="1.0",
            name="parent-workflow",
            steps=[
                PythonStepRecord(
                    name="ok_step",
                    type=StepType.PYTHON,
                    action="ok_step_action",
                    kwargs={},
                ),
                SubWorkflowStepRecord(
                    name="call_failing",
                    type=StepType.SUBWORKFLOW,
                    workflow="failing_sub",
                ),
                PythonStepRecord(
                    name="never_runs",
                    type=StepType.PYTHON,
                    action="never_step_action",
                    kwargs={},
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(parent_workflow):
            pass

        result = executor.get_result()
        assert result.success is False
        assert result.failed_step is not None
        assert result.failed_step.name == "call_failing"

    @pytest.mark.asyncio
    async def test_validate_and_subworkflow_combined(
        self, registry, mock_validation_runner
    ) -> None:
        """Test workflow combining validation and sub-workflows."""

        @registry.actions.register("auto_fix_action")
        def auto_fix_action():
            return "fixed"

        # Fix workflow
        fix_workflow = WorkflowFile(
            version="1.0",
            name="fix-workflow",
            steps=[
                PythonStepRecord(
                    name="auto_fix",
                    type=StepType.PYTHON,
                    action="auto_fix_action",
                    kwargs={},
                )
            ],
        )
        registry.workflows.register("fix_workflow", fix_workflow)

        # Complex workflow
        complex_workflow = WorkflowFile(
            version="1.0",
            name="complex-workflow",
            steps=[
                PythonStepRecord(
                    name="process",
                    type=StepType.PYTHON,
                    action="create_code_data",
                    kwargs={},
                ),
                SubWorkflowStepRecord(
                    name="helper",
                    type=StepType.SUBWORKFLOW,
                    workflow="fix_workflow",
                ),
                ValidateStepRecord(
                    name="validate",
                    type=StepType.VALIDATE,
                    stages=["lint"],
                    retry=1,
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(complex_workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        # Final output is last step (validate), which returns success=True
        # ValidationResult is converted to dict for expression evaluation compatibility
        assert result.final_output["success"] is True


class TestEdgeCases:
    """Integration tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_context_builder_failure_stops_workflow(self, registry) -> None:
        """Test that context builder failure returns failed StepResult."""

        @registry.actions.register("ok_first")
        def ok_first():
            return "ok"

        @registry.actions.register("never_runs_action")
        def never_runs_action():
            return "never"

        @registry.context_builders.register("failing_context_builder")
        async def failing_context_builder(inputs: dict, step_results: dict):
            raise RuntimeError("Context builder intentionally failed")

        workflow = WorkflowFile(
            version="1.0",
            name="context-builder-failure-workflow",
            steps=[
                PythonStepRecord(
                    name="first",
                    type=StepType.PYTHON,
                    action="ok_first",
                    kwargs={},
                ),
                AgentStepRecord(
                    name="agent-with-failing-context",
                    type=StepType.AGENT,
                    agent="mock_agent",
                    context="failing_context_builder",
                ),
                PythonStepRecord(
                    name="never-runs",
                    type=StepType.PYTHON,
                    action="never_runs_action",
                    kwargs={},
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        events = []

        async for event in executor.execute(workflow):
            events.append(event)

        result = executor.get_result()

        assert result.success is False
        assert result.failed_step is not None
        assert result.failed_step.name == "agent-with-failing-context"
        assert "Context builder" in result.failed_step.error

        assert len(result.step_results) == 2
        assert result.step_results[0].success is True
        assert result.step_results[1].success is False

        assert isinstance(events[-1], WorkflowCompleted)
        assert events[-1].success is False

    @pytest.mark.asyncio
    async def test_executor_get_result_before_execution(self) -> None:
        """Test that get_result() raises error if called before execution."""
        executor = WorkflowFileExecutor()

        with pytest.raises(RuntimeError, match="has not been executed"):
            executor.get_result()

    @pytest.mark.asyncio
    async def test_workflow_cancellation(self, registry) -> None:
        """Test that calling cancel() stops workflow at next boundary."""
        call_count = {"value": 0}

        @registry.actions.register("track_calls")
        def track_calls() -> str:
            call_count["value"] += 1
            return f"step-{call_count['value']}"

        workflow = WorkflowFile(
            version="1.0",
            name="cancellable-workflow",
            steps=[
                PythonStepRecord(
                    name="step1",
                    type=StepType.PYTHON,
                    action="track_calls",
                    kwargs={},
                ),
                PythonStepRecord(
                    name="step2",
                    type=StepType.PYTHON,
                    action="track_calls",
                    kwargs={},
                ),
                PythonStepRecord(
                    name="step3",
                    type=StepType.PYTHON,
                    action="track_calls",
                    kwargs={},
                ),
                PythonStepRecord(
                    name="step4",
                    type=StepType.PYTHON,
                    action="track_calls",
                    kwargs={},
                ),
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        events = []
        step_count = 0

        async for event in executor.execute(workflow):
            events.append(event)
            if isinstance(event, StepCompleted):
                step_count += 1
                if step_count == 2:
                    executor.cancel()

        result = executor.get_result()

        assert result.success is False

        assert len(result.step_results) == 2
        assert result.step_results[0].name == "step1"
        assert result.step_results[1].name == "step2"
        assert call_count["value"] == 2

        workflow_completed_events = [
            e for e in events if isinstance(e, WorkflowCompleted)
        ]
        assert len(workflow_completed_events) == 1
        assert workflow_completed_events[0].success is False
