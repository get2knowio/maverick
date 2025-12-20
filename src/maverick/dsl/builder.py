from __future__ import annotations

from collections.abc import Callable
from typing import Any

from maverick.dsl.steps.agent import AgentStep
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.steps.generate import GenerateStep
from maverick.dsl.steps.python import PythonStep
from maverick.dsl.steps.subworkflow import SubWorkflowStep
from maverick.dsl.steps.validate import ValidateStep
from maverick.dsl.types import ContextBuilder


class StepBuilder:
    """Fluent builder for creating step definitions.

    Usage:
        step("process").python(action=my_func, args=(data,))
    """

    def __init__(self, name: str) -> None:
        if not name or not name.strip():
            raise ValueError("Step name cannot be empty or whitespace")
        self._name = name

    def python(
        self,
        action: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
    ) -> PythonStep:
        """Create a Python step that executes a callable.

        Args:
            action: Callable to execute (sync or async).
            args: Positional arguments for action.
            kwargs: Keyword arguments for action.

        Returns:
            PythonStep definition.
        """
        return PythonStep(
            name=self._name,
            action=action,
            args=args,
            kwargs=kwargs or {},
        )

    def agent(
        self,
        agent: Any,
        context: dict[str, Any] | ContextBuilder,
    ) -> AgentStep:
        """Create an agent step that invokes a MaverickAgent.

        Args:
            agent: MaverickAgent instance to invoke.
            context: Static dict or async callable that builds context.

        Returns:
            AgentStep definition.

        Example:
            result = yield step("review").agent(
                agent=CodeReviewerAgent(),
                context={"files": ["main.py"]},
            )
        """
        return AgentStep(
            name=self._name,
            agent=agent,
            context=context,
        )

    def generate(
        self,
        generator: Any,
        context: dict[str, Any] | ContextBuilder,
    ) -> GenerateStep:
        """Create a generate step that invokes a GeneratorAgent.

        Args:
            generator: GeneratorAgent instance to invoke.
            context: Static dict or async callable that builds context.

        Returns:
            GenerateStep definition.

        Example:
            text = yield step("describe").generate(
                generator=PRDescriptionGenerator(),
                context=lambda ctx: {"changes": ctx.get_step_output("review")},
            )
        """
        return GenerateStep(
            name=self._name,
            generator=generator,
            context=context,
        )

    def validate(
        self,
        stages: list[str] | str | None = None,
        retry: int = 3,
        on_failure: StepDefinition | None = None,
    ) -> ValidateStep:
        """Create a validate step that runs validation stages with retry.

        Args:
            stages: Explicit list of stages, config key, or None for default.
            retry: Number of retry attempts (0 = no retries).
            on_failure: Optional step to run before each retry.

        Returns:
            ValidateStep definition.

        Example:
            result = yield step("validate").validate(
                stages=["format", "lint", "test"],
                retry=2,
                on_failure=step("fix").python(action=auto_fix),
            )
        """
        return ValidateStep(
            name=self._name,
            stages=stages,
            retry=retry,
            on_failure=on_failure,
        )

    def subworkflow(
        self,
        workflow: Any,
        inputs: dict[str, Any] | None = None,
    ) -> SubWorkflowStep:
        """Create a subworkflow step that executes another workflow.

        Args:
            workflow: Decorated workflow function to execute.
            inputs: Input arguments for the sub-workflow.

        Returns:
            SubWorkflowStep definition.

        Example:
            result = yield step("nested").subworkflow(
                workflow=my_other_workflow,
                inputs={"data": processed_data},
            )
        """
        return SubWorkflowStep(
            name=self._name,
            workflow=workflow,
            inputs=inputs or {},
        )


def step(name: str) -> StepBuilder:
    """Create a step builder with the given name.

    Args:
        name: Unique step name within the workflow.

    Returns:
        StepBuilder instance for fluent step configuration.

    Raises:
        ValueError: If name is empty.

    Example:
        result = yield step("validate").python(action=validate, args=(data,))
    """
    return StepBuilder(name)
