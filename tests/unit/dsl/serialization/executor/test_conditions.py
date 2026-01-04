"""Tests for conditions module expression resolution.

This module tests:
1. resolve_expressions handles all step types correctly
2. Template expressions are resolved in checkpoint_id fields
3. Iteration context (index, item) is available in expressions
"""

from __future__ import annotations

from maverick.dsl.context import WorkflowContext
from maverick.dsl.results import StepResult
from maverick.dsl.serialization.executor.conditions import resolve_expressions
from maverick.dsl.serialization.schema import (
    CheckpointStepRecord,
    PythonStepRecord,
)
from maverick.dsl.types import StepType


class TestResolveExpressionsCheckpoint:
    """Tests for resolve_expressions with CheckpointStepRecord."""

    def test_resolve_checkpoint_id_with_index_expression(self) -> None:
        """Verify checkpoint_id with ${{ index }} expression is resolved."""
        # Create a checkpoint step with templated checkpoint_id
        step = CheckpointStepRecord(
            name="checkpoint_phase",
            checkpoint_id="phase_${{ index }}_complete",
        )

        # Create context with iteration_context (as would be set by loop handler)
        context = WorkflowContext(
            inputs={},
            iteration_context={"item": "phase_1", "index": 0},
        )

        # Resolve expressions
        resolved = resolve_expressions(step, context)

        # Verify checkpoint_id was resolved with the index value
        assert resolved["checkpoint_id"] == "phase_0_complete"

    def test_resolve_checkpoint_id_with_item_expression(self) -> None:
        """Verify checkpoint_id with ${{ item }} expression is resolved."""
        step = CheckpointStepRecord(
            name="checkpoint_phase",
            checkpoint_id="checkpoint_${{ item }}",
        )

        context = WorkflowContext(
            inputs={},
            iteration_context={"item": "setup", "index": 0},
        )

        resolved = resolve_expressions(step, context)

        assert resolved["checkpoint_id"] == "checkpoint_setup"

    def test_resolve_checkpoint_id_with_input_expression(self) -> None:
        """Verify checkpoint_id with ${{ inputs.* }} expression is resolved."""
        step = CheckpointStepRecord(
            name="checkpoint_branch",
            checkpoint_id="branch_${{ inputs.branch_name }}_done",
        )

        context = WorkflowContext(
            inputs={"branch_name": "feature-123"},
        )

        resolved = resolve_expressions(step, context)

        assert resolved["checkpoint_id"] == "branch_feature-123_done"

    def test_resolve_checkpoint_id_static_string(self) -> None:
        """Verify static checkpoint_id is passed through unchanged."""
        step = CheckpointStepRecord(
            name="checkpoint_final",
            checkpoint_id="implementation_complete",
        )

        context = WorkflowContext(inputs={})

        resolved = resolve_expressions(step, context)

        assert resolved["checkpoint_id"] == "implementation_complete"

    def test_resolve_checkpoint_id_none_returns_empty(self) -> None:
        """Verify None checkpoint_id results in empty resolved dict."""
        step = CheckpointStepRecord(
            name="checkpoint_auto",
            checkpoint_id=None,  # Will use step name as fallback in handler
        )

        context = WorkflowContext(inputs={})

        resolved = resolve_expressions(step, context)

        # No checkpoint_id key when original is None
        assert "checkpoint_id" not in resolved

    def test_resolve_checkpoint_id_with_step_output(self) -> None:
        """Verify checkpoint_id can reference step outputs."""
        step = CheckpointStepRecord(
            name="checkpoint_dynamic",
            checkpoint_id="after_${{ steps.init.output.branch_name }}",
        )

        # Create context with step results
        context = WorkflowContext(
            inputs={},
            results={
                "init": StepResult(
                    name="init",
                    step_type=StepType.PYTHON,
                    success=True,
                    output={"branch_name": "main"},
                    duration_ms=10,
                )
            },
        )

        resolved = resolve_expressions(step, context)

        assert resolved["checkpoint_id"] == "after_main"


class TestResolveExpressionsIterationContext:
    """Tests for resolve_expressions with iteration context."""

    def test_python_step_with_iteration_context(self) -> None:
        """Verify Python step kwargs can use iteration context."""
        step = PythonStepRecord(
            name="process_item",
            action="process",
            kwargs={
                "item_name": "${{ item }}",
                "position": "${{ index }}",
            },
        )

        context = WorkflowContext(
            inputs={},
            iteration_context={"item": "task_A", "index": 2},
        )

        resolved = resolve_expressions(step, context)

        assert resolved["item_name"] == "task_A"
        assert resolved["position"] == 2  # Numeric index preserved
