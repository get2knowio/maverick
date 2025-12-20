"""Unit tests for GenerateStep class.

This module tests the GenerateStep class that invokes a GeneratorAgent
to produce generated text within workflow execution.

TDD Note: These tests are written FIRST and will FAIL until implementation
is complete. They define the expected behavior of GenerateStep.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from maverick.dsl import StepResult, StepType, WorkflowContext
from maverick.dsl.steps.generate import GenerateStep


# Mock GeneratorAgent for testing
class MockGeneratorAgent:
    """Mock GeneratorAgent with a generate method."""

    def __init__(self, name: str = "mock-generator") -> None:
        """Initialize mock generator.

        Args:
            name: Generator name for identification.
        """
        self.name = name
        self.generate_called = False
        self.last_context: dict[str, Any] | None = None

    async def generate(self, context: dict[str, Any]) -> str:
        """Mock generate method that returns a string.

        Args:
            context: Generation context.

        Returns:
            Generated string.
        """
        self.generate_called = True
        self.last_context = context
        await asyncio.sleep(0.001)  # Simulate async work
        return f"Generated text with context: {context.get('prompt', 'no prompt')}"


class FailingGeneratorAgent:
    """Mock GeneratorAgent that always fails."""

    def __init__(self, name: str = "failing-generator") -> None:
        """Initialize failing generator.

        Args:
            name: Generator name for identification.
        """
        self.name = name

    async def generate(self, context: dict[str, Any]) -> str:
        """Mock generate method that always raises an exception.

        Args:
            context: Generation context (ignored).

        Raises:
            RuntimeError: Always raised to simulate failure.
        """
        await asyncio.sleep(0.001)
        raise RuntimeError("Generator failed to produce output")


class TestGenerateStepCreation:
    """Test GenerateStep instantiation and properties."""

    def test_creation_with_static_context(self) -> None:
        """Test creating GenerateStep with static dict context."""
        generator = MockGeneratorAgent()
        context = {"prompt": "Write a test", "max_tokens": 100}

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context=context,
        )

        assert step.name == "test-generate"
        assert step.generator is generator
        assert step.context == context
        assert step.step_type == StepType.GENERATE

    def test_creation_with_callable_context(self) -> None:
        """Test creating GenerateStep with callable context builder."""
        generator = MockGeneratorAgent()

        async def context_builder(ctx: WorkflowContext) -> dict[str, Any]:
            return {"prompt": f"Process {ctx.inputs.get('task', 'unknown')}"}

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context=context_builder,
        )

        assert step.name == "test-generate"
        assert step.generator is generator
        assert callable(step.context)
        assert step.context is context_builder
        assert step.step_type == StepType.GENERATE

    def test_step_type_is_always_generate(self) -> None:
        """Test that step_type is always StepType.GENERATE."""
        generator = MockGeneratorAgent()

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context={},
        )

        assert step.step_type == StepType.GENERATE

    def test_generate_step_is_frozen(self) -> None:
        """Test that GenerateStep is immutable (frozen=True)."""
        generator = MockGeneratorAgent()

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context={},
        )

        # Attempt to modify should raise error
        with pytest.raises((AttributeError, TypeError)):
            step.name = "modified"

    def test_generate_step_has_slots(self) -> None:
        """Test that GenerateStep declares __slots__ for memory efficiency."""
        # Dataclass with slots=True declares __slots__
        assert hasattr(GenerateStep, "__slots__")


class TestGenerateStepToDict:
    """Test GenerateStep.to_dict() serialization."""

    def test_to_dict_with_static_context(self) -> None:
        """Test to_dict() with static dict context."""
        generator = MockGeneratorAgent(name="commit-message-generator")

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context={"prompt": "Write commit message"},
        )

        result = step.to_dict()

        assert result["name"] == "test-generate"
        assert result["step_type"] == "generate"
        assert result["generator"] == "commit-message-generator"
        assert result["context_type"] == "static"

    def test_to_dict_with_callable_context(self) -> None:
        """Test to_dict() with callable context builder."""
        generator = MockGeneratorAgent(name="pr-body-generator")

        async def context_builder(ctx: WorkflowContext) -> dict[str, Any]:
            return {"data": "builder"}

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context=context_builder,
        )

        result = step.to_dict()

        assert result["name"] == "test-generate"
        assert result["step_type"] == "generate"
        assert result["generator"] == "pr-body-generator"
        assert result["context_type"] == "callable"

    def test_to_dict_with_generator_without_name(self) -> None:
        """Test to_dict() when generator has no name attribute."""

        class UnnamedGenerator:
            """Generator without a name attribute."""

            async def generate(self, context: dict[str, Any]) -> str:
                """Generate method."""
                return "output"

        generator = UnnamedGenerator()

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context={},
        )

        result = step.to_dict()

        assert result["generator"] == "UnnamedGenerator"


class TestGenerateStepExecuteWithStaticContext:
    """Test GenerateStep.execute() with static dict context."""

    @pytest.mark.asyncio
    async def test_execute_with_static_context_returns_step_result(self) -> None:
        """Test that execute() with static context returns StepResult."""
        generator = MockGeneratorAgent()
        context_dict = {"prompt": "Write a summary", "style": "formal"}

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context=context_dict,
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        result = await step.execute(workflow_context)

        assert isinstance(result, StepResult)
        assert result.name == "test-generate"
        assert result.step_type == StepType.GENERATE
        assert result.success is True
        assert isinstance(result.output, str)
        assert "Generated text with context" in result.output
        assert result.duration_ms >= 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_passes_static_context_to_generator(self) -> None:
        """Test that execute() passes static context dict to generator.generate()."""
        generator = MockGeneratorAgent()
        context_dict = {
            "prompt": "Write unit tests",
            "language": "python",
            "max_tokens": 500,
        }

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context=context_dict,
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        result = await step.execute(workflow_context)

        # Verify generator was called with the context
        assert generator.generate_called is True
        assert generator.last_context == context_dict
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_with_empty_static_context(self) -> None:
        """Test execute() with empty static context dict."""
        generator = MockGeneratorAgent()

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context={},
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        result = await step.execute(workflow_context)

        assert result.success is True
        assert generator.last_context == {}


class TestGenerateStepExecuteWithCallableContext:
    """Test GenerateStep.execute() with callable context builder."""

    @pytest.mark.asyncio
    async def test_execute_with_callable_context_returns_step_result(self) -> None:
        """Test that execute() with callable context returns StepResult."""
        generator = MockGeneratorAgent()

        async def context_builder(ctx: WorkflowContext) -> dict[str, Any]:
            return {
                "prompt": "Generate from workflow input",
                "input_data": ctx.inputs.get("user_input"),
            }

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context=context_builder,
        )

        workflow_context = WorkflowContext(
            inputs={"user_input": "Test data"},
            results={},
        )
        result = await step.execute(workflow_context)

        assert isinstance(result, StepResult)
        assert result.name == "test-generate"
        assert result.step_type == StepType.GENERATE
        assert result.success is True
        assert isinstance(result.output, str)
        assert result.duration_ms >= 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_resolves_callable_context_before_generate(self) -> None:
        """Test that execute() resolves callable context before calling generator."""
        generator = MockGeneratorAgent()

        async def context_builder(ctx: WorkflowContext) -> dict[str, Any]:
            await asyncio.sleep(0.001)  # Simulate async work
            return {
                "prompt": f"Input was: {ctx.inputs.get('value')}",
                "mode": "test",
            }

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context=context_builder,
        )

        workflow_context = WorkflowContext(
            inputs={"value": 42},
            results={},
        )
        result = await step.execute(workflow_context)

        # Verify generator received the resolved context
        assert generator.generate_called is True
        assert generator.last_context == {
            "prompt": "Input was: 42",
            "mode": "test",
        }
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_context_builder_can_access_prior_step_results(
        self,
    ) -> None:
        """Test that context builder can access results from prior steps."""
        generator = MockGeneratorAgent()

        async def context_builder(ctx: WorkflowContext) -> dict[str, Any]:
            prior_output = ctx.get_step_output("parse_input")
            return {
                "prompt": f"Generate based on: {prior_output}",
            }

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context=context_builder,
        )

        # Create workflow context with a prior step result
        prior_result = StepResult(
            name="parse_input",
            step_type=StepType.PYTHON,
            success=True,
            output="parsed_data",
            duration_ms=10,
        )
        workflow_context = WorkflowContext(
            inputs={},
            results={"parse_input": prior_result},
        )

        result = await step.execute(workflow_context)

        assert result.success is True
        assert generator.last_context == {
            "prompt": "Generate based on: parsed_data",
        }

    @pytest.mark.asyncio
    async def test_execute_context_builder_with_complex_logic(self) -> None:
        """Test context builder with complex conditional logic."""
        generator = MockGeneratorAgent()

        async def context_builder(ctx: WorkflowContext) -> dict[str, Any]:
            issue_num = ctx.inputs.get("issue_number")
            if issue_num:
                return {
                    "prompt": f"Generate fix for issue #{issue_num}",
                    "context_type": "issue",
                }
            else:
                return {
                    "prompt": "Generate new feature",
                    "context_type": "feature",
                }

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context=context_builder,
        )

        # Test with issue number
        workflow_context = WorkflowContext(
            inputs={"issue_number": 123},
            results={},
        )
        result = await step.execute(workflow_context)

        assert result.success is True
        assert generator.last_context["context_type"] == "issue"
        assert "issue #123" in generator.last_context["prompt"]


class TestGenerateStepExecuteExceptionHandling:
    """Test GenerateStep.execute() exception handling."""

    @pytest.mark.asyncio
    async def test_execute_handles_generator_exception(self) -> None:
        """Test execute() catches generator exceptions, returns failed result."""
        generator = FailingGeneratorAgent()

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context={"prompt": "test"},
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        result = await step.execute(workflow_context)

        assert result.success is False
        assert result.output is None
        assert result.error is not None
        assert "RuntimeError" in result.error
        assert "Generator failed to produce output" in result.error
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_returns_failed_result_on_builder_exception(
        self,
    ) -> None:
        """Test that execute() returns failed StepResult when context builder fails."""
        generator = MockGeneratorAgent()

        async def failing_context_builder(ctx: WorkflowContext) -> dict[str, Any]:
            raise ValueError("Context builder failed")

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context=failing_context_builder,
        )

        workflow_context = WorkflowContext(inputs={}, results={})

        # Context builder failures should return failed StepResult
        result = await step.execute(workflow_context)

        # Check the result contains useful information
        assert result.success is False
        assert result.output is None
        assert result.error is not None
        assert "test-generate" in result.error
        assert "Context builder" in result.error
        assert "ValueError" in result.error
        assert "Context builder failed" in result.error
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_succeeds_when_context_builder_references_missing_step(
        self,
    ) -> None:
        """Test that missing step returns None (FR-009a), allowing graceful handling."""
        generator = MockGeneratorAgent()

        async def context_builder(ctx: WorkflowContext) -> dict[str, Any]:
            # get_step_output returns None for missing steps (FR-009a)
            output = ctx.get_step_output("non_existent_step")
            return {"prompt": str(output)}  # Will be "None"

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context=context_builder,
        )

        workflow_context = WorkflowContext(inputs={}, results={})

        # Should succeed since get_step_output returns None instead of raising
        result = await step.execute(workflow_context)

        assert result.success is True
        assert result.output is not None  # Generator produces output

    @pytest.mark.asyncio
    async def test_execute_handles_generator_returning_non_string(self) -> None:
        """Test handling when generator returns non-string value."""

        class BadGeneratorAgent:
            """Generator that returns wrong type."""

            name = "bad-generator"

            async def generate(self, context: dict[str, Any]) -> int:  # type: ignore
                """Return int instead of str."""
                return 123

        generator = BadGeneratorAgent()

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context={},
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        result = await step.execute(workflow_context)

        # Implementation should handle this gracefully
        # Either convert to string or fail with clear error
        # Here we test that it doesn't crash the workflow
        assert isinstance(result, StepResult)
        assert result.name == "test-generate"


class TestGenerateStepExecuteDuration:
    """Test that execute() correctly measures duration."""

    @pytest.mark.asyncio
    async def test_execute_measures_duration_for_successful_generation(self) -> None:
        """Test that execute() records execution duration in milliseconds."""

        class SlowGenerator:
            """Generator with intentional delay."""

            name = "slow-generator"

            async def generate(self, context: dict[str, Any]) -> str:
                """Generate with delay."""
                await asyncio.sleep(0.05)  # 50ms
                return "Generated content"

        generator = SlowGenerator()

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context={},
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        result = await step.execute(workflow_context)

        # Should be at least 50ms (accounting for overhead)
        assert result.duration_ms >= 40
        assert result.duration_ms < 200  # Sanity check

    @pytest.mark.asyncio
    async def test_execute_measures_duration_on_failure(self) -> None:
        """Test that execute() records duration even when generation fails."""

        class SlowFailingGenerator:
            """Generator that fails after delay."""

            name = "slow-failing-generator"

            async def generate(self, context: dict[str, Any]) -> str:
                """Generate with delay then fail."""
                await asyncio.sleep(0.01)
                raise RuntimeError("Failed after delay")

        generator = SlowFailingGenerator()

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context={},
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        result = await step.execute(workflow_context)

        assert result.success is False
        assert result.duration_ms >= 5  # At least some time recorded

    @pytest.mark.asyncio
    async def test_execute_includes_context_builder_time_in_duration(self) -> None:
        """Test that duration includes time spent resolving context builder."""

        class FastGenerator:
            """Generator with minimal delay."""

            name = "fast-generator"

            async def generate(self, context: dict[str, Any]) -> str:
                """Generate quickly."""
                await asyncio.sleep(0.001)
                return "output"

        async def slow_context_builder(ctx: WorkflowContext) -> dict[str, Any]:
            await asyncio.sleep(0.03)  # 30ms context building
            return {"prompt": "test"}

        generator = FastGenerator()

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context=slow_context_builder,
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        result = await step.execute(workflow_context)

        # Total time should include both context building and generation
        assert result.duration_ms >= 25  # 30ms + 1ms - overhead tolerance


class TestGenerateStepContextResolution:
    """Test GenerateStep context resolution behavior."""

    @pytest.mark.asyncio
    async def test_static_context_is_not_modified_by_execution(self) -> None:
        """Test that static context dict is not mutated during execution."""
        generator = MockGeneratorAgent()
        original_context = {"prompt": "test", "value": 42}
        context_copy = original_context.copy()

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context=original_context,
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        await step.execute(workflow_context)

        # Original context should be unchanged
        assert original_context == context_copy

    @pytest.mark.asyncio
    async def test_callable_context_is_called_on_each_execute(self) -> None:
        """Test that callable context is invoked on each execution."""
        generator = MockGeneratorAgent()
        call_count = 0

        async def counting_context_builder(ctx: WorkflowContext) -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            return {"call_number": call_count}

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context=counting_context_builder,
        )

        workflow_context = WorkflowContext(inputs={}, results={})

        # First execution
        await step.execute(workflow_context)
        assert call_count == 1
        assert generator.last_context == {"call_number": 1}

        # Second execution (if step were reused)
        await step.execute(workflow_context)
        assert call_count == 2
        assert generator.last_context == {"call_number": 2}

    @pytest.mark.asyncio
    async def test_context_builder_receives_correct_workflow_context(self) -> None:
        """Test that context builder receives the correct WorkflowContext."""
        generator = MockGeneratorAgent()
        received_context: WorkflowContext | None = None

        async def inspecting_context_builder(
            ctx: WorkflowContext,
        ) -> dict[str, Any]:
            nonlocal received_context
            received_context = ctx
            return {"prompt": "test"}

        step = GenerateStep(
            name="test-generate",
            generator=generator,
            context=inspecting_context_builder,
        )

        workflow_context = WorkflowContext(
            inputs={"test_input": "value"},
            results={},
        )

        await step.execute(workflow_context)

        assert received_context is workflow_context
        assert received_context.inputs == {"test_input": "value"}
