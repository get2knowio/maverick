"""Integration tests for workflow execution.

These tests verify end-to-end workflow execution with the DSL,
testing real-world scenarios across multiple user stories.
"""

from __future__ import annotations

import pytest

from maverick.dsl import (
    workflow,
    step,
    WorkflowEngine,
    WorkflowStarted,
    StepStarted,
    StepCompleted,
    WorkflowCompleted,
    StepType,
)
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.results import StepResult


class TestUserStory1TwoStepWorkflow:
    """Integration tests for User Story 1: Define and run a workflow."""

    @pytest.mark.asyncio
    async def test_two_step_workflow_execution(self) -> None:
        """Test executing a workflow with two Python steps.

        This is the canonical User Story 1 integration test that verifies:
        - Workflow definition with @workflow decorator
        - Step creation with step().python() builder
        - Step output passing between steps
        - Final output from explicit return
        - Progress event emission
        - WorkflowResult correctness
        """

        @workflow(name="two-step-workflow", description="Process and format data")
        def two_step_workflow(input_data: str) -> dict[str, str]:
            """A simple two-step workflow."""
            # Step 1: Parse and uppercase
            parsed = yield step("parse").python(
                action=str.upper,
                args=(input_data,),
            )

            # Step 2: Format the result
            formatted = yield step("format").python(
                action=lambda x: f"Result: {x}",
                args=(parsed,),
            )

            return {"output": formatted, "original": input_data}

        engine = WorkflowEngine()
        events: list = []

        # Execute workflow
        async for event in engine.execute(two_step_workflow, input_data="hello world"):
            events.append(event)

        # Verify event sequence
        assert len(events) == 6  # Started + 2*(StepStarted + StepCompleted) + Completed

        # Verify WorkflowStarted
        assert isinstance(events[0], WorkflowStarted)
        assert events[0].workflow_name == "two-step-workflow"
        assert events[0].inputs == {"input_data": "hello world"}

        # Verify Step 1 events
        assert isinstance(events[1], StepStarted)
        assert events[1].step_name == "parse"
        assert events[1].step_type == StepType.PYTHON

        assert isinstance(events[2], StepCompleted)
        assert events[2].step_name == "parse"
        assert events[2].success is True

        # Verify Step 2 events
        assert isinstance(events[3], StepStarted)
        assert events[3].step_name == "format"

        assert isinstance(events[4], StepCompleted)
        assert events[4].step_name == "format"
        assert events[4].success is True

        # Verify WorkflowCompleted
        assert isinstance(events[5], WorkflowCompleted)
        assert events[5].workflow_name == "two-step-workflow"
        assert events[5].success is True

        # Verify WorkflowResult
        result = engine.get_result()
        assert result.workflow_name == "two-step-workflow"
        assert result.success is True
        assert len(result.step_results) == 2

        # Verify step results
        assert result.step_results[0].name == "parse"
        assert result.step_results[0].output == "HELLO WORLD"

        assert result.step_results[1].name == "format"
        assert result.step_results[1].output == "Result: HELLO WORLD"

        # Verify final output
        assert result.final_output == {
            "output": "Result: HELLO WORLD",
            "original": "hello world",
        }

    @pytest.mark.asyncio
    async def test_workflow_with_async_steps(self) -> None:
        """Test workflow with async Python steps."""
        import asyncio

        async def async_process(value: int) -> int:
            await asyncio.sleep(0.01)
            return value * 2

        @workflow(name="async-workflow")
        def async_workflow(start: int) -> int:
            result1 = yield step("double1").python(action=async_process, args=(start,))
            result2 = yield step("double2").python(action=async_process, args=(result1,))
            return result2

        engine = WorkflowEngine()

        async for _ in engine.execute(async_workflow, start=5):
            pass

        result = engine.get_result()
        assert result.success is True
        assert result.final_output == 20  # 5 * 2 * 2

    @pytest.mark.asyncio
    async def test_workflow_step_failure_propagation(self) -> None:
        """Test that step failures are properly captured and propagated."""

        def failing_step() -> None:
            raise ValueError("Intentional failure")

        @workflow(name="failing-workflow")
        def failing_workflow() -> None:
            yield step("good-step").python(action=lambda: "ok")
            yield step("bad-step").python(action=failing_step)
            yield step("never-runs").python(action=lambda: "never")

        engine = WorkflowEngine()
        events = []

        async for event in engine.execute(failing_workflow):
            events.append(event)

        # Workflow should complete (not raise) but with failure status
        result = engine.get_result()
        assert result.success is False
        assert result.failed_step is not None
        assert result.failed_step.name == "bad-step"
        assert "ValueError" in result.failed_step.error

        # Only 2 steps should have executed (good-step and bad-step)
        assert len(result.step_results) == 2

        # Verify final event indicates failure
        assert isinstance(events[-1], WorkflowCompleted)
        assert events[-1].success is False

    @pytest.mark.asyncio
    async def test_workflow_with_complex_data_types(self) -> None:
        """Test workflow with complex data structures passed between steps."""

        @workflow(name="complex-data-workflow")
        def complex_workflow() -> dict:
            # Step 1: Create initial structure
            data = yield step("create").python(
                action=lambda: {"items": [1, 2, 3], "metadata": {"count": 3}}
            )

            # Step 2: Transform
            transformed = yield step("transform").python(
                action=lambda d: {
                    "items": [x * 2 for x in d["items"]],
                    "metadata": {**d["metadata"], "transformed": True},
                },
                args=(data,),
            )

            return transformed

        engine = WorkflowEngine()

        async for _ in engine.execute(complex_workflow):
            pass

        result = engine.get_result()
        assert result.success is True
        assert result.final_output == {
            "items": [2, 4, 6],
            "metadata": {"count": 3, "transformed": True},
        }

    @pytest.mark.asyncio
    async def test_workflow_serialization(self) -> None:
        """Test that WorkflowResult can be serialized to dict."""

        @workflow(name="serialization-test")
        def simple_workflow() -> str:
            yield step("step1").python(action=lambda: "done")
            return "complete"

        engine = WorkflowEngine()

        async for _ in engine.execute(simple_workflow):
            pass

        result = engine.get_result()
        result_dict = result.to_dict()

        assert result_dict["workflow_name"] == "serialization-test"
        assert result_dict["success"] is True
        assert len(result_dict["step_results"]) == 1
        assert result_dict["step_results"][0]["name"] == "step1"
        assert result_dict["final_output"] == "complete"


class TestUserStory2AgentWorkflow:
    """Integration tests for User Story 2: Invoke agents with context."""

    @pytest.mark.asyncio
    async def test_agent_step_with_static_context(self) -> None:
        """Test workflow with agent step using static context."""

        class MockReviewAgent:
            """Mock agent for testing."""

            name = "mock-reviewer"

            async def execute(self, context: dict) -> dict:
                return {
                    "review": f"Reviewed {len(context.get('files', []))} files",
                    "approved": True,
                }

        @workflow(name="agent-workflow")
        def agent_workflow() -> dict:
            review = yield step("review").agent(
                agent=MockReviewAgent(),
                context={"files": ["main.py", "utils.py"]},
            )
            return review

        engine = WorkflowEngine()
        events = []

        async for event in engine.execute(agent_workflow):
            events.append(event)

        result = engine.get_result()
        assert result.success is True
        assert result.final_output == {
            "review": "Reviewed 2 files",
            "approved": True,
        }

        # Verify step type
        step_started = [e for e in events if isinstance(e, StepStarted)][0]
        assert step_started.step_type == StepType.AGENT

    @pytest.mark.asyncio
    async def test_agent_step_with_callable_context(self) -> None:
        """Test workflow with agent step using callable context builder."""

        class MockAgent:
            name = "mock-agent"

            async def execute(self, context: dict) -> str:
                return f"Processed: {context.get('data', '')}"

        @workflow(name="context-builder-workflow")
        def context_builder_workflow(input_text: str) -> str:
            # First step produces data
            parsed = yield step("parse").python(
                action=str.upper,
                args=(input_text,),
            )

            # Agent step uses context builder to access prior step
            async def build_context(ctx):
                return {"data": ctx.get_step_output("parse")}

            result = yield step("process").agent(
                agent=MockAgent(),
                context=build_context,
            )

            return result

        engine = WorkflowEngine()

        async for _ in engine.execute(context_builder_workflow, input_text="hello"):
            pass

        result = engine.get_result()
        assert result.success is True
        assert result.final_output == "Processed: HELLO"

    @pytest.mark.asyncio
    async def test_generate_step_execution(self) -> None:
        """Test workflow with generate step."""

        class MockGenerator:
            name = "mock-generator"

            async def generate(self, context: dict) -> str:
                topic = context.get("topic", "unknown")
                return f"Generated content about {topic}"

        @workflow(name="generate-workflow")
        def generate_workflow() -> str:
            text = yield step("generate").generate(
                generator=MockGenerator(),
                context={"topic": "Python DSLs"},
            )
            return text

        engine = WorkflowEngine()
        events = []

        async for event in engine.execute(generate_workflow):
            events.append(event)

        result = engine.get_result()
        assert result.success is True
        assert result.final_output == "Generated content about Python DSLs"

        # Verify step type
        step_started = [e for e in events if isinstance(e, StepStarted)][0]
        assert step_started.step_type == StepType.GENERATE

    @pytest.mark.asyncio
    async def test_mixed_step_types_workflow(self) -> None:
        """Test workflow combining Python, agent, and generate steps."""

        class AnalyzerAgent:
            name = "analyzer"

            async def execute(self, context: dict) -> dict:
                return {"analysis": f"Found {len(context['code'])} chars"}

        class SummaryGenerator:
            name = "summarizer"

            async def generate(self, context: dict) -> str:
                return f"Summary: {context['analysis']['analysis']}"

        @workflow(name="mixed-workflow")
        def mixed_workflow(code: str) -> dict:
            # Python step: preprocess
            processed = yield step("preprocess").python(
                action=str.strip,
                args=(code,),
            )

            # Agent step: analyze
            analysis = yield step("analyze").agent(
                agent=AnalyzerAgent(),
                context={"code": processed},
            )

            # Generate step: summarize
            summary = yield step("summarize").generate(
                generator=SummaryGenerator(),
                context={"analysis": analysis},
            )

            return {"code": processed, "analysis": analysis, "summary": summary}

        engine = WorkflowEngine()

        async for _ in engine.execute(mixed_workflow, code="  def foo(): pass  "):
            pass

        result = engine.get_result()
        assert result.success is True
        assert result.final_output["code"] == "def foo(): pass"
        assert result.final_output["analysis"] == {"analysis": "Found 15 chars"}
        assert result.final_output["summary"] == "Summary: Found 15 chars"

    @pytest.mark.asyncio
    async def test_agent_failure_handling(self) -> None:
        """Test workflow handles agent step failure gracefully."""

        class FailingAgent:
            name = "failing-agent"

            async def execute(self, context: dict) -> None:
                raise RuntimeError("Agent execution failed")

        @workflow(name="failing-agent-workflow")
        def failing_agent_workflow() -> None:
            yield step("will-fail").agent(
                agent=FailingAgent(),
                context={},
            )

        engine = WorkflowEngine()

        async for _ in engine.execute(failing_agent_workflow):
            pass

        result = engine.get_result()
        assert result.success is False
        assert result.failed_step is not None
        assert result.failed_step.name == "will-fail"
        assert "RuntimeError" in result.failed_step.error


class TestUserStory3ValidateWorkflow:
    """Integration tests for User Story 3: Validate with retry and fix."""

    @pytest.mark.asyncio
    async def test_validate_step_passes_first_try(self) -> None:
        """Test validation that passes on first attempt."""

        class MockConfig:
            validation_stages = ["format", "lint"]
            call_count = 0

            async def run_validation_stages(self, stages: list[str]):
                self.call_count += 1
                return type("Result", (), {"success": True, "stages": stages})()

        config = MockConfig()

        @workflow(name="validate-workflow")
        def validate_workflow() -> dict:
            # First do some work
            data = yield step("process").python(action=lambda: {"value": 42})

            # Then validate
            result = yield step("validate").validate(
                stages=["format", "lint"],
                retry=2,
            )

            return {"data": data, "validated": result.success}

        from maverick.dsl import WorkflowContext

        engine = WorkflowEngine()

        # We need to inject the config into the context
        # For now, test that the step structure is correct
        async for _ in engine.execute(validate_workflow):
            pass

        result = engine.get_result()
        # Without config, validation passes by default
        assert result.success is True

    @pytest.mark.asyncio
    async def test_subworkflow_step_execution(self) -> None:
        """Test executing a sub-workflow."""

        @workflow(name="helper-workflow")
        def helper_workflow(multiplier: int) -> int:
            result = yield step("multiply").python(
                action=lambda x: x * 2,
                args=(multiplier,),
            )
            return result

        @workflow(name="main-workflow")
        def main_workflow(input_value: int) -> dict:
            # Run a sub-workflow
            sub_result = yield step("run-helper").subworkflow(
                workflow=helper_workflow,
                inputs={"multiplier": input_value},
            )

            # Continue with main workflow
            final = yield step("finalize").python(
                action=lambda x: x + 10,
                args=(sub_result.final_output,),
            )

            return {"sub_result": sub_result.final_output, "final": final}

        engine = WorkflowEngine()
        events = []

        async for event in engine.execute(main_workflow, input_value=5):
            events.append(event)

        result = engine.get_result()
        assert result.success is True
        assert result.final_output["sub_result"] == 10  # 5 * 2
        assert result.final_output["final"] == 20  # 10 + 10

        # Verify step type
        step_started = [e for e in events if isinstance(e, StepStarted)]
        assert any(e.step_type == StepType.SUBWORKFLOW for e in step_started)

    @pytest.mark.asyncio
    async def test_nested_subworkflows(self) -> None:
        """Test nested sub-workflow execution."""

        @workflow(name="inner-workflow")
        def inner_workflow(value: int) -> int:
            result = yield step("inner-step").python(
                action=lambda x: x + 1,
                args=(value,),
            )
            return result

        @workflow(name="middle-workflow")
        def middle_workflow(value: int) -> int:
            result = yield step("call-inner").subworkflow(
                workflow=inner_workflow,
                inputs={"value": value},
            )
            return result.final_output + 10

        @workflow(name="outer-workflow")
        def outer_workflow(start: int) -> int:
            result = yield step("call-middle").subworkflow(
                workflow=middle_workflow,
                inputs={"value": start},
            )
            return result.final_output

        engine = WorkflowEngine()

        async for _ in engine.execute(outer_workflow, start=5):
            pass

        result = engine.get_result()
        assert result.success is True
        # 5 + 1 (inner) + 10 (middle) = 16
        assert result.final_output == 16

    @pytest.mark.asyncio
    async def test_subworkflow_failure_propagation(self) -> None:
        """Test that sub-workflow failures propagate correctly."""

        @workflow(name="failing-sub")
        def failing_sub() -> None:
            yield step("fail").python(action=lambda: (_ for _ in ()).throw(ValueError("boom")))

        @workflow(name="parent-workflow")
        def parent_workflow() -> str:
            yield step("ok-step").python(action=lambda: "ok")
            yield step("call-failing").subworkflow(workflow=failing_sub)
            yield step("never-runs").python(action=lambda: "never")
            return "done"

        engine = WorkflowEngine()

        async for _ in engine.execute(parent_workflow):
            pass

        result = engine.get_result()
        assert result.success is False
        assert result.failed_step is not None
        assert result.failed_step.name == "call-failing"

    @pytest.mark.asyncio
    async def test_validate_and_subworkflow_combined(self) -> None:
        """Test workflow combining validation and sub-workflows."""

        @workflow(name="fix-workflow")
        def fix_workflow() -> str:
            yield step("auto-fix").python(action=lambda: "fixed")
            return "applied"

        @workflow(name="complex-workflow")
        def complex_workflow() -> dict:
            # Process data
            data = yield step("process").python(
                action=lambda: {"code": "def foo(): pass"},
            )

            # Run a helper sub-workflow
            helper_result = yield step("helper").subworkflow(
                workflow=fix_workflow,
            )

            # Validate (will pass by default without config)
            validate_result = yield step("validate").validate(
                stages=["lint"],
                retry=1,
            )

            return {
                "data": data,
                "helper": helper_result.final_output,
                "validated": validate_result.success,
            }

        engine = WorkflowEngine()

        async for _ in engine.execute(complex_workflow):
            pass

        result = engine.get_result()
        assert result.success is True
        assert result.final_output["data"] == {"code": "def foo(): pass"}
        assert result.final_output["helper"] == "applied"
        assert result.final_output["validated"] is True


class TestEdgeCases:
    """Integration tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_context_builder_failure_stops_workflow(self) -> None:
        """Test that context builder failure returns a failed StepResult and stops workflow."""

        class MockAgent:
            name = "mock-agent"

            async def execute(self, context: dict) -> str:
                return "should not reach here"

        async def failing_context_builder(ctx):
            """Context builder that raises an exception."""
            raise RuntimeError("Context builder intentionally failed")

        @workflow(name="context-builder-failure-workflow")
        def context_builder_failure_workflow() -> str:
            # First step succeeds
            step1 = yield step("first").python(action=lambda: "ok")

            # Second step has a failing context builder
            step2 = yield step("agent-with-failing-context").agent(
                agent=MockAgent(),
                context=failing_context_builder,
            )

            # This should never execute
            yield step("never-runs").python(action=lambda: "never")
            return "done"

        engine = WorkflowEngine()
        events = []

        async for event in engine.execute(context_builder_failure_workflow):
            events.append(event)

        result = engine.get_result()

        # Workflow should complete with failure
        assert result.success is False
        assert result.failed_step is not None
        assert result.failed_step.name == "agent-with-failing-context"
        assert "Context builder" in result.failed_step.error
        assert "RuntimeError" in result.failed_step.error

        # Only 2 steps should have executed (first + agent-with-failing-context)
        assert len(result.step_results) == 2
        assert result.step_results[0].success is True
        assert result.step_results[1].success is False

        # Final event should indicate failure
        assert isinstance(events[-1], WorkflowCompleted)
        assert events[-1].success is False

    @pytest.mark.asyncio
    async def test_validate_step_stages_not_found_returns_failed_result(self) -> None:
        """Test that validate step with non-existent stages config key returns failed result."""

        @workflow(name="validate-stages-not-found-workflow")
        def validate_workflow() -> str:
            # Try to validate with a non-existent config key
            result = yield step("validate").validate(
                stages="nonexistent_key",  # This key doesn't exist in config
                retry=1,
            )
            return "done"

        # Create engine with config that doesn't have "nonexistent_key"
        class MockConfig:
            validation_stages = ["format", "lint"]  # Has default, but not "nonexistent_key"

        engine = WorkflowEngine(config=MockConfig())
        events = []

        async for event in engine.execute(validate_workflow):
            events.append(event)

        result = engine.get_result()

        # Workflow should complete with failure
        assert result.success is False
        assert result.failed_step is not None
        assert result.failed_step.name == "validate"
        assert "nonexistent_key" in result.failed_step.error
        assert "not found" in result.failed_step.error.lower()

        # Only validate step should have executed
        assert len(result.step_results) == 1
        assert result.step_results[0].success is False

    @pytest.mark.asyncio
    async def test_engine_catches_step_execution_exception(self) -> None:
        """Test that engine catches unexpected exceptions from step.execute() and returns failed StepResult."""
        from dataclasses import dataclass, field

        @dataclass(frozen=True, slots=True)
        class BrokenStep(StepDefinition):
            """Mock step that raises an exception in execute()."""

            name: str = field(default="broken")
            step_type: StepType = field(default=StepType.PYTHON)

            async def execute(self, context) -> StepResult:
                """Raises an exception instead of returning StepResult."""
                raise ValueError("Step execute() raised an unexpected exception")

            def to_dict(self) -> dict:
                return {"name": self.name, "step_type": self.step_type.value}

        # We need to manually create a workflow that yields the broken step
        # Since the builder pattern creates specific step types, we'll use a direct generator
        def broken_workflow_func():
            yield step("before").python(action=lambda: "ok")
            yield BrokenStep()  # This will raise in execute()
            yield step("after").python(action=lambda: "never")
            return "done"

        # Create a workflow definition manually
        from maverick.dsl.decorator import WorkflowDefinition

        workflow_def = WorkflowDefinition(
            name="broken-step-workflow",
            description="Test broken step",
            parameters=(),  # No parameters
            func=broken_workflow_func,
        )

        # Attach to function
        broken_workflow_func.__workflow_def__ = workflow_def  # type: ignore[attr-defined]

        engine = WorkflowEngine()
        events = []

        async for event in engine.execute(broken_workflow_func):
            events.append(event)

        result = engine.get_result()

        # Workflow should complete with failure
        assert result.success is False
        assert result.failed_step is not None
        assert result.failed_step.name == "broken"
        assert "ValueError" in result.failed_step.error
        assert "unexpected exception" in result.failed_step.error

        # Only 2 steps should have executed (before + broken)
        assert len(result.step_results) == 2
        assert result.step_results[0].success is True
        assert result.step_results[1].success is False

    @pytest.mark.asyncio
    async def test_workflow_cancellation(self) -> None:
        """Test that calling cancel() stops workflow at next step boundary."""
        import asyncio

        call_count = 0

        def track_calls() -> str:
            nonlocal call_count
            call_count += 1
            return f"step-{call_count}"

        @workflow(name="cancellable-workflow")
        def cancellable_workflow() -> str:
            step1 = yield step("step1").python(action=track_calls)
            step2 = yield step("step2").python(action=track_calls)
            step3 = yield step("step3").python(action=track_calls)
            step4 = yield step("step4").python(action=track_calls)
            return "all done"

        engine = WorkflowEngine()
        events = []
        step_count = 0

        # Execute workflow and cancel after step 2 completes
        async for event in engine.execute(cancellable_workflow):
            events.append(event)
            if isinstance(event, StepCompleted):
                step_count += 1
                if step_count == 2:
                    # Cancel after step 2 completes
                    engine.cancel()

        result = engine.get_result()

        # Workflow should have stopped with failure status
        assert result.success is False

        # Should have executed exactly 2 steps (step1 and step2)
        assert len(result.step_results) == 2
        assert result.step_results[0].name == "step1"
        assert result.step_results[1].name == "step2"
        assert call_count == 2  # Only 2 steps executed

        # Workflow should have emitted WorkflowCompleted with success=False
        workflow_completed_events = [e for e in events if isinstance(e, WorkflowCompleted)]
        assert len(workflow_completed_events) == 1
        assert workflow_completed_events[0].success is False
