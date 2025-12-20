"""Example workflow unit tests demonstrating testing patterns.

This file demonstrates best practices for testing workflow logic in isolation:
1. Testing workflow class methods without full execution
2. Mocking dependencies (agents, tools, external services)
3. Testing state transitions and validation
4. Testing configuration validation and edge cases

Use this as a reference when writing unit tests for workflow components.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from maverick.models.validation import (
    ValidationStage,
    ValidationWorkflowConfig,
)
from maverick.workflows.validation import ValidationWorkflow

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def mock_fix_agent() -> MagicMock:
    """Create a mock fix agent for testing workflow behavior.

    This demonstrates how to mock agent dependencies for workflow testing.
    The mock agent can be configured to simulate success/failure scenarios.

    Returns:
        Mock agent with execute() method configured.

    Example:
        >>> mock_agent = mock_fix_agent()
        >>> mock_agent.execute.return_value = AsyncMock()
        >>> # Agent can now be injected into workflow
    """
    mock_agent = MagicMock()
    mock_agent.execute = AsyncMock()
    return mock_agent


@pytest.fixture
def sample_validation_stages() -> list[ValidationStage]:
    """Create sample validation stages for testing.

    This demonstrates how to create test data for workflow testing.
    Stages are simple and non-failing for baseline tests.

    Returns:
        List of ValidationStage objects for testing.
    """
    return [
        ValidationStage(
            name="format",
            command=["echo", "formatting"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
        ValidationStage(
            name="lint",
            command=["echo", "linting"],
            fixable=True,
            max_fix_attempts=2,
            timeout_seconds=10.0,
        ),
    ]


# =============================================================================
# Configuration Validation Tests
# =============================================================================


class TestWorkflowConfiguration:
    """Example tests for workflow configuration validation.

    Demonstrates:
    - Testing Pydantic model validation
    - Testing default values
    - Testing invalid configurations
    - Testing frozen/immutable configurations
    """

    def test_config_default_values(self) -> None:
        """Test ValidationWorkflowConfig default values.

        Demonstrates:
        - Creating config with no arguments
        - Verifying default values match specification
        - Testing boolean and path defaults
        """
        config = ValidationWorkflowConfig()

        assert config.stop_on_failure is False
        assert config.dry_run is False
        assert config.cwd is None

    def test_config_custom_values(self) -> None:
        """Test ValidationWorkflowConfig accepts custom values.

        Demonstrates:
        - Creating config with custom values
        - Verifying all fields can be set
        - Testing Path type handling
        """
        config = ValidationWorkflowConfig(
            stop_on_failure=False,
            dry_run=True,
            cwd=Path("/tmp/test"),
        )

        assert config.stop_on_failure is False
        assert config.dry_run is True
        assert config.cwd == Path("/tmp/test")

    def test_config_immutability(self) -> None:
        """Test ValidationWorkflowConfig mutability.

        Demonstrates:
        - Testing that config can be modified (not frozen)
        - Note: ValidationWorkflowConfig is NOT frozen in current implementation
        - This pattern shows how to test mutable configs
        """
        config = ValidationWorkflowConfig(stop_on_failure=True)

        # ValidationWorkflowConfig is not frozen, so modification is allowed
        config.stop_on_failure = False
        assert config.stop_on_failure is False


# =============================================================================
# Workflow Initialization Tests
# =============================================================================


class TestWorkflowInitialization:
    """Example tests for workflow initialization.

    Demonstrates:
    - Testing workflow constructor
    - Testing with/without optional dependencies
    - Testing configuration injection
    """

    def test_workflow_init_minimal(
        self, sample_validation_stages: list[ValidationStage]
    ) -> None:
        """Test workflow initialization with minimal arguments.

        Demonstrates:
        - Creating workflow with only required arguments
        - Verifying default config is created
        - Testing that fix_agent defaults to None
        """
        workflow = ValidationWorkflow(stages=sample_validation_stages)

        # Verify workflow initialized with defaults
        assert workflow._stages == sample_validation_stages
        assert workflow._fix_agent is None
        assert isinstance(workflow._config, ValidationWorkflowConfig)
        assert workflow._config.stop_on_failure is False

    def test_workflow_init_with_fix_agent(
        self,
        sample_validation_stages: list[ValidationStage],
        mock_fix_agent: MagicMock,
    ) -> None:
        """Test workflow initialization with fix agent.

        Demonstrates:
        - Injecting mock agent dependency
        - Verifying agent is stored correctly
        - Testing dependency injection pattern
        """
        workflow = ValidationWorkflow(
            stages=sample_validation_stages,
            fix_agent=mock_fix_agent,
        )

        assert workflow._fix_agent == mock_fix_agent

    def test_workflow_init_with_custom_config(
        self, sample_validation_stages: list[ValidationStage]
    ) -> None:
        """Test workflow initialization with custom config.

        Demonstrates:
        - Creating custom configuration
        - Injecting config into workflow
        - Verifying config is used instead of default
        """
        custom_config = ValidationWorkflowConfig(
            stop_on_failure=False,
            dry_run=True,
        )

        workflow = ValidationWorkflow(
            stages=sample_validation_stages,
            config=custom_config,
        )

        assert workflow._config == custom_config
        assert workflow._config.stop_on_failure is False
        assert workflow._config.dry_run is True


# =============================================================================
# State Management Tests
# =============================================================================


class TestWorkflowStateMethods:
    """Example tests for workflow state management methods.

    Demonstrates:
    - Testing state getter/setter methods
    - Testing cancellation mechanism
    - Testing result retrieval
    """

    def test_cancel_sets_event(
        self, sample_validation_stages: list[ValidationStage]
    ) -> None:
        """Test workflow cancel() method sets cancellation event.

        Demonstrates:
        - Testing workflow cancellation mechanism
        - Verifying internal state changes
        - Testing cooperative cancellation pattern
        """
        workflow = ValidationWorkflow(stages=sample_validation_stages)

        # Initially, cancel event should not be set
        assert not workflow._cancel_event.is_set()

        # Call cancel()
        workflow.cancel()

        # Verify cancel event is now set
        assert workflow._cancel_event.is_set()

    def test_get_result_before_run_raises(
        self, sample_validation_stages: list[ValidationStage]
    ) -> None:
        """Test get_result() raises if called before workflow runs.

        Demonstrates:
        - Testing precondition validation
        - Verifying error messages are descriptive
        - Testing RuntimeError for invalid state
        """
        workflow = ValidationWorkflow(stages=sample_validation_stages)

        # Calling get_result() before run() should raise RuntimeError
        with pytest.raises(RuntimeError, match="Workflow has not completed"):
            workflow.get_result()


# =============================================================================
# Method Isolation Tests (Mocking Dependencies)
# =============================================================================


class TestCommandExecution:
    """Example tests for command execution method in isolation.

    Demonstrates:
    - Testing internal methods with mocked subprocess
    - Testing timeout handling
    - Testing command not found scenarios
    - Testing error handling
    """

    @pytest.mark.asyncio
    async def test_execute_command_success(
        self, sample_validation_stages: list[ValidationStage]
    ) -> None:
        """Test _execute_command() with successful command.

        Demonstrates:
        - Mocking asyncio.create_subprocess_exec
        - Testing successful command execution path
        - Verifying stdout/stderr capture
        - Asserting correct return code
        """
        workflow = ValidationWorkflow(stages=sample_validation_stages)
        stage = sample_validation_stages[0]

        # Mock subprocess to simulate successful command
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate = AsyncMock(
            return_value=(b"Success output", b"")
        )

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await workflow._execute_command(stage)

        # Verify result
        assert result.return_code == 0
        assert result.stdout == "Success output"
        assert result.stderr == ""
        assert result.error is None
        assert result.timed_out is False
        assert result.command_not_found is False

    @pytest.mark.asyncio
    async def test_execute_command_timeout(
        self, sample_validation_stages: list[ValidationStage]
    ) -> None:
        """Test _execute_command() handles timeout correctly.

        Demonstrates:
        - Simulating timeout with AsyncMock side_effect
        - Testing timeout error handling
        - Verifying process is killed on timeout
        - Checking timeout flag in result
        """
        workflow = ValidationWorkflow(stages=sample_validation_stages)
        stage = sample_validation_stages[0]

        # Mock subprocess to simulate timeout
        mock_process = MagicMock()
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_process.kill = MagicMock()
        mock_process.wait = AsyncMock()
        mock_process.returncode = None

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            result = await workflow._execute_command(stage)

        # Verify timeout was handled
        assert result.timed_out is True
        assert result.return_code == -1
        assert "timed out" in result.error.lower()
        mock_process.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_command_not_found(
        self, sample_validation_stages: list[ValidationStage]
    ) -> None:
        """Test _execute_command() handles command not found.

        Demonstrates:
        - Simulating FileNotFoundError
        - Testing command_not_found flag
        - Verifying error message content
        """
        workflow = ValidationWorkflow(stages=sample_validation_stages)
        stage = sample_validation_stages[0]

        # Mock subprocess to raise FileNotFoundError
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("missing_command"),
        ):
            result = await workflow._execute_command(stage)

        # Verify command not found was handled
        assert result.command_not_found is True
        assert result.return_code == -1
        assert "Command not found" in result.error


# =============================================================================
# Fix Agent Integration Tests
# =============================================================================


class TestFixAgentInvocation:
    """Example tests for fix agent invocation logic.

    Demonstrates:
    - Testing agent invocation in isolation
    - Mocking agent responses
    - Testing error handling in agent calls
    """

    @pytest.mark.asyncio
    async def test_invoke_fix_agent_success(
        self,
        sample_validation_stages: list[ValidationStage],
        mock_fix_agent: MagicMock,
    ) -> None:
        """Test _invoke_fix_agent() with successful fix.

        Demonstrates:
        - Mocking agent.execute() call
        - Verifying agent is called with correct arguments
        - Testing successful fix agent invocation
        """
        workflow = ValidationWorkflow(
            stages=sample_validation_stages,
            fix_agent=mock_fix_agent,
        )
        stage = sample_validation_stages[1]  # fixable stage
        error_output = "Some error output"

        # Configure mock to succeed
        mock_fix_agent.execute.return_value = AsyncMock()

        result = await workflow._invoke_fix_agent(stage, error_output)

        # Verify agent was called correctly
        assert result is True
        mock_fix_agent.execute.assert_called_once()
        call_kwargs = mock_fix_agent.execute.call_args.kwargs
        assert call_kwargs["stage_name"] == stage.name
        assert call_kwargs["command"] == stage.command
        assert call_kwargs["error_output"] == error_output

    @pytest.mark.asyncio
    async def test_invoke_fix_agent_no_agent(
        self, sample_validation_stages: list[ValidationStage]
    ) -> None:
        """Test _invoke_fix_agent() when no agent is configured.

        Demonstrates:
        - Testing behavior when dependency is None
        - Verifying early return when agent unavailable
        """
        workflow = ValidationWorkflow(
            stages=sample_validation_stages,
            fix_agent=None,
        )
        stage = sample_validation_stages[1]

        result = await workflow._invoke_fix_agent(stage, "error")

        # Should return False when no agent available
        assert result is False

    @pytest.mark.asyncio
    async def test_invoke_fix_agent_exception(
        self,
        sample_validation_stages: list[ValidationStage],
        mock_fix_agent: MagicMock,
    ) -> None:
        """Test _invoke_fix_agent() handles agent exceptions.

        Demonstrates:
        - Mocking agent to raise exception
        - Testing error handling in agent invocation
        - Verifying exception is caught and logged
        """
        workflow = ValidationWorkflow(
            stages=sample_validation_stages,
            fix_agent=mock_fix_agent,
        )
        stage = sample_validation_stages[1]

        # Configure mock to raise exception
        mock_fix_agent.execute.side_effect = RuntimeError("Agent failed")

        result = await workflow._invoke_fix_agent(stage, "error")

        # Should return False and log error (not raise)
        assert result is False


# =============================================================================
# Stage Validation Tests
# =============================================================================


class TestStageValidation:
    """Example tests for stage configuration validation.

    Demonstrates:
    - Testing ValidationStage model validation
    - Testing field constraints
    - Testing invalid configurations
    """

    def test_stage_requires_name(self) -> None:
        """Test ValidationStage requires non-empty name.

        Demonstrates:
        - Testing Pydantic field validation
        - Verifying min_length constraint
        - Catching ValidationError for invalid input
        """
        with pytest.raises(ValidationError, match="name"):
            ValidationStage(
                name="",  # Invalid: empty name
                command=["echo", "test"],
                fixable=False,
                max_fix_attempts=0,
                timeout_seconds=10.0,
            )

    def test_stage_requires_command(self) -> None:
        """Test ValidationStage requires non-empty command.

        Demonstrates:
        - Testing list field validation
        - Verifying min_length constraint on list
        """
        with pytest.raises(ValidationError, match="command"):
            ValidationStage(
                name="test",
                command=[],  # Invalid: empty command
                fixable=False,
                max_fix_attempts=0,
                timeout_seconds=10.0,
            )

    def test_stage_timeout_must_be_positive(self) -> None:
        """Test ValidationStage requires positive timeout.

        Demonstrates:
        - Testing numeric field constraints
        - Verifying gt (greater than) validation
        """
        with pytest.raises(ValidationError, match="timeout"):
            ValidationStage(
                name="test",
                command=["echo", "test"],
                fixable=False,
                max_fix_attempts=0,
                timeout_seconds=0.0,  # Invalid: must be > 0
            )

    def test_stage_is_fixable_property(self) -> None:
        """Test ValidationStage.is_fixable property logic.

        Demonstrates:
        - Testing computed properties
        - Verifying boolean logic
        - Testing edge cases (fixable=True but max_fix_attempts=0)
        """
        # Stage with fixable=True AND max_fix_attempts > 0
        stage1 = ValidationStage(
            name="test",
            command=["echo", "test"],
            fixable=True,
            max_fix_attempts=2,
            timeout_seconds=10.0,
        )
        assert stage1.is_fixable is True

        # Stage with fixable=False
        stage2 = ValidationStage(
            name="test",
            command=["echo", "test"],
            fixable=False,
            max_fix_attempts=2,
            timeout_seconds=10.0,
        )
        assert stage2.is_fixable is False

        # Stage with fixable=True but max_fix_attempts=0
        stage3 = ValidationStage(
            name="test",
            command=["echo", "test"],
            fixable=True,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        )
        assert stage3.is_fixable is False


# =============================================================================
# Dry-Run Mode Tests
# =============================================================================


class TestDryRunMode:
    """Example tests for dry-run mode behavior.

    Demonstrates:
    - Testing workflow behavior in dry-run mode
    - Verifying commands are not executed
    - Testing metadata in results
    """

    @pytest.mark.asyncio
    async def test_dry_run_skips_execution(
        self, sample_validation_stages: list[ValidationStage]
    ) -> None:
        """Test dry-run mode does not execute commands.

        Demonstrates:
        - Creating workflow with dry_run=True config
        - Verifying subprocess is not called
        - Testing that results show dry-run status
        """
        config = ValidationWorkflowConfig(dry_run=True)
        workflow = ValidationWorkflow(
            stages=sample_validation_stages,
            config=config,
        )

        # Track if subprocess was called
        with patch("asyncio.create_subprocess_exec") as mock_exec:
            # Run workflow
            async for _ in workflow.run():
                pass

            # Verify subprocess was NOT called in dry-run mode
            mock_exec.assert_not_called()

        # Verify result shows dry-run
        result = workflow.get_result()
        assert result.metadata.get("dry_run") is True
        assert result.success is True
        assert all(
            "[DRY-RUN]" in stage_result.output
            for stage_result in result.stage_results
        )


# =============================================================================
# Key Testing Patterns Summary
# =============================================================================
#
# 1. WORKFLOW INITIALIZATION TESTING:
#    - Test with minimal required arguments
#    - Test with all optional dependencies (agents, configs)
#    - Verify default values are set correctly
#    - Use fixtures for common test data (stages, configs)
#
# 2. CONFIGURATION VALIDATION:
#    - Test Pydantic model constraints (min/max, types)
#    - Test immutability (frozen=True)
#    - Test default values
#    - Test invalid configurations raise ValidationError
#
# 3. METHOD ISOLATION TESTING:
#    - Mock external dependencies (subprocess, agents)
#    - Test one method at a time
#    - Use AsyncMock for async methods
#    - Verify method calls and arguments with assert_called_once()
#
# 4. STATE MANAGEMENT:
#    - Test state transition methods (cancel, get_result)
#    - Test preconditions (get_result before run)
#    - Verify internal state flags (_cancel_event, _result)
#
# 5. ERROR HANDLING:
#    - Mock exceptions in dependencies
#    - Test timeout scenarios
#    - Test command not found scenarios
#    - Verify errors are caught and handled gracefully
#
# 6. DEPENDENCY INJECTION:
#    - Create mock fixtures for agent dependencies
#    - Test behavior with and without optional deps
#    - Verify agents are called with correct arguments
#
# 7. DRY-RUN AND SPECIAL MODES:
#    - Test dry-run mode skips execution
#    - Verify metadata in results
#    - Test that dry-run results show appropriate status
#
# =============================================================================
