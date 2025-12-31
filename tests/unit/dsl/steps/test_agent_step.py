"""Unit tests for AgentStep class.

This module tests the AgentStep class that executes MaverickAgent instances
within workflow execution, with support for static and callable context builders.

TDD Note: These tests are written FIRST and will FAIL until implementation
is complete. They define the expected behavior of AgentStep.
"""

from __future__ import annotations

from typing import Any

import pytest

from maverick.dsl import StepResult, StepType, WorkflowContext
from maverick.dsl.steps.agent import AgentStep


class MockAgent:
    """Mock agent for testing AgentStep.

    Simulates the MaverickAgent interface without requiring the full SDK.
    """

    def __init__(self, name: str = "test-agent") -> None:
        """Initialize mock agent.

        Args:
            name: Agent name for identification.
        """
        self.name = name
        self.execute_called = False
        self.last_context: dict[str, Any] | None = None

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Mock execute method that records invocation.

        Args:
            context: Context dictionary passed to the agent.

        Returns:
            Mock result dictionary.
        """
        self.execute_called = True
        self.last_context = context
        return {"status": "success", "result": "mock_output"}


class FailingMockAgent:
    """Mock agent that raises an exception during execution."""

    def __init__(self, name: str = "failing-agent") -> None:
        """Initialize failing mock agent.

        Args:
            name: Agent name for identification.
        """
        self.name = name

    async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Mock execute method that raises an exception.

        Args:
            context: Context dictionary (not used).

        Raises:
            RuntimeError: Always raises to simulate agent failure.
        """
        raise RuntimeError("Agent execution failed")


class TestAgentStepCreation:
    """Test AgentStep instantiation and properties."""

    def test_creation_with_static_context(self) -> None:
        """Test creating AgentStep with static dict context."""
        agent = MockAgent(name="my-agent")
        static_context = {"key1": "value1", "key2": 42}

        step = AgentStep(
            name="test-step",
            agent=agent,
            context=static_context,
        )

        assert step.name == "test-step"
        assert step.agent is agent
        assert step.context == static_context
        assert step.step_type == StepType.AGENT

    def test_creation_with_callable_context(self) -> None:
        """Test creating AgentStep with callable context builder."""
        agent = MockAgent(name="my-agent")

        async def context_builder(workflow_context: WorkflowContext) -> dict[str, Any]:
            return {"dynamic": "value"}

        step = AgentStep(
            name="test-step",
            agent=agent,
            context=context_builder,
        )

        assert step.name == "test-step"
        assert step.agent is agent
        assert callable(step.context)
        assert step.context is context_builder
        assert step.step_type == StepType.AGENT

    def test_step_type_is_always_agent(self) -> None:
        """Test that step_type is always StepType.AGENT."""
        agent = MockAgent()

        step = AgentStep(
            name="test-step",
            agent=agent,
            context={},
        )

        assert step.step_type == StepType.AGENT

    def test_agent_step_is_frozen(self) -> None:
        """Test that AgentStep is immutable (frozen=True)."""
        agent = MockAgent()

        step = AgentStep(
            name="test-step",
            agent=agent,
            context={},
        )

        # Attempt to modify should raise error
        with pytest.raises((AttributeError, TypeError)):
            step.name = "modified"

    def test_agent_step_has_slots(self) -> None:
        """Test that AgentStep declares __slots__ for memory efficiency."""
        agent = MockAgent()

        AgentStep(
            name="test-step",
            agent=agent,
            context={},
        )

        # Dataclass with slots=True declares __slots__
        assert hasattr(AgentStep, "__slots__")


class TestAgentStepToDict:
    """Test AgentStep.to_dict() serialization."""

    def test_to_dict_with_static_context(self) -> None:
        """Test that to_dict() returns correct structure for static context."""
        agent = MockAgent(name="my-agent")
        static_context = {"key": "value"}

        step = AgentStep(
            name="test-step",
            agent=agent,
            context=static_context,
        )

        result = step.to_dict()

        assert result["name"] == "test-step"
        assert result["step_type"] == "agent"
        assert result["agent"] == "my-agent"
        assert result["context_type"] == "static"

    def test_to_dict_with_callable_context(self) -> None:
        """Test that to_dict() returns correct structure for callable context."""
        agent = MockAgent(name="my-agent")

        async def context_builder(workflow_context: WorkflowContext) -> dict[str, Any]:
            return {}

        step = AgentStep(
            name="test-step",
            agent=agent,
            context=context_builder,
        )

        result = step.to_dict()

        assert result["name"] == "test-step"
        assert result["step_type"] == "agent"
        assert result["agent"] == "my-agent"
        assert result["context_type"] == "callable"

    def test_to_dict_with_agent_without_name_attribute(self) -> None:
        """Test to_dict() with agent that doesn't have a name attribute."""

        class UnnamedAgent:
            async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
                return {}

        agent = UnnamedAgent()

        step = AgentStep(
            name="test-step",
            agent=agent,
            context={},
        )

        result = step.to_dict()

        # Should use class name as fallback
        assert result["agent"] == "UnnamedAgent"


class TestAgentStepResolveContext:
    """Test AgentStep._resolve_context() method."""

    @pytest.mark.asyncio
    async def test_resolve_context_returns_static_dict_unchanged(self) -> None:
        """Test that _resolve_context() returns static dict unchanged."""
        agent = MockAgent()
        static_context = {"key1": "value1", "key2": 42, "nested": {"a": "b"}}

        step = AgentStep(
            name="test-step",
            agent=agent,
            context=static_context,
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        resolved = await step._resolve_context(workflow_context)

        assert resolved == static_context
        assert resolved is static_context  # Should be same object

    @pytest.mark.asyncio
    async def test_resolve_context_calls_and_awaits_context_builder(self) -> None:
        """Test that _resolve_context() calls and awaits context builder."""
        agent = MockAgent()
        builder_called = False

        async def context_builder(workflow_context: WorkflowContext) -> dict[str, Any]:
            nonlocal builder_called
            builder_called = True
            return {"built": "context", "input": workflow_context.inputs.get("test")}

        step = AgentStep(
            name="test-step",
            agent=agent,
            context=context_builder,
        )

        workflow_context = WorkflowContext(inputs={"test": "value"}, results={})
        resolved = await step._resolve_context(workflow_context)

        assert builder_called is True
        assert resolved == {"built": "context", "input": "value"}

    @pytest.mark.asyncio
    async def test_resolve_context_builder_receives_workflow_context(self) -> None:
        """Test that context builder receives correct WorkflowContext."""
        agent = MockAgent()
        received_context = None

        async def context_builder(workflow_context: WorkflowContext) -> dict[str, Any]:
            nonlocal received_context
            received_context = workflow_context
            return {}

        step = AgentStep(
            name="test-step",
            agent=agent,
            context=context_builder,
        )

        workflow_context = WorkflowContext(
            inputs={"input1": "value1"},
            results={},
        )
        await step._resolve_context(workflow_context)

        assert received_context is workflow_context


class TestAgentStepExecute:
    """Test AgentStep.execute() method."""

    @pytest.mark.asyncio
    async def test_execute_with_static_context_returns_step_result(self) -> None:
        """Test that execute() with static context returns StepResult."""
        agent = MockAgent(name="test-agent")
        static_context = {"key": "value"}

        step = AgentStep(
            name="test-step",
            agent=agent,
            context=static_context,
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        result = await step.execute(workflow_context)

        assert isinstance(result, StepResult)
        assert result.name == "test-step"
        assert result.step_type == StepType.AGENT
        assert result.success is True
        assert result.output == {"status": "success", "result": "mock_output"}
        assert result.duration_ms >= 0
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_passes_static_context_to_agent(self) -> None:
        """Test that execute() passes static context to agent.execute()."""
        agent = MockAgent(name="test-agent")
        static_context = {"key1": "value1", "key2": 42}

        step = AgentStep(
            name="test-step",
            agent=agent,
            context=static_context,
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        await step.execute(workflow_context)

        # Verify agent received the context
        assert agent.execute_called is True
        assert agent.last_context == static_context

    @pytest.mark.asyncio
    async def test_execute_with_callable_context_resolves_and_passes(self) -> None:
        """Test that execute() resolves callable context and passes to agent."""
        agent = MockAgent(name="test-agent")

        async def context_builder(workflow_context: WorkflowContext) -> dict[str, Any]:
            return {
                "input_value": workflow_context.inputs.get("test_input"),
                "computed": "dynamic",
            }

        step = AgentStep(
            name="test-step",
            agent=agent,
            context=context_builder,
        )

        workflow_context = WorkflowContext(inputs={"test_input": "hello"}, results={})
        result = await step.execute(workflow_context)

        # Verify agent received resolved context
        assert agent.execute_called is True
        assert agent.last_context == {"input_value": "hello", "computed": "dynamic"}
        assert result.success is True

    @pytest.mark.asyncio
    async def test_execute_with_agent_exception_returns_failed_result(
        self,
    ) -> None:
        """Test that execute() handles agent exceptions and returns
        failed StepResult."""
        agent = FailingMockAgent(name="failing-agent")

        step = AgentStep(
            name="test-step",
            agent=agent,
            context={},
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        result = await step.execute(workflow_context)

        assert result.success is False
        assert result.output is None
        assert result.error is not None
        assert "RuntimeError" in result.error
        assert "Agent execution failed" in result.error
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_measures_duration(self) -> None:
        """Test that execute() records execution duration in milliseconds."""
        import asyncio

        class SlowAgent:
            name = "slow-agent"

            async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
                await asyncio.sleep(0.05)  # 50ms
                return {"done": True}

        agent = SlowAgent()
        step = AgentStep(
            name="test-step",
            agent=agent,
            context={},
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        result = await step.execute(workflow_context)

        # Should be at least 50ms (accounting for overhead)
        assert result.duration_ms >= 40
        assert result.duration_ms < 200  # Sanity check


class TestAgentStepContextBuilderFailure:
    """Test AgentStep context builder failure handling (T039)."""

    @pytest.mark.asyncio
    async def test_context_builder_exception_returns_failed_result(self) -> None:
        """Test that context builder failure returns failed StepResult."""
        agent = MockAgent()

        async def failing_builder(workflow_context: WorkflowContext) -> dict[str, Any]:
            raise ValueError("Builder failed")

        step = AgentStep(
            name="test-step",
            agent=agent,
            context=failing_builder,
        )

        workflow_context = WorkflowContext(inputs={}, results={})

        # Should return failed StepResult instead of raising
        result = await step.execute(workflow_context)

        assert isinstance(result, StepResult)
        assert result.success is False
        assert result.output is None
        assert result.error is not None
        assert "Context builder for step 'test-step' failed" in result.error
        assert "ValueError" in result.error
        assert "Builder failed" in result.error
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_context_builder_error_includes_original_exception(self) -> None:
        """Test that context builder failure includes original exception details."""
        agent = MockAgent()

        async def failing_builder(workflow_context: WorkflowContext) -> dict[str, Any]:
            raise KeyError("missing_key")

        step = AgentStep(
            name="test-step",
            agent=agent,
            context=failing_builder,
        )

        workflow_context = WorkflowContext(inputs={}, results={})

        result = await step.execute(workflow_context)

        # Verify error details in failed result
        assert result.success is False
        assert result.output is None
        assert result.error is not None
        assert "Context builder for step 'test-step' failed" in result.error
        assert "KeyError" in result.error
        assert "missing_key" in result.error
        assert result.duration_ms >= 0


class TestAgentStepEdgeCases:
    """Test edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_execute_with_empty_static_context(self) -> None:
        """Test execute() with empty dict as static context."""
        agent = MockAgent()

        step = AgentStep(
            name="test-step",
            agent=agent,
            context={},
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        result = await step.execute(workflow_context)

        assert result.success is True
        assert agent.last_context == {}

    @pytest.mark.asyncio
    async def test_execute_with_context_builder_returning_empty_dict(self) -> None:
        """Test execute() with context builder that returns empty dict."""
        agent = MockAgent()

        async def empty_builder(workflow_context: WorkflowContext) -> dict[str, Any]:
            return {}

        step = AgentStep(
            name="test-step",
            agent=agent,
            context=empty_builder,
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        result = await step.execute(workflow_context)

        assert result.success is True
        assert agent.last_context == {}

    @pytest.mark.asyncio
    async def test_execute_with_agent_returning_none(self) -> None:
        """Test execute() when agent returns None."""

        class NoneAgent:
            name = "none-agent"

            async def execute(self, context: dict[str, Any]) -> None:  # type: ignore[misc]
                return None

        agent = NoneAgent()
        step = AgentStep(
            name="test-step",
            agent=agent,
            context={},
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        result = await step.execute(workflow_context)

        assert result.success is True
        assert result.output is None

    @pytest.mark.asyncio
    async def test_execute_with_complex_agent_output(self) -> None:
        """Test execute() with complex agent output structure."""

        class ComplexAgent:
            name = "complex-agent"

            async def execute(self, context: dict[str, Any]) -> dict[str, Any]:
                return {
                    "status": "success",
                    "data": {
                        "items": [1, 2, 3],
                        "metadata": {"count": 3},
                    },
                    "nested": {"deep": {"value": "here"}},
                }

        agent = ComplexAgent()
        step = AgentStep(
            name="test-step",
            agent=agent,
            context={},
        )

        workflow_context = WorkflowContext(inputs={}, results={})
        result = await step.execute(workflow_context)

        assert result.success is True
        assert result.output["status"] == "success"
        assert result.output["data"]["items"] == [1, 2, 3]
        assert result.output["nested"]["deep"]["value"] == "here"
