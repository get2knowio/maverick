"""Unit tests for ValidateStep class.

This module tests the ValidateStep class that executes validation stages
with retry logic and optional failure recovery steps.

Test Coverage:
- T048: Stage resolution (explicit list, None, string key, errors)
- T049: Retry logic (0 retries, N retries, exhaustion, early success)
- T050: On-failure step execution (runs before retry, receives context, failures)
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from maverick.dsl import StepResult, StepType, WorkflowContext
from maverick.dsl.steps.python import PythonStep
from maverick.dsl.steps.validate import ValidateStep


class MockValidationResult:
    """Mock validation result object."""

    def __init__(self, success: bool, stages: list[str] | None = None) -> None:
        """Initialize mock validation result.

        Args:
            success: Whether validation succeeded.
            stages: Optional list of stages that were run.
        """
        self.success = success
        self.stages = stages or []


class MockConfig:
    """Mock configuration object with validation support."""

    def __init__(
        self,
        validation_stages: list[str] | None = None,
        custom_stages: list[str] | None = None,
    ) -> None:
        """Initialize mock config.

        Args:
            validation_stages: Default validation stages.
            custom_stages: Custom validation stages for key lookup.
        """
        self.validation_stages = validation_stages or ["format", "lint", "test"]
        self.custom_stages = custom_stages or ["format", "lint"]
        self.run_validation_stages = AsyncMock(
            return_value=MockValidationResult(success=True)
        )


class TestValidateStepCreation:
    """Test ValidateStep instantiation and properties."""

    def test_creation_with_minimal_fields(self) -> None:
        """Test creating ValidateStep with minimal required fields."""
        step = ValidateStep(name="validate")

        assert step.name == "validate"
        assert step.stages is None
        assert step.retry == 3
        assert step.on_failure is None
        assert step.step_type == StepType.VALIDATE

    def test_creation_with_explicit_stages_list(self) -> None:
        """Test creating ValidateStep with explicit list of stages."""
        stages = ["format", "lint", "test"]
        step = ValidateStep(name="validate", stages=stages)

        assert step.stages == stages
        assert step.retry == 3

    def test_creation_with_string_config_key(self) -> None:
        """Test creating ValidateStep with string config key."""
        step = ValidateStep(name="validate", stages="custom_stages")

        assert step.stages == "custom_stages"
        assert isinstance(step.stages, str)

    def test_creation_with_custom_retry(self) -> None:
        """Test creating ValidateStep with custom retry count."""
        step = ValidateStep(name="validate", retry=5)

        assert step.retry == 5

    def test_creation_with_zero_retries(self) -> None:
        """Test creating ValidateStep with no retries."""
        step = ValidateStep(name="validate", retry=0)

        assert step.retry == 0

    def test_creation_with_on_failure_step(self) -> None:
        """Test creating ValidateStep with on_failure step."""
        on_failure = PythonStep(name="auto_fix", action=lambda: None)
        step = ValidateStep(name="validate", on_failure=on_failure)

        assert step.on_failure is on_failure

    def test_validate_step_is_frozen(self) -> None:
        """Test that ValidateStep is immutable (frozen=True)."""
        step = ValidateStep(name="validate")

        with pytest.raises((AttributeError, TypeError)):
            step.name = "modified"

    def test_validate_step_has_slots(self) -> None:
        """Test that ValidateStep declares __slots__ for memory efficiency."""
        ValidateStep(name="validate")

        assert hasattr(ValidateStep, "__slots__")


class TestValidateStepToDict:
    """Test ValidateStep.to_dict() serialization."""

    def test_to_dict_returns_expected_structure(self) -> None:
        """Test that to_dict() returns correct structure."""
        step = ValidateStep(
            name="validate",
            stages=["format", "lint"],
            retry=2,
        )

        result = step.to_dict()

        assert result["name"] == "validate"
        assert result["step_type"] == "validate"
        assert result["stages"] == ["format", "lint"]
        assert result["retry"] == 2
        assert result["has_on_failure"] is False

    def test_to_dict_with_on_failure(self) -> None:
        """Test to_dict() with on_failure step present."""
        on_failure = PythonStep(name="auto_fix", action=lambda: None)
        step = ValidateStep(name="validate", on_failure=on_failure)

        result = step.to_dict()

        assert result["has_on_failure"] is True

    def test_to_dict_with_string_stages(self) -> None:
        """Test to_dict() with string config key."""
        step = ValidateStep(name="validate", stages="custom_stages")

        result = step.to_dict()

        assert result["stages"] == "custom_stages"

    def test_to_dict_with_none_stages(self) -> None:
        """Test to_dict() with None stages (uses default)."""
        step = ValidateStep(name="validate", stages=None)

        result = step.to_dict()

        assert result["stages"] is None


class TestValidateStepStagesResolution:
    """Test T048: ValidateStep stage resolution logic."""

    @pytest.mark.asyncio
    async def test_execute_with_explicit_list_of_stages(self) -> None:
        """Test validation runs with explicit list of stages."""
        config = MockConfig()
        context = WorkflowContext(inputs={}, config=config)

        explicit_stages = ["format", "lint"]
        step = ValidateStep(name="validate", stages=explicit_stages, retry=0)

        result = await step.execute(context)

        assert result.success is True
        config.run_validation_stages.assert_called_once_with(explicit_stages)

    @pytest.mark.asyncio
    async def test_execute_with_none_uses_default_stages(self) -> None:
        """Test validation with None uses default stages from config."""
        default_stages = ["format", "lint", "test"]
        config = MockConfig(validation_stages=default_stages)
        context = WorkflowContext(inputs={}, config=config)

        step = ValidateStep(name="validate", stages=None, retry=0)

        result = await step.execute(context)

        assert result.success is True
        config.run_validation_stages.assert_called_once_with(default_stages)

    @pytest.mark.asyncio
    async def test_execute_with_string_key_looks_up_in_config(self) -> None:
        """Test validation with string key looks up stages from config."""
        custom_stages = ["format", "lint"]
        config = MockConfig(custom_stages=custom_stages)
        context = WorkflowContext(inputs={}, config=config)

        step = ValidateStep(name="validate", stages="custom_stages", retry=0)

        result = await step.execute(context)

        assert result.success is True
        config.run_validation_stages.assert_called_once_with(custom_stages)

    @pytest.mark.asyncio
    async def test_execute_returns_failed_result_if_string_key_not_in_config(
        self,
    ) -> None:
        """Test returns failed StepResult if string key not found in config."""
        config = MockConfig()
        context = WorkflowContext(inputs={}, config=config)

        step = ValidateStep(name="validate", stages="nonexistent_key", retry=0)

        result = await step.execute(context)

        assert result.success is False
        assert result.output is None
        assert result.error is not None
        assert "nonexistent_key" in result.error
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_with_no_config_returns_empty_stages(self) -> None:
        """Test validation with no config returns empty stages list."""
        context = WorkflowContext(inputs={}, config=None)

        step = ValidateStep(name="validate", stages=None, retry=0)

        result = await step.execute(context)

        # No config.run_validation_stages, so treated as success
        assert result.success is True


class TestValidateStepRetryLogic:
    """Test T049: ValidateStep retry logic."""

    @pytest.mark.asyncio
    async def test_retry_zero_no_retries_on_failure(self) -> None:
        """Test retry=0 means no retries, on_failure never runs."""
        config = MockConfig()
        config.run_validation_stages = AsyncMock(
            return_value=MockValidationResult(success=False)
        )
        context = WorkflowContext(inputs={}, config=config)

        on_failure_called = []

        async def on_failure_action() -> None:
            on_failure_called.append(True)

        on_failure_step = PythonStep(name="on_failure", action=on_failure_action)
        step = ValidateStep(
            name="validate",
            stages=["format"],
            retry=0,
            on_failure=on_failure_step,
        )

        result = await step.execute(context)

        assert result.success is False
        assert config.run_validation_stages.call_count == 1
        assert len(on_failure_called) == 0  # on_failure should never run

    @pytest.mark.asyncio
    async def test_retry_one_allows_one_retry_attempt(self) -> None:
        """Test retry=1 allows one retry attempt."""
        config = MockConfig()
        config.run_validation_stages = AsyncMock(
            return_value=MockValidationResult(success=False)
        )
        context = WorkflowContext(inputs={}, config=config)

        step = ValidateStep(name="validate", stages=["format"], retry=1)

        result = await step.execute(context)

        assert result.success is False
        # First attempt + 1 retry = 2 total calls
        assert config.run_validation_stages.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_n_exhausts_all_retries(self) -> None:
        """Test retry=N exhausts all N retry attempts."""
        config = MockConfig()
        config.run_validation_stages = AsyncMock(
            return_value=MockValidationResult(success=False)
        )
        context = WorkflowContext(inputs={}, config=config)

        step = ValidateStep(name="validate", stages=["format"], retry=5)

        result = await step.execute(context)

        assert result.success is False
        # First attempt + 5 retries = 6 total calls
        assert config.run_validation_stages.call_count == 6
        assert "after 5 retries" in result.error

    @pytest.mark.asyncio
    async def test_validation_passes_on_first_try_no_retries_needed(self) -> None:
        """Test validation passes on first try, no retries needed."""
        config = MockConfig()
        config.run_validation_stages = AsyncMock(
            return_value=MockValidationResult(success=True)
        )
        context = WorkflowContext(inputs={}, config=config)

        step = ValidateStep(name="validate", stages=["format"], retry=3)

        result = await step.execute(context)

        assert result.success is True
        assert config.run_validation_stages.call_count == 1

    @pytest.mark.asyncio
    async def test_validation_passes_on_second_try_one_retry_used(self) -> None:
        """Test validation passes on second try (one retry used)."""
        config = MockConfig()
        # Fail first, succeed second
        config.run_validation_stages = AsyncMock(
            side_effect=[
                MockValidationResult(success=False),
                MockValidationResult(success=True),
            ]
        )
        context = WorkflowContext(inputs={}, config=config)

        step = ValidateStep(name="validate", stages=["format"], retry=3)

        result = await step.execute(context)

        assert result.success is True
        assert config.run_validation_stages.call_count == 2

    @pytest.mark.asyncio
    async def test_validation_passes_on_last_retry(self) -> None:
        """Test validation passes on the last allowed retry."""
        config = MockConfig()
        # Fail 3 times, succeed on 4th (last retry for retry=3)
        config.run_validation_stages = AsyncMock(
            side_effect=[
                MockValidationResult(success=False),
                MockValidationResult(success=False),
                MockValidationResult(success=False),
                MockValidationResult(success=True),
            ]
        )
        context = WorkflowContext(inputs={}, config=config)

        step = ValidateStep(name="validate", stages=["format"], retry=3)

        result = await step.execute(context)

        assert result.success is True
        assert config.run_validation_stages.call_count == 4


class TestValidateStepOnFailureExecution:
    """Test T050: On-failure step execution."""

    @pytest.mark.asyncio
    async def test_on_failure_step_runs_before_each_retry(self) -> None:
        """Test on_failure step runs before each retry attempt."""
        config = MockConfig()
        config.run_validation_stages = AsyncMock(
            return_value=MockValidationResult(success=False)
        )
        context = WorkflowContext(inputs={}, config=config)

        on_failure_call_count = []

        async def on_failure_action() -> None:
            on_failure_call_count.append(True)

        on_failure_step = PythonStep(name="on_failure", action=on_failure_action)
        step = ValidateStep(
            name="validate",
            stages=["format"],
            retry=3,
            on_failure=on_failure_step,
        )

        result = await step.execute(context)

        assert result.success is False
        # Should run 3 times (once before each of 3 retries)
        assert len(on_failure_call_count) == 3

    @pytest.mark.asyncio
    async def test_on_failure_can_be_any_step_definition(self) -> None:
        """Test on_failure can be any StepDefinition (e.g., PythonStep)."""
        config = MockConfig()
        # Fail once, then succeed
        config.run_validation_stages = AsyncMock(
            side_effect=[
                MockValidationResult(success=False),
                MockValidationResult(success=True),
            ]
        )
        context = WorkflowContext(inputs={}, config=config)

        fix_applied = []

        async def auto_fix() -> str:
            fix_applied.append(True)
            return "fixed"

        on_failure_step = PythonStep(name="auto_fix", action=auto_fix)
        step = ValidateStep(
            name="validate",
            stages=["format"],
            retry=1,
            on_failure=on_failure_step,
        )

        result = await step.execute(context)

        assert result.success is True
        assert len(fix_applied) == 1

    @pytest.mark.asyncio
    async def test_on_failure_receives_workflow_context(self) -> None:
        """Test on_failure step receives workflow context."""
        config = MockConfig()
        config.run_validation_stages = AsyncMock(
            side_effect=[
                MockValidationResult(success=False),
                MockValidationResult(success=True),
            ]
        )
        context = WorkflowContext(inputs={"test_input": "value"}, config=config)

        received_context = []

        async def on_failure_action(ctx: WorkflowContext) -> None:
            received_context.append(ctx)

        # Use a custom step that accepts context
        class ContextAwareStep(PythonStep):
            """Custom step that passes context to action."""

            async def execute(self, context: WorkflowContext) -> StepResult:
                """Execute action with context."""
                # Pass context to the action
                await self.action(context)
                return StepResult(
                    name=self.name,
                    step_type=self.step_type,
                    success=True,
                    output=None,
                    duration_ms=0,
                )

        on_failure_step = ContextAwareStep(name="on_failure", action=on_failure_action)
        step = ValidateStep(
            name="validate",
            stages=["format"],
            retry=1,
            on_failure=on_failure_step,
        )

        result = await step.execute(context)

        assert result.success is True
        assert len(received_context) == 1
        assert received_context[0].inputs["test_input"] == "value"

    @pytest.mark.asyncio
    async def test_on_failure_failure_does_not_stop_retry_loop(self) -> None:
        """Test on_failure step failure doesn't stop retry loop."""
        config = MockConfig()
        config.run_validation_stages = AsyncMock(
            side_effect=[
                MockValidationResult(success=False),
                MockValidationResult(success=False),
                MockValidationResult(success=True),
            ]
        )
        context = WorkflowContext(inputs={}, config=config)

        call_count = []

        async def failing_on_failure() -> None:
            call_count.append(True)
            raise RuntimeError("Fix failed")

        on_failure_step = PythonStep(name="on_failure", action=failing_on_failure)
        step = ValidateStep(
            name="validate",
            stages=["format"],
            retry=2,
            on_failure=on_failure_step,
        )

        result = await step.execute(context)

        # Should succeed eventually despite on_failure failures
        assert result.success is True
        # on_failure should have been called 2 times (before each of 2 retries)
        assert len(call_count) == 2

    @pytest.mark.asyncio
    async def test_on_failure_not_called_when_validation_passes_first_try(
        self,
    ) -> None:
        """Test on_failure not called when validation passes on first try."""
        config = MockConfig()
        config.run_validation_stages = AsyncMock(
            return_value=MockValidationResult(success=True)
        )
        context = WorkflowContext(inputs={}, config=config)

        on_failure_called = []

        async def on_failure_action() -> None:
            on_failure_called.append(True)

        on_failure_step = PythonStep(name="on_failure", action=on_failure_action)
        step = ValidateStep(
            name="validate",
            stages=["format"],
            retry=3,
            on_failure=on_failure_step,
        )

        result = await step.execute(context)

        assert result.success is True
        assert len(on_failure_called) == 0


class TestValidateStepExecuteResult:
    """Test ValidateStep execute() return value."""

    @pytest.mark.asyncio
    async def test_execute_returns_step_result_on_success(self) -> None:
        """Test execute() returns StepResult with success=True."""
        config = MockConfig()
        stages = ["format", "lint"]
        config.run_validation_stages = AsyncMock(
            return_value=MockValidationResult(success=True, stages=stages)
        )
        context = WorkflowContext(inputs={}, config=config)

        step = ValidateStep(name="validate", stages=stages, retry=0)

        result = await step.execute(context)

        assert isinstance(result, StepResult)
        assert result.name == "validate"
        assert result.step_type == StepType.VALIDATE
        assert result.success is True
        assert result.error is None
        assert result.duration_ms >= 0
        assert result.output.success is True

    @pytest.mark.asyncio
    async def test_execute_returns_step_result_on_failure(self) -> None:
        """Test execute() returns StepResult with success=False after retries."""
        config = MockConfig()
        config.run_validation_stages = AsyncMock(
            return_value=MockValidationResult(success=False)
        )
        context = WorkflowContext(inputs={}, config=config)

        step = ValidateStep(name="validate", stages=["format"], retry=2)

        result = await step.execute(context)

        assert isinstance(result, StepResult)
        assert result.name == "validate"
        assert result.step_type == StepType.VALIDATE
        assert result.success is False
        assert result.error is not None
        assert "after 2 retries" in result.error
        assert result.duration_ms >= 0
        assert result.output.success is False

    @pytest.mark.asyncio
    async def test_execute_output_contains_validation_result(self) -> None:
        """Test execute() output contains ValidationResult object."""
        config = MockConfig()
        stages = ["format", "lint", "test"]
        validation_result = MockValidationResult(success=True, stages=stages)
        config.run_validation_stages = AsyncMock(return_value=validation_result)
        context = WorkflowContext(inputs={}, config=config)

        step = ValidateStep(name="validate", stages=stages, retry=0)

        result = await step.execute(context)

        assert result.output is validation_result
        assert result.output.success is True
        assert result.output.stages == stages

    @pytest.mark.asyncio
    async def test_execute_measures_duration(self) -> None:
        """Test execute() records execution duration in milliseconds."""
        config = MockConfig()

        async def slow_validation(stages: list[str]) -> MockValidationResult:
            import asyncio

            await asyncio.sleep(0.05)  # 50ms
            return MockValidationResult(success=True, stages=stages)

        config.run_validation_stages = slow_validation
        context = WorkflowContext(inputs={}, config=config)

        step = ValidateStep(name="validate", stages=["format"], retry=0)

        result = await step.execute(context)

        # Should be at least 50ms
        assert result.duration_ms >= 40
        assert result.duration_ms < 200  # Sanity check
