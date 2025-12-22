"""Agent step for the Maverick workflow DSL.

This module defines AgentStep, which invokes a MaverickAgent with
context that can be either static or dynamically built.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from maverick.dsl.context import WorkflowContext
from maverick.dsl.results import StepResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.types import ContextBuilder, StepType

if TYPE_CHECKING:
    from maverick.dsl.protocols import AgentProtocol


@dataclass(frozen=True, slots=True)
class AgentStep(StepDefinition):
    """Step that invokes a MaverickAgent with context.

    AgentStep executes a MaverickAgent as part of a workflow. The context
    can be provided as either a static dictionary or a callable that builds
    the context dynamically from the workflow state.

    Attributes:
        name: Step name.
        agent: MaverickAgent instance to execute.
        context: Either a static dict or an async callable that builds context.
        step_type: Always StepType.AGENT (auto-set, do not pass).

    Example:
        >>> # Static context
        >>> step = AgentStep(
        ...     name="review_code",
        ...     agent=code_reviewer,
        ...     context={"files": ["main.py", "utils.py"]}
        ... )
        >>>
        >>> # Dynamic context
        >>> async def build_context(wf_ctx: WorkflowContext) -> dict[str, Any]:
        ...     files = wf_ctx.results["find_files"].output
        ...     return {"files": files}
        >>> step = AgentStep(
        ...     name="review_code",
        ...     agent=code_reviewer,
        ...     context=build_context
        ... )
    """

    name: str
    agent: AgentProtocol
    context: dict[str, Any] | ContextBuilder
    step_type: StepType = field(default=StepType.AGENT, init=False)

    async def _resolve_context(
        self, workflow_context: WorkflowContext
    ) -> dict[str, Any]:
        """Resolve context - return static dict or call builder.

        Args:
            workflow_context: Current workflow execution context.

        Returns:
            Resolved context dictionary to pass to agent.

        Raises:
            Exception: If context builder fails or returns invalid type.
        """
        if callable(self.context):
            return await self.context(workflow_context)
        return self.context

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Execute agent with resolved context.

        Resolves the context (calling builder if needed), then executes
        the agent. Handles context builder failures separately from agent
        execution failures.

        Args:
            context: Workflow execution context.

        Returns:
            StepResult with success=True and output=agent_result on success,
            or success=False and error message on failure.
        """
        start_time = time.perf_counter()

        try:
            # Resolve context (may call builder)
            resolved_context = await self._resolve_context(context)
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return StepResult(
                name=self.name,
                step_type=self.step_type,
                success=False,
                output=None,
                duration_ms=duration_ms,
                error=(
                    f"Context builder for step '{self.name}' failed: "
                    f"{type(e).__name__}: {e}"
                ),
            )

        try:
            # Call agent.execute() with resolved context
            result = await self.agent.execute(resolved_context)
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            return StepResult(
                name=self.name,
                step_type=self.step_type,
                success=True,
                output=result,
                duration_ms=duration_ms,
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
            Dictionary with step metadata. Includes agent name and context
            type (static or callable) for debugging purposes.
        """
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "agent": (
                self.agent.name
                if hasattr(self.agent, "name")
                else type(self.agent).__name__
            ),
            "context_type": "callable" if callable(self.context) else "static",
        }
