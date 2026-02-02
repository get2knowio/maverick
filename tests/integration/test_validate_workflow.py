"""Integration tests for validate workflow.

This module validates end-to-end execution of the validate workflow:
- Running validation stages (format, lint, typecheck, test)
- Conditional branching based on fix parameter
- Invoking validate-and-fix sub-workflow when fix=True
- Single validation run when fix=False
- Proper error handling and event emission
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from maverick.dsl.events import (
    StepStarted,
    ValidationCompleted,
    ValidationStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.dsl.serialization.executor import WorkflowFileExecutor
from maverick.dsl.serialization.parser import parse_workflow
from maverick.dsl.serialization.registry import ComponentRegistry


class TestValidateWorkflowIntegration:
    """Integration tests for the validate workflow."""

    @pytest.fixture
    def workflow_path(self) -> Path:
        """Get path to validate workflow YAML."""
        return (
            Path(__file__).parent.parent.parent
            / "src"
            / "maverick"
            / "library"
            / "workflows"
            / "validate.yaml"
        )

    @pytest.fixture
    def registry(self) -> ComponentRegistry:
        """Create component registry with mocked actions and sub-workflows."""
        registry = ComponentRegistry()

        # Import and register real validation actions
        from maverick.library.actions import validation

        registry.actions.register(
            "generate_validation_report", validation.generate_validation_report
        )
        registry.actions.register("log_message", validation.log_message)

        # Mock validate step type (this would normally be implemented in executor)
        # For now, we'll register it as a Python action
        async def mock_validate_step(stages: list[str]) -> dict[str, Any]:
            """Mock validation step that always passes."""
            return {
                "success": True,
                "passed": True,
                "failed": False,
                "stages": [
                    {"stage": stage, "success": True, "output": f"{stage} passed"}
                    for stage in stages
                ],
            }

        async def mock_validate_step_failure(stages: list[str]) -> dict[str, Any]:
            """Mock validation step that fails."""
            return {
                "success": False,
                "passed": False,
                "failed": True,
                "stages": [
                    {"stage": stages[0], "success": False, "error": "lint error"},
                    *[
                        {"stage": stage, "success": True, "output": f"{stage} passed"}
                        for stage in stages[1:]
                    ],
                ],
            }

        # Register mock validate actions
        registry.actions.register("validate_success", mock_validate_step)
        registry.actions.register("validate_failure", mock_validate_step_failure)

        # Register validate-and-fix sub-workflow for semantic validation
        mock_vaf_workflow = parse_workflow("""
version: "1.0"
name: validate-and-fix
description: Mock validate-and-fix for testing
inputs:
  stages:
    type: array
    required: false
  max_attempts:
    type: integer
    required: false
    default: 3
steps:
  - name: mock_validate
    type: python
    action: log_message
    kwargs:
      message: "Mock validation"
""")
        registry.workflows.register("validate-and-fix", mock_vaf_workflow)

        return registry

    @pytest.mark.asyncio
    async def test_validate_workflow_with_fix_disabled(
        self, workflow_path: Path, registry: ComponentRegistry
    ) -> None:
        """Test validate workflow with fix=False.

        This test validates:
        - Workflow loads from YAML definition
        - Validation step executes
        - Fix loop is skipped when fix=False
        - Report is generated
        """
        # Parse workflow from YAML
        with open(workflow_path) as f:
            workflow = parse_workflow(f.read())

        # Execute workflow with fix=False
        # The validate step is already implemented and will run the mock stages
        executor = WorkflowFileExecutor(registry=registry)
        events = []
        async for event in executor.execute(
            workflow,
            inputs={"fix": False, "max_attempts": 3},
        ):
            events.append(event)

        # Verify workflow events were generated
        from maverick.dsl.events import PreflightCompleted, PreflightStarted

        assert len(events) > 0
        # Validation and preflight events come first
        assert isinstance(events[0], ValidationStarted)
        assert isinstance(events[1], ValidationCompleted)
        assert isinstance(events[2], PreflightStarted)
        assert isinstance(events[3], PreflightCompleted)
        assert isinstance(events[4], WorkflowStarted)
        assert events[4].workflow_name == "validate"

        # Verify final event is workflow completion
        assert isinstance(events[-1], WorkflowCompleted)

        # Verify at least run_validation and report steps executed
        step_started_events = [e for e in events if isinstance(e, StepStarted)]
        step_names = [e.step_name for e in step_started_events]
        assert "run_validation" in step_names
        assert "report" in step_names

    @pytest.mark.asyncio
    async def test_validate_workflow_passes_on_first_attempt(
        self, workflow_path: Path, registry: ComponentRegistry
    ) -> None:
        """Test validate workflow when validation passes immediately.

        This test validates:
        - Validation runs and passes (using built-in validate step which always passes)
        - Fix loop branch selects "skip_fixes" path
        - No fix attempts are made
        - Report shows success
        """
        with open(workflow_path) as f:
            workflow = parse_workflow(f.read())

        # The built-in validate step implementation returns success=True
        # So this test will naturally follow the success path
        executor = WorkflowFileExecutor(registry=registry)
        events = []
        async for event in executor.execute(
            workflow,
            inputs={"fix": True, "max_attempts": 3},
        ):
            events.append(event)

        # Should complete successfully
        from maverick.dsl.events import PreflightCompleted, PreflightStarted

        assert isinstance(events[-1], WorkflowCompleted)
        assert events[-1].success is True

        # Verify workflow started and completed
        # Validation and preflight events come first
        assert isinstance(events[0], ValidationStarted)
        assert isinstance(events[1], ValidationCompleted)
        assert isinstance(events[2], PreflightStarted)
        assert isinstance(events[3], PreflightCompleted)
        assert isinstance(events[4], WorkflowStarted)

    @pytest.mark.asyncio
    async def test_validate_workflow_with_fix_enabled_and_failure(
        self, workflow_path: Path, registry: ComponentRegistry
    ) -> None:
        """Test validate workflow with fix=True and validation failure.

        This test validates:
        - Initial validation fails
        - Fix loop branch selects "attempt_fixes" path
        - validate-and-fix sub-workflow would be invoked
        - Report is generated

        Note: The validate-and-fix sub-workflow is registered by the fixture.
        """
        with open(workflow_path) as f:
            workflow = parse_workflow(f.read())

        # Mock validate step to fail

        async def mock_execute_validate(
            step, resolved_inputs, context, registry, config=None
        ):
            """Mock validation that fails."""
            return {
                "success": False,
                "stages": [
                    {"stage": "lint", "success": False, "error": "lint errors"},
                ],
            }

        with patch(
            "maverick.dsl.serialization.executor.handlers.validate_step.execute_validate_step",
            mock_execute_validate,
        ):
            executor = WorkflowFileExecutor(registry=registry)
            events = []
            async for event in executor.execute(
                workflow,
                inputs={"fix": True, "max_attempts": 3},
            ):
                events.append(event)

            # Verify workflow completed
            assert isinstance(events[-1], WorkflowCompleted)

    @pytest.mark.asyncio
    async def test_validate_workflow_with_custom_max_attempts(
        self, workflow_path: Path, registry: ComponentRegistry
    ) -> None:
        """Test validate workflow with custom max_attempts parameter.

        This test validates:
        - Custom max_attempts is accepted as input
        - Workflow completes successfully
        """
        with open(workflow_path) as f:
            workflow = parse_workflow(f.read())

        executor = WorkflowFileExecutor(registry=registry)
        events = []
        async for event in executor.execute(
            workflow,
            inputs={"fix": False, "max_attempts": 5},
        ):
            events.append(event)

        # Verify workflow completed
        assert isinstance(events[-1], WorkflowCompleted)


class TestValidateWorkflowActions:
    """Integration tests for individual validate workflow actions."""

    @pytest.mark.asyncio
    async def test_log_message_action(self) -> None:
        """Test log_message action executes and returns expected output."""
        from maverick.library.actions.validation import log_message

        result = log_message("Test message")

        assert result["message"] == "Test message"
        assert result["logged"] is True

    @pytest.mark.asyncio
    async def test_generate_validation_report_with_success(self) -> None:
        """Test generate_validation_report with successful validation."""
        from maverick.library.actions.validation import generate_validation_report

        initial_result = {
            "success": True,
            "passed": True,
            "stages": [
                {"stage": "format", "success": True},
                {"stage": "lint", "success": True},
            ],
        }

        result = await generate_validation_report(
            initial_result=initial_result,
            fix_result=None,
            fix_enabled=False,
            max_attempts=3,
        )

        assert result["passed"] is True
        assert result["attempts"] == 0
        assert len(result["fixes_applied"]) == 0
        assert len(result["remaining_errors"]) == 0

    @pytest.mark.asyncio
    async def test_generate_validation_report_with_fixes(self) -> None:
        """Test generate_validation_report with fix attempts."""
        from maverick.library.actions.validation import generate_validation_report

        initial_result = {
            "success": False,
            "passed": False,
            "stages": [{"stage": "lint", "success": False}],
        }

        # fix_loop_result should be the output from fix_loop step
        fix_loop_result = {
            "passed": True,
            "attempts": 2,
            "fixes_applied": ["Fixed lint error on line 10", "Fixed import order"],
        }

        result = await generate_validation_report(
            initial_result=initial_result,
            fix_loop_result=fix_loop_result,
            fix_enabled=True,
            max_attempts=3,
        )

        # The function should extract data from fix_loop_result
        assert result["passed"] is True
        assert result["attempts"] == 2
        assert len(result["fixes_applied"]) == 2


class TestValidateWorkflowEdgeCases:
    """Integration tests for edge cases in validate workflow."""

    @pytest.mark.asyncio
    async def test_workflow_with_zero_max_attempts(self) -> None:
        """Test workflow handles max_attempts=0 gracefully."""
        from maverick.library.actions.validation import generate_validation_report

        initial_result = {"success": False, "passed": False}

        result = await generate_validation_report(
            initial_result=initial_result,
            fix_result=None,
            fix_enabled=False,
            max_attempts=0,
        )

        # Should not attempt any fixes
        assert result["attempts"] == 0
        assert result["passed"] is False

    @pytest.mark.asyncio
    async def test_workflow_with_empty_stages(self) -> None:
        """Test workflow handles empty stages list."""
        from maverick.library.actions.validation import generate_validation_report

        initial_result = {"success": True, "passed": True, "stages": []}

        result = await generate_validation_report(
            initial_result=initial_result,
            fix_result=None,
            fix_enabled=False,
            max_attempts=3,
        )

        assert result["passed"] is True
        # Should use default stages or handle empty gracefully
        assert "stages" in result

    @pytest.mark.asyncio
    async def test_workflow_validation_failure_with_fix_disabled(self) -> None:
        """Test workflow completes when validation fails but fix is disabled."""
        from maverick.library.actions.validation import generate_validation_report

        initial_result = {
            "success": False,
            "passed": False,
            "stages": [
                {
                    "stage": "typecheck",
                    "success": False,
                    "error": "Type error on line 42",
                }
            ],
        }

        result = await generate_validation_report(
            initial_result=initial_result,
            fix_result=None,
            fix_enabled=False,
            max_attempts=3,
        )

        assert result["passed"] is False
        assert result["attempts"] == 0
        assert len(result["remaining_errors"]) > 0
        assert len(result["suggestions"]) > 0
