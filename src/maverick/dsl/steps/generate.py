"""Generate step for the Maverick workflow DSL.

This module defines GenerateStep, which invokes a GeneratorAgent to produce text
as part of a workflow.
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
    from maverick.dsl.protocols import GeneratorProtocol


@dataclass(frozen=True, slots=True)
class GenerateStep(StepDefinition):
    """Step that invokes a GeneratorAgent to produce text.

    GenerateStep wraps a GeneratorAgent and invokes its generate() method with
    a resolved context. The context can be a static dictionary or a callable
    that dynamically builds the context from workflow state.

    Attributes:
        name: Step name.
        generator: GeneratorAgent instance.
        context: Static dict OR callable context builder.
        step_type: Always StepType.GENERATE (auto-set, do not pass).

    Example:
        >>> from maverick.agents.generators import PRBodyGenerator
        >>> generator = PRBodyGenerator()
        >>> step = GenerateStep(
        ...     name="generate_pr_body",
        ...     generator=generator,
        ...     context={"commits": ["fix: bug"], "diff": "..."}
        ... )
        >>> result = await step.execute(workflow_context)
        >>> result.output  # Generated PR body text
    """

    name: str
    generator: GeneratorProtocol
    context: dict[str, Any] | ContextBuilder
    step_type: StepType = field(default=StepType.GENERATE, init=False)

    async def _resolve_context(
        self, workflow_context: WorkflowContext
    ) -> dict[str, Any]:
        """Resolve context - return static dict or call builder.

        Args:
            workflow_context: Current workflow execution context.

        Returns:
            Resolved context dictionary to pass to generator.
        """
        if callable(self.context):
            return await self.context(workflow_context)
        return self.context

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Execute generator with resolved context.

        Resolves the context (static or via builder), then calls the generator's
        generate() method. Handles errors gracefully and returns a StepResult.

        Args:
            context: Workflow execution context.

        Returns:
            StepResult with success=True and output=generated_text on success,
            or success=False and error message on failure.
        """
        start_time = time.perf_counter()

        try:
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
            # GeneratorAgent has a generate() method that returns string
            result = await self.generator.generate(resolved_context)
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            return StepResult(
                name=self.name,
                step_type=self.step_type,
                success=True,
                output=result,  # String output from generator
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
            Dictionary with step metadata. Includes generator name/type and
            context type (static or callable) for debugging.
        """
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "generator": (
                self.generator.name
                if hasattr(self.generator, "name")
                else type(self.generator).__name__
            ),
            "context_type": "callable" if callable(self.context) else "static",
        }
