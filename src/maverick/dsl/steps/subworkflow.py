"""SubWorkflow step for the Maverick workflow DSL."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from maverick.dsl.results import StepResult, SubWorkflowInvocationResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.types import StepType

if TYPE_CHECKING:
    from maverick.dsl.context import WorkflowContext


@dataclass(frozen=True, slots=True)
class SubWorkflowStep(StepDefinition):
    """Step that executes a sub-workflow.

    Attributes:
        name: Step name.
        workflow: Decorated workflow function with __workflow_def__.
        inputs: Input arguments for sub-workflow.
        step_type: Always StepType.SUBWORKFLOW (auto-set).
    """

    name: str
    workflow: Any  # Decorated workflow function
    inputs: dict[str, Any] = field(default_factory=dict)
    step_type: StepType = field(default=StepType.SUBWORKFLOW, init=False)

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Execute sub-workflow and return result.

        Args:
            context: Workflow execution context (unused for sub-workflows).

        Returns:
            StepResult containing SubWorkflowInvocationResult as output.
        """
        from maverick.dsl.engine import WorkflowEngine

        start_time = time.perf_counter()

        try:
            # Create engine for sub-workflow
            engine = WorkflowEngine()

            # Execute sub-workflow, consuming all events
            async for _ in engine.execute(self.workflow, **self.inputs):
                pass

            # Get the result
            workflow_result = engine.get_result()

            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Create sub-workflow invocation result
            invocation_result = SubWorkflowInvocationResult(
                final_output=workflow_result.final_output,
                workflow_result=workflow_result,
            )

            return StepResult(
                name=self.name,
                step_type=self.step_type,
                success=workflow_result.success,
                output=invocation_result,
                duration_ms=duration_ms,
                error=(
                    None
                    if workflow_result.success
                    else f"Sub-workflow '{workflow_result.workflow_name}' failed"
                ),
            )

        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return StepResult(
                name=self.name,
                step_type=self.step_type,
                success=False,
                output=None,
                duration_ms=duration_ms,
                error=f"Step '{self.name}' failed: {type(e).__name__}: {e}",
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize for logging/persistence.

        Returns:
            Dictionary representation of this step.
        """
        workflow_name = (
            self.workflow.__workflow_def__.name
            if hasattr(self.workflow, "__workflow_def__")
            else str(self.workflow)
        )
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "workflow": workflow_name,
            "inputs_keys": list(self.inputs.keys()),
        }
