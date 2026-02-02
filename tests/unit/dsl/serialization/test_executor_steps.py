"""Unit tests for WorkflowFileExecutor step implementations.

This module tests the execution of specific step types in WorkflowFileExecutor:
- AgentStepRecord execution with mocked agents
- GenerateStepRecord execution with mocked generators
- ValidateStepRecord execution with validation stages
- BranchStepRecord execution with conditional branching
- LoopStepRecord execution with concurrent steps

These tests use mocking to isolate step execution logic from actual implementations.
"""

from __future__ import annotations

import pytest

from maverick.dsl.serialization import (
    AgentStepRecord,
    BranchOptionRecord,
    BranchStepRecord,
    ComponentRegistry,
    GenerateStepRecord,
    LoopStepRecord,
    PythonStepRecord,
    ValidateStepRecord,
    WorkflowFile,
    WorkflowFileExecutor,
)
from maverick.dsl.types import StepType

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def registry():
    """Create a component registry with test components."""
    return ComponentRegistry()


@pytest.fixture
def registry_with_agent():
    """Create a registry with a mock agent."""
    reg = ComponentRegistry()

    # Create a mock agent class
    class MockAgent:
        """Mock agent for testing."""

        def execute(self, context):
            """Execute agent with context."""
            # Return a result based on context
            if isinstance(context, dict) and "input" in context:
                return f"Agent processed: {context['input']}"
            return "Agent executed"

    reg.agents.register("test_agent", MockAgent, validate=False)
    return reg


@pytest.fixture
def registry_with_async_agent():
    """Create a registry with a mock async agent."""
    reg = ComponentRegistry()

    # Create a mock async agent class
    class MockAsyncAgent:
        """Mock async agent for testing."""

        async def execute(self, context):
            """Execute agent with context asynchronously."""
            if isinstance(context, dict) and "input" in context:
                return f"Async agent processed: {context['input']}"
            return "Async agent executed"

    reg.agents.register("async_agent", MockAsyncAgent, validate=False)
    return reg


@pytest.fixture
def registry_with_generator():
    """Create a registry with a mock generator."""
    reg = ComponentRegistry()

    # Create a mock generator class
    class MockGenerator:
        """Mock generator for testing."""

        def generate(self, context):
            """Generate text based on context."""
            if isinstance(context, dict) and "prompt" in context:
                return f"Generated: {context['prompt']}"
            return "Generated content"

    reg.generators.register("test_generator", MockGenerator, validate=False)
    return reg


@pytest.fixture
def registry_with_async_generator():
    """Create a registry with a mock async generator."""
    reg = ComponentRegistry()

    # Create a mock async generator class
    class MockAsyncGenerator:
        """Mock async generator for testing."""

        async def generate(self, context):
            """Generate text asynchronously."""
            if isinstance(context, dict) and "prompt" in context:
                return f"Async generated: {context['prompt']}"
            return "Async generated content"

    reg.generators.register("async_generator", MockAsyncGenerator, validate=False)
    return reg


@pytest.fixture
def registry_with_context_builder():
    """Create a registry with a context builder."""
    reg = ComponentRegistry()

    # Create a context builder function
    def build_context(inputs, step_results):
        """Build enhanced context from inputs and step results."""
        return {
            "enhanced": True,
            "inputs": inputs,
            "step_results": step_results,
            "built_field": "from_builder",
        }

    reg.context_builders.register("test_context_builder", build_context)
    return reg


@pytest.fixture
def registry_with_async_context_builder():
    """Create a registry with an async context builder."""
    reg = ComponentRegistry()

    # Create an async context builder function
    async def build_context_async(inputs, step_results):
        """Build enhanced context asynchronously."""
        return {
            "enhanced": True,
            "async": True,
            "inputs": inputs,
            "step_results": step_results,
            "built_field": "from_async_builder",
        }

    reg.context_builders.register("async_context_builder", build_context_async)
    return reg


# =============================================================================
# AgentStep Execution Tests
# =============================================================================


class TestAgentStepExecution:
    """Tests for AgentStepRecord execution."""

    @pytest.mark.asyncio
    async def test_agent_step_success(self, registry_with_agent):
        """Test successful agent step execution."""
        workflow = WorkflowFile(
            version="1.0",
            name="agent-workflow",
            steps=[
                AgentStepRecord(
                    name="run_agent",
                    type=StepType.AGENT,
                    agent="test_agent",
                    context={"input": "test data"},
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry_with_agent)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == "Agent processed: test data"

    @pytest.mark.asyncio
    async def test_agent_step_async_agent(self, registry_with_async_agent):
        """Test agent step with async agent execution."""
        workflow = WorkflowFile(
            version="1.0",
            name="async-agent-workflow",
            steps=[
                AgentStepRecord(
                    name="run_async_agent",
                    type=StepType.AGENT,
                    agent="async_agent",
                    context={"input": "async test"},
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry_with_async_agent)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == "Async agent processed: async test"

    @pytest.mark.asyncio
    async def test_agent_step_with_expression_in_context(self, registry_with_agent):
        """Test agent step with expression resolution in context."""
        workflow = WorkflowFile(
            version="1.0",
            name="expr-agent-workflow",
            steps=[
                AgentStepRecord(
                    name="run_agent",
                    type=StepType.AGENT,
                    agent="test_agent",
                    context={"input": "${{ inputs.user_input }}"},
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry_with_agent)
        async for _ in executor.execute(workflow, inputs={"user_input": "from input"}):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == "Agent processed: from input"

    @pytest.mark.asyncio
    async def test_agent_step_with_context_builder(
        self, registry_with_agent, registry_with_context_builder
    ):
        """Test agent step using a context builder."""
        # Merge registries
        registry = registry_with_agent
        registry.context_builders = registry_with_context_builder.context_builders

        # Create mock agent that returns the context for inspection
        class ContextInspectorAgent:
            def execute(self, context):
                return context

        registry.agents.register(
            "inspector_agent", ContextInspectorAgent, validate=False
        )

        workflow = WorkflowFile(
            version="1.0",
            name="context-builder-workflow",
            steps=[
                AgentStepRecord(
                    name="run_agent",
                    type=StepType.AGENT,
                    agent="inspector_agent",
                    context="test_context_builder",
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        # Verify context was built by the builder
        assert result.final_output["enhanced"] is True
        assert result.final_output["built_field"] == "from_builder"

    @pytest.mark.asyncio
    async def test_agent_step_with_async_context_builder(
        self, registry_with_agent, registry_with_async_context_builder
    ):
        """Test agent step using an async context builder."""
        # Merge registries
        registry = registry_with_agent
        registry.context_builders = registry_with_async_context_builder.context_builders

        # Create mock agent that returns the context for inspection
        class ContextInspectorAgent:
            def execute(self, context):
                return context

        registry.agents.register(
            "inspector_agent", ContextInspectorAgent, validate=False
        )

        workflow = WorkflowFile(
            version="1.0",
            name="async-context-builder-workflow",
            steps=[
                AgentStepRecord(
                    name="run_agent",
                    type=StepType.AGENT,
                    agent="inspector_agent",
                    context="async_context_builder",
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        # Verify context was built by the async builder
        assert result.final_output["enhanced"] is True
        assert result.final_output["async"] is True
        assert result.final_output["built_field"] == "from_async_builder"

    @pytest.mark.asyncio
    async def test_agent_step_missing_agent(self, registry):
        """Test agent step with missing agent reference."""
        workflow = WorkflowFile(
            version="1.0",
            name="missing-agent-workflow",
            steps=[
                AgentStepRecord(
                    name="run_agent",
                    type=StepType.AGENT,
                    agent="nonexistent_agent",
                    context={},
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        events = []
        async for event in executor.execute(workflow):
            events.append(event)

        result = executor.get_result()
        assert result.success is False
        # Validation catches missing agent before step execution
        assert len(result.step_results) == 0

    @pytest.mark.asyncio
    async def test_agent_step_missing_context_builder(self, registry_with_agent):
        """Test agent step with missing context builder reference."""
        workflow = WorkflowFile(
            version="1.0",
            name="missing-context-builder-workflow",
            steps=[
                AgentStepRecord(
                    name="run_agent",
                    type=StepType.AGENT,
                    agent="test_agent",
                    context="nonexistent_builder",
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry_with_agent)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is False
        # Validation catches missing context builder before step execution
        assert len(result.step_results) == 0

    @pytest.mark.asyncio
    async def test_agent_step_agent_raises_exception(self, registry):
        """Test agent step when agent raises exception."""

        class FailingAgent:
            def execute(self, context):
                raise RuntimeError("Agent failed!")

        registry.agents.register("failing_agent", FailingAgent, validate=False)

        workflow = WorkflowFile(
            version="1.0",
            name="failing-agent-workflow",
            steps=[
                AgentStepRecord(
                    name="run_agent",
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
        assert "Agent failed!" in result.step_results[0].error


# =============================================================================
# GenerateStep Execution Tests
# =============================================================================


class TestGenerateStepExecution:
    """Tests for GenerateStepRecord execution."""

    @pytest.mark.asyncio
    async def test_generate_step_success(self, registry_with_generator):
        """Test successful generate step execution."""
        workflow = WorkflowFile(
            version="1.0",
            name="generate-workflow",
            steps=[
                GenerateStepRecord(
                    name="generate_text",
                    type=StepType.GENERATE,
                    generator="test_generator",
                    context={"prompt": "Write a summary"},
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry_with_generator)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == "Generated: Write a summary"

    @pytest.mark.asyncio
    async def test_generate_step_async_generator(self, registry_with_async_generator):
        """Test generate step with async generator execution."""
        workflow = WorkflowFile(
            version="1.0",
            name="async-generate-workflow",
            steps=[
                GenerateStepRecord(
                    name="generate_text",
                    type=StepType.GENERATE,
                    generator="async_generator",
                    context={"prompt": "Async prompt"},
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry_with_async_generator)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == "Async generated: Async prompt"

    @pytest.mark.asyncio
    async def test_generate_step_with_expression_in_context(
        self, registry_with_generator
    ):
        """Test generate step with expression resolution in context."""
        workflow = WorkflowFile(
            version="1.0",
            name="expr-generate-workflow",
            steps=[
                GenerateStepRecord(
                    name="generate_text",
                    type=StepType.GENERATE,
                    generator="test_generator",
                    context={"prompt": "${{ inputs.user_prompt }}"},
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry_with_generator)
        async for _ in executor.execute(
            workflow, inputs={"user_prompt": "Custom prompt"}
        ):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == "Generated: Custom prompt"

    @pytest.mark.asyncio
    async def test_generate_step_with_context_builder(
        self, registry_with_generator, registry_with_context_builder
    ):
        """Test generate step using a context builder."""
        # Merge registries
        registry = registry_with_generator
        registry.context_builders = registry_with_context_builder.context_builders

        # Create mock generator that returns the context for inspection
        class ContextInspectorGenerator:
            def generate(self, context):
                return context

        registry.generators.register(
            "inspector_generator", ContextInspectorGenerator, validate=False
        )

        workflow = WorkflowFile(
            version="1.0",
            name="context-builder-workflow",
            steps=[
                GenerateStepRecord(
                    name="generate_text",
                    type=StepType.GENERATE,
                    generator="inspector_generator",
                    context="test_context_builder",
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        # Verify context was built by the builder
        assert result.final_output["enhanced"] is True
        assert result.final_output["built_field"] == "from_builder"

    @pytest.mark.asyncio
    async def test_generate_step_missing_generator(self, registry):
        """Test generate step with missing generator reference."""
        workflow = WorkflowFile(
            version="1.0",
            name="missing-generator-workflow",
            steps=[
                GenerateStepRecord(
                    name="generate_text",
                    type=StepType.GENERATE,
                    generator="nonexistent_generator",
                    context={},
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is False
        # Validation catches missing generator before step execution
        assert len(result.step_results) == 0

    @pytest.mark.asyncio
    async def test_generate_step_missing_context_builder(self, registry_with_generator):
        """Test generate step with missing context builder reference."""
        workflow = WorkflowFile(
            version="1.0",
            name="missing-context-builder-workflow",
            steps=[
                GenerateStepRecord(
                    name="generate_text",
                    type=StepType.GENERATE,
                    generator="test_generator",
                    context="nonexistent_builder",
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry_with_generator)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is False
        # Validation catches missing context builder before step execution
        assert len(result.step_results) == 0

    @pytest.mark.asyncio
    async def test_generate_step_generator_raises_exception(self, registry):
        """Test generate step when generator raises exception."""

        class FailingGenerator:
            def generate(self, context):
                raise RuntimeError("Generator failed!")

        registry.generators.register(
            "failing_generator", FailingGenerator, validate=False
        )

        workflow = WorkflowFile(
            version="1.0",
            name="failing-generator-workflow",
            steps=[
                GenerateStepRecord(
                    name="generate_text",
                    type=StepType.GENERATE,
                    generator="failing_generator",
                    context={},
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is False
        assert "Generator failed!" in result.step_results[0].error


# =============================================================================
# ValidateStep Execution Tests
# =============================================================================


class TestValidateStepExecution:
    """Tests for ValidateStepRecord execution."""

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
                StageResult(
                    stage_name="typecheck",
                    passed=True,
                    output="OK",
                    duration_ms=10,
                    fix_attempts=0,
                    errors=(),
                ),
                StageResult(
                    stage_name="test",
                    passed=True,
                    output="OK",
                    duration_ms=10,
                    fix_attempts=0,
                    errors=(),
                ),
            ),
            total_duration_ms=40,
        )

        mock_runner = AsyncMock()
        mock_runner.run.return_value = mock_output

        with patch(
            "maverick.dsl.serialization.executor.handlers.validate_step.ValidationRunner",
            return_value=mock_runner,
        ):
            yield mock_runner

    @pytest.mark.asyncio
    async def test_validate_step_success(self, registry, mock_validation_runner):
        """Test successful validate step execution."""
        workflow = WorkflowFile(
            version="1.0",
            name="validate-workflow",
            steps=[
                ValidateStepRecord(
                    name="validate",
                    type=StepType.VALIDATE,
                    stages=["format", "lint"],
                    retry=0,
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        # ValidationResult is converted to dict for expression evaluation compatibility
        assert "success" in result.final_output
        assert result.final_output["success"] is True
        assert len(result.final_output["stages"]) == 2

    @pytest.mark.asyncio
    async def test_validate_step_multiple_stages(
        self, registry, mock_validation_runner
    ):
        """Test validate step with multiple stages."""
        workflow = WorkflowFile(
            version="1.0",
            name="multi-stage-validate-workflow",
            steps=[
                ValidateStepRecord(
                    name="validate",
                    type=StepType.VALIDATE,
                    stages=["format", "lint", "typecheck", "test"],
                    retry=0,
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        # ValidationResult has stages as a list of stage names
        # ValidationResult is converted to dict for expression evaluation compatibility
        assert len(result.final_output["stages"]) == 4
        assert result.final_output["stages"] == ["format", "lint", "typecheck", "test"]

    @pytest.mark.asyncio
    async def test_validate_step_with_retry(self, registry, mock_validation_runner):
        """Test validate step with retry configuration."""
        workflow = WorkflowFile(
            version="1.0",
            name="retry-validate-workflow",
            steps=[
                ValidateStepRecord(
                    name="validate",
                    type=StepType.VALIDATE,
                    stages=["test"],
                    retry=3,  # Max 3 retries
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        # Current implementation doesn't actually retry, just mocks success
        assert result.success is True

    @pytest.mark.asyncio
    async def test_validate_step_empty_stages(self, registry):
        """Test validate step with empty stages list."""
        workflow = WorkflowFile(
            version="1.0",
            name="empty-validate-workflow",
            steps=[
                ValidateStepRecord(
                    name="validate",
                    type=StepType.VALIDATE,
                    stages=[],
                    retry=0,
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        # ValidationResult is converted to dict for expression evaluation compatibility
        assert len(result.final_output["stages"]) == 0


# =============================================================================
# BranchStep Execution Tests
# =============================================================================


class TestBranchStepExecution:
    """Tests for BranchStepRecord execution."""

    @pytest.mark.asyncio
    async def test_branch_step_first_condition_true(self, registry):
        """Test branch step when first condition is true."""

        @registry.actions.register("action_a")
        def action_a():
            return "A"

        @registry.actions.register("action_b")
        def action_b():
            return "B"

        workflow = WorkflowFile(
            version="1.0",
            name="branch-workflow",
            steps=[
                BranchStepRecord(
                    name="choose_branch",
                    type=StepType.BRANCH,
                    options=[
                        BranchOptionRecord(
                            when="${{ inputs.choose_a }}",
                            step=PythonStepRecord(
                                name="branch_a",
                                type=StepType.PYTHON,
                                action="action_a",
                            ),
                        ),
                        BranchOptionRecord(
                            when="${{ inputs.choose_b }}",
                            step=PythonStepRecord(
                                name="branch_b",
                                type=StepType.PYTHON,
                                action="action_b",
                            ),
                        ),
                    ],
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(
            workflow, inputs={"choose_a": True, "choose_b": False}
        ):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == "A"

    @pytest.mark.asyncio
    async def test_branch_step_second_condition_true(self, registry):
        """Test branch step when second condition is true."""

        @registry.actions.register("action_a")
        def action_a():
            return "A"

        @registry.actions.register("action_b")
        def action_b():
            return "B"

        workflow = WorkflowFile(
            version="1.0",
            name="branch-workflow",
            steps=[
                BranchStepRecord(
                    name="choose_branch",
                    type=StepType.BRANCH,
                    options=[
                        BranchOptionRecord(
                            when="${{ inputs.choose_a }}",
                            step=PythonStepRecord(
                                name="branch_a",
                                type=StepType.PYTHON,
                                action="action_a",
                            ),
                        ),
                        BranchOptionRecord(
                            when="${{ inputs.choose_b }}",
                            step=PythonStepRecord(
                                name="branch_b",
                                type=StepType.PYTHON,
                                action="action_b",
                            ),
                        ),
                    ],
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(
            workflow, inputs={"choose_a": False, "choose_b": True}
        ):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == "B"

    @pytest.mark.asyncio
    async def test_branch_step_no_condition_matches(self, registry):
        """Test branch step when no condition matches."""

        @registry.actions.register("action_a")
        def action_a():
            return "A"

        workflow = WorkflowFile(
            version="1.0",
            name="branch-workflow",
            steps=[
                BranchStepRecord(
                    name="choose_branch",
                    type=StepType.BRANCH,
                    options=[
                        BranchOptionRecord(
                            when="${{ inputs.choose_a }}",
                            step=PythonStepRecord(
                                name="branch_a",
                                type=StepType.PYTHON,
                                action="action_a",
                            ),
                        ),
                    ],
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow, inputs={"choose_a": False}):
            pass

        result = executor.get_result()
        assert result.success is True
        # When no branch matches, result is None
        assert result.final_output is None

    @pytest.mark.asyncio
    async def test_branch_step_with_negation_condition(self, registry):
        """Test branch step with negation in condition."""

        @registry.actions.register("action_x")
        def action_x():
            return "X"

        @registry.actions.register("action_y")
        def action_y():
            return "Y"

        workflow = WorkflowFile(
            version="1.0",
            name="negation-branch-workflow",
            steps=[
                BranchStepRecord(
                    name="choose_branch",
                    type=StepType.BRANCH,
                    options=[
                        BranchOptionRecord(
                            when="${{ inputs.is_valid }}",
                            step=PythonStepRecord(
                                name="branch_x",
                                type=StepType.PYTHON,
                                action="action_x",
                            ),
                        ),
                        BranchOptionRecord(
                            when="${{ not inputs.is_valid }}",
                            step=PythonStepRecord(
                                name="branch_y",
                                type=StepType.PYTHON,
                                action="action_y",
                            ),
                        ),
                    ],
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow, inputs={"is_valid": False}):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == "Y"

    @pytest.mark.asyncio
    async def test_branch_step_evaluates_in_order(self, registry):
        """Test that branch options are evaluated in order."""

        @registry.actions.register("first")
        def first():
            return "first"

        @registry.actions.register("second")
        def second():
            return "second"

        workflow = WorkflowFile(
            version="1.0",
            name="order-branch-workflow",
            steps=[
                BranchStepRecord(
                    name="choose_branch",
                    type=StepType.BRANCH,
                    options=[
                        BranchOptionRecord(
                            when="${{ inputs.flag }}",
                            step=PythonStepRecord(
                                name="first_branch",
                                type=StepType.PYTHON,
                                action="first",
                            ),
                        ),
                        BranchOptionRecord(
                            when="${{ inputs.flag }}",  # Same condition
                            step=PythonStepRecord(
                                name="second_branch",
                                type=StepType.PYTHON,
                                action="second",
                            ),
                        ),
                    ],
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow, inputs={"flag": True}):
            pass

        result = executor.get_result()
        assert result.success is True
        # First matching option should be executed
        assert result.final_output == "first"


# =============================================================================
# ParallelStep Execution Tests
# =============================================================================


class TestParallelStepExecution:
    """Tests for LoopStepRecord execution."""

    @pytest.mark.asyncio
    async def test_parallel_step_success(self, registry):
        """Test successful parallel step execution."""

        @registry.actions.register("action_1")
        async def action_1():
            return "result_1"

        @registry.actions.register("action_2")
        async def action_2():
            return "result_2"

        workflow = WorkflowFile(
            version="1.0",
            name="parallel-workflow",
            steps=[
                LoopStepRecord(
                    name="run_parallel",
                    type=StepType.LOOP,
                    steps=[
                        PythonStepRecord(
                            name="step_1",
                            type=StepType.PYTHON,
                            action="action_1",
                        ),
                        PythonStepRecord(
                            name="step_2",
                            type=StepType.PYTHON,
                            action="action_2",
                        ),
                    ],
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        # Parallel step returns dict with results
        assert isinstance(result.final_output, dict)
        assert "results" in result.final_output
        assert len(result.final_output["results"]) == 2
        assert "result_1" in result.final_output["results"]
        assert "result_2" in result.final_output["results"]

    @pytest.mark.asyncio
    async def test_parallel_step_multiple_steps(self, registry):
        """Test parallel step with multiple concurrent steps."""

        @registry.actions.register("action_a")
        async def action_a():
            return "A"

        @registry.actions.register("action_b")
        async def action_b():
            return "B"

        @registry.actions.register("action_c")
        async def action_c():
            return "C"

        workflow = WorkflowFile(
            version="1.0",
            name="multi-parallel-workflow",
            steps=[
                LoopStepRecord(
                    name="run_parallel",
                    type=StepType.LOOP,
                    steps=[
                        PythonStepRecord(
                            name="step_a",
                            type=StepType.PYTHON,
                            action="action_a",
                        ),
                        PythonStepRecord(
                            name="step_b",
                            type=StepType.PYTHON,
                            action="action_b",
                        ),
                        PythonStepRecord(
                            name="step_c",
                            type=StepType.PYTHON,
                            action="action_c",
                        ),
                    ],
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        assert len(result.final_output["results"]) == 3

    @pytest.mark.asyncio
    async def test_parallel_step_with_exceptions(self, registry):
        """Test parallel step when one step raises exception.

        When any step in a parallel loop fails, the loop step should fail
        and propagate the error to stop the workflow. This ensures that failures
        are not silently swallowed.
        """

        @registry.actions.register("success_action")
        async def success_action():
            return "success"

        @registry.actions.register("failing_action")
        async def failing_action():
            raise RuntimeError("Failed!")

        workflow = WorkflowFile(
            version="1.0",
            name="parallel-with-error-workflow",
            steps=[
                LoopStepRecord(
                    name="run_parallel",
                    type=StepType.LOOP,
                    steps=[
                        PythonStepRecord(
                            name="success_step",
                            type=StepType.PYTHON,
                            action="success_action",
                        ),
                        PythonStepRecord(
                            name="failing_step",
                            type=StepType.PYTHON,
                            action="failing_action",
                        ),
                    ],
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        # Loop step should fail when any step fails
        assert result.success is False

        # Check that the step result indicates failure
        assert len(result.step_results) == 1
        step_result = result.step_results[0]
        assert step_result.name == "run_parallel"
        assert step_result.success is False
        assert step_result.error is not None
        assert "Failed!" in step_result.error

    @pytest.mark.asyncio
    async def test_parallel_step_with_sync_and_async(self, registry):
        """Test parallel step with mix of sync and async actions."""

        @registry.actions.register("sync_action")
        def sync_action():
            return "sync"

        @registry.actions.register("async_action")
        async def async_action():
            return "async"

        workflow = WorkflowFile(
            version="1.0",
            name="mixed-parallel-workflow",
            steps=[
                LoopStepRecord(
                    name="run_parallel",
                    type=StepType.LOOP,
                    steps=[
                        PythonStepRecord(
                            name="sync_step",
                            type=StepType.PYTHON,
                            action="sync_action",
                        ),
                        PythonStepRecord(
                            name="async_step",
                            type=StepType.PYTHON,
                            action="async_action",
                        ),
                    ],
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        assert len(result.final_output["results"]) == 2
        assert "sync" in result.final_output["results"]
        assert "async" in result.final_output["results"]

    @pytest.mark.asyncio
    async def test_parallel_step_with_for_each(self, registry):
        """Test parallel step with for_each iteration."""

        @registry.actions.register("process_item")
        async def process_item(item):
            return f"processed_{item}"

        workflow = WorkflowFile(
            version="1.0",
            name="parallel-for-each-workflow",
            steps=[
                LoopStepRecord(
                    name="process_items",
                    type=StepType.LOOP,
                    for_each="${{ inputs.items }}",
                    steps=[
                        PythonStepRecord(
                            name="process",
                            type=StepType.PYTHON,
                            action="process_item",
                            kwargs={"item": "${{ item }}"},
                        ),
                    ],
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow, inputs={"items": ["a", "b", "c"]}):
            pass

        result = executor.get_result()
        assert result.success is True
        # for_each creates one iteration per item
        assert "results" in result.final_output
        assert len(result.final_output["results"]) == 3
        # Each iteration returns a list with results from its steps
        for iteration_result in result.final_output["results"]:
            assert isinstance(iteration_result, (list, tuple))
            assert len(iteration_result) == 1  # One step per iteration

    @pytest.mark.asyncio
    async def test_parallel_step_for_each_with_multiple_steps(self, registry):
        """Test parallel step with for_each executing multiple steps per iteration."""

        @registry.actions.register("double")
        async def double(value):
            return value * 2

        @registry.actions.register("square")
        async def square(value):
            return value**2

        workflow = WorkflowFile(
            version="1.0",
            name="parallel-multi-step-for-each",
            steps=[
                LoopStepRecord(
                    name="process_numbers",
                    type=StepType.LOOP,
                    for_each="${{ inputs.numbers }}",
                    steps=[
                        PythonStepRecord(
                            name="double_it",
                            type=StepType.PYTHON,
                            action="double",
                            kwargs={"value": "${{ item }}"},
                        ),
                        PythonStepRecord(
                            name="square_it",
                            type=StepType.PYTHON,
                            action="square",
                            kwargs={"value": "${{ item }}"},
                        ),
                    ],
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow, inputs={"numbers": [2, 3, 4]}):
            pass

        result = executor.get_result()
        assert result.success is True
        assert len(result.final_output["results"]) == 3
        # Each iteration has 2 steps (double and square)
        for iteration_result in result.final_output["results"]:
            assert len(iteration_result) == 2

    @pytest.mark.asyncio
    async def test_parallel_step_for_each_empty_list(self, registry):
        """Test parallel step with for_each on empty list."""

        @registry.actions.register("process_item")
        async def process_item(item):
            return f"processed_{item}"

        workflow = WorkflowFile(
            version="1.0",
            name="parallel-empty-for-each",
            steps=[
                LoopStepRecord(
                    name="process_items",
                    type=StepType.LOOP,
                    for_each="${{ inputs.items }}",
                    steps=[
                        PythonStepRecord(
                            name="process",
                            type=StepType.PYTHON,
                            action="process_item",
                            kwargs={"item": "${{ item }}"},
                        ),
                    ],
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow, inputs={"items": []}):
            pass

        result = executor.get_result()
        assert result.success is True
        # Empty list means no iterations
        assert result.final_output["results"] == []

    @pytest.mark.asyncio
    async def test_parallel_step_for_each_invalid_expression(self, registry):
        """Test parallel step with for_each that evaluates to non-list."""

        @registry.actions.register("process_item")
        async def process_item(item):
            return f"processed_{item}"

        workflow = WorkflowFile(
            version="1.0",
            name="parallel-invalid-for-each",
            steps=[
                LoopStepRecord(
                    name="process_items",
                    type=StepType.LOOP,
                    for_each="${{ inputs.not_a_list }}",
                    steps=[
                        PythonStepRecord(
                            name="process",
                            type=StepType.PYTHON,
                            action="process_item",
                            kwargs={"item": "${{ item }}"},
                        ),
                    ],
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow, inputs={"not_a_list": "string"}):
            pass

        result = executor.get_result()
        # Should fail because for_each expects a list
        assert result.success is False
        assert "must evaluate to a list or tuple" in result.step_results[0].error

    @pytest.mark.asyncio
    async def test_parallel_step_for_each_with_exception(self, registry):
        """Test parallel step with for_each when one iteration fails.

        When any iteration in a for_each loop fails, the loop step should fail
        and propagate the error to stop the workflow.
        """

        @registry.actions.register("maybe_fail")
        async def maybe_fail(item):
            if item == "bad":
                raise ValueError("Bad item!")
            return f"ok_{item}"

        workflow = WorkflowFile(
            version="1.0",
            name="parallel-for-each-with-error",
            steps=[
                LoopStepRecord(
                    name="process_items",
                    type=StepType.LOOP,
                    for_each="${{ inputs.items }}",
                    steps=[
                        PythonStepRecord(
                            name="process",
                            type=StepType.PYTHON,
                            action="maybe_fail",
                            kwargs={"item": "${{ item }}"},
                        ),
                    ],
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(
            workflow, inputs={"items": ["good", "bad", "also_good"]}
        ):
            pass

        result = executor.get_result()
        # Loop step should fail when any iteration fails
        assert result.success is False

        # Check that the step result indicates failure
        assert len(result.step_results) == 1
        step_result = result.step_results[0]
        assert step_result.name == "process_items"
        assert step_result.success is False
        assert step_result.error is not None
        assert "Bad item!" in step_result.error


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestStepExecutionEdgeCases:
    """Tests for edge cases and error handling in step execution."""

    @pytest.mark.asyncio
    async def test_step_with_invalid_condition_expression(self, registry):
        """Test step with invalid condition expression."""

        @registry.actions.register("test_action")
        def test_action():
            return "test"

        workflow = WorkflowFile(
            version="1.0",
            name="invalid-condition-workflow",
            steps=[
                PythonStepRecord(
                    name="conditional_step",
                    type=StepType.PYTHON,
                    action="test_action",
                    when="${{ invalid.reference }}",  # Invalid reference
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        # Validation catches invalid expression before step execution
        assert result.success is False
        assert len(result.step_results) == 0

    @pytest.mark.asyncio
    async def test_agent_step_empty_context(self, registry_with_agent):
        """Test agent step with empty context."""
        workflow = WorkflowFile(
            version="1.0",
            name="empty-context-workflow",
            steps=[
                AgentStepRecord(
                    name="run_agent",
                    type=StepType.AGENT,
                    agent="test_agent",
                    context={},  # Empty context
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry_with_agent)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == "Agent executed"

    @pytest.mark.asyncio
    async def test_generate_step_empty_context(self, registry_with_generator):
        """Test generate step with empty context."""
        workflow = WorkflowFile(
            version="1.0",
            name="empty-context-workflow",
            steps=[
                GenerateStepRecord(
                    name="generate_text",
                    type=StepType.GENERATE,
                    generator="test_generator",
                    context={},  # Empty context
                )
            ],
        )

        executor = WorkflowFileExecutor(registry=registry_with_generator)
        async for _ in executor.execute(workflow):
            pass

        result = executor.get_result()
        assert result.success is True
        assert result.final_output == "Generated content"
