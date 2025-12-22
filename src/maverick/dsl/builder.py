from __future__ import annotations

from collections.abc import Callable
from typing import Any

from maverick.dsl.steps.agent import AgentStep
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.steps.branch import BranchOption, BranchStep
from maverick.dsl.steps.checkpoint import CheckpointStep
from maverick.dsl.steps.conditional import ConditionalStep
from maverick.dsl.steps.error_handler import ErrorHandler, ErrorHandlerStep
from maverick.dsl.steps.generate import GenerateStep
from maverick.dsl.steps.parallel import ParallelStep
from maverick.dsl.steps.python import PythonStep
from maverick.dsl.steps.retry import RetryStep
from maverick.dsl.steps.rollback import RollbackStep
from maverick.dsl.steps.subworkflow import SubWorkflowStep
from maverick.dsl.steps.validate import ValidateStep
from maverick.dsl.types import ContextBuilder, Predicate, RollbackAction, StepType


class StepBuilder:
    """Fluent builder for creating step definitions.

    Usage:
        step("process").python(action=my_func, args=(data,))
        step("deploy").when(
            lambda ctx: ctx.inputs["env"] == "prod"
        ).python(action=deploy)
    """

    def __init__(self, name: str) -> None:
        if not name or not name.strip():
            raise ValueError("Step name cannot be empty or whitespace")
        self._name = name
        self._predicate: Predicate | None = None
        self._max_attempts: int | None = None
        self._backoff: float | None = None
        self._on_error_handler: ErrorHandler | None = None
        self._skip_on_error: bool = False
        self._rollback_action: RollbackAction | None = None
        self._checkpoint: bool = False

    def when(self, predicate: Predicate) -> StepBuilder:
        """Add conditional execution to the step.

        Args:
            predicate: Callable returning bool. Receives WorkflowContext.
                If False, step is skipped with SkipMarker output.
                If raises exception, step is skipped and warning logged.
                If returns non-bool, workflow fails with TypeError.

        Returns:
            Self for method chaining.
        """
        self._predicate = predicate
        return self

    def retry(
        self,
        max_attempts: int,
        backoff: float | None = None,
    ) -> StepBuilder:
        """Add retry with exponential backoff.

        Args:
            max_attempts: Maximum number of attempts (including first try).
            backoff: Base delay in seconds. Default 1.0.
                Delay formula: min(backoff * 2^(attempt-1), 60) with jitter.

        Returns:
            Self for method chaining.
        """
        self._max_attempts = max_attempts
        self._backoff = backoff
        return self

    def on_error(
        self,
        handler: ErrorHandler,
    ) -> StepBuilder:
        """Add error handler with fallback step selection.

        Args:
            handler: Callable that receives context and failed result,
                returns a fallback StepDefinition to execute.

        Returns:
            Self for method chaining.
        """
        self._on_error_handler = handler
        return self

    def skip_on_error(self) -> StepBuilder:
        """Convert failure to skip instead of failing workflow.

        Returns:
            Self for method chaining.
        """
        self._skip_on_error = True
        return self

    def with_rollback(
        self,
        rollback: RollbackAction,
    ) -> StepBuilder:
        """Register rollback action for this step.

        The rollback is executed (best-effort) if the workflow fails
        AFTER this step has successfully completed.

        Args:
            rollback: Async or sync callable that compensates the step.

        Returns:
            Self for method chaining.
        """
        self._rollback_action = rollback
        return self

    def checkpoint(self) -> StepBuilder:
        """Mark this step as a checkpoint for resumability.

        After this step completes successfully, workflow state is
        persisted. The workflow can be resumed from this point.

        Returns:
            Self for method chaining.
        """
        self._checkpoint = True
        return self

    def _wrap_step(self, step: StepDefinition) -> StepDefinition:
        """Apply any pending wrappers to the step.

        Wrappers are applied in this order (innermost to outermost):
        1. Rollback (registers on success)
        2. Error handler (skip_on_error or on_error)
        3. Retry (retries the wrapped step)
        4. Conditional (skips if predicate false)
        5. Checkpoint (marks for state persistence)

        Args:
            step: The base step definition to wrap.

        Returns:
            Wrapped step definition with all flow control applied.
        """
        # 1. Rollback wrapper (innermost - registers after step success)
        if self._rollback_action is not None:
            step = RollbackStep(inner=step, rollback_action=self._rollback_action)

        # 2. Error handler wrapper
        if self._skip_on_error or self._on_error_handler is not None:
            step = ErrorHandlerStep(
                inner=step,
                on_error_handler=self._on_error_handler,
                skip_on_error=self._skip_on_error,
            )

        # 3. Retry wrapper
        if self._max_attempts is not None:
            step = RetryStep(
                inner=step,
                max_attempts=self._max_attempts,
                backoff_base=self._backoff if self._backoff is not None else 1.0,
            )

        # 4. Conditional wrapper
        if self._predicate is not None:
            step = ConditionalStep(inner=step, predicate=self._predicate)

        # 5. Checkpoint wrapper (outermost - marks for state persistence)
        if self._checkpoint:
            step = CheckpointStep(inner=step)

        return step

    def python(
        self,
        action: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
    ) -> StepDefinition:
        """Create a Python step that executes a callable.

        Args:
            action: Callable to execute (sync or async).
            args: Positional arguments for action.
            kwargs: Keyword arguments for action.

        Returns:
            PythonStep definition (possibly wrapped with flow control).
        """
        base_step = PythonStep(
            name=self._name,
            action=action,
            args=args,
            kwargs=kwargs or {},
        )
        return self._wrap_step(base_step)

    def agent(
        self,
        agent: Any,
        context: dict[str, Any] | ContextBuilder,
    ) -> StepDefinition:
        """Create an agent step that invokes a MaverickAgent.

        Args:
            agent: MaverickAgent instance to invoke.
            context: Static dict or async callable that builds context.

        Returns:
            AgentStep definition (possibly wrapped with flow control).

        Example:
            result = yield step("review").agent(
                agent=CodeReviewerAgent(),
                context={"files": ["main.py"]},
            )
        """
        base_step = AgentStep(
            name=self._name,
            agent=agent,
            context=context,
        )
        return self._wrap_step(base_step)

    def generate(
        self,
        generator: Any,
        context: dict[str, Any] | ContextBuilder,
    ) -> StepDefinition:
        """Create a generate step that invokes a GeneratorAgent.

        Args:
            generator: GeneratorAgent instance to invoke.
            context: Static dict or async callable that builds context.

        Returns:
            GenerateStep definition (possibly wrapped with flow control).

        Example:
            text = yield step("describe").generate(
                generator=PRDescriptionGenerator(),
                context=lambda ctx: {"changes": ctx.get_step_output("review")},
            )
        """
        base_step = GenerateStep(
            name=self._name,
            generator=generator,
            context=context,
        )
        return self._wrap_step(base_step)

    def validate(
        self,
        stages: list[str] | str | None = None,
        retry: int = 3,
        on_failure: StepDefinition | None = None,
    ) -> StepDefinition:
        """Create a validate step that runs validation stages with retry.

        Args:
            stages: Explicit list of stages, config key, or None for default.
            retry: Number of retry attempts (0 = no retries).
            on_failure: Optional step to run before each retry.

        Returns:
            ValidateStep definition (possibly wrapped with flow control).

        Example:
            result = yield step("validate").validate(
                stages=["format", "lint", "test"],
                retry=2,
                on_failure=step("fix").python(action=auto_fix),
            )
        """
        base_step = ValidateStep(
            name=self._name,
            stages=stages,
            retry=retry,
            on_failure=on_failure,
        )
        return self._wrap_step(base_step)

    def subworkflow(
        self,
        workflow: Any,
        inputs: dict[str, Any] | None = None,
    ) -> StepDefinition:
        """Create a subworkflow step that executes another workflow.

        Args:
            workflow: Decorated workflow function to execute.
            inputs: Input arguments for the sub-workflow.

        Returns:
            SubWorkflowStep definition (possibly wrapped with flow control).

        Example:
            result = yield step("nested").subworkflow(
                workflow=my_other_workflow,
                inputs={"data": processed_data},
            )
        """
        base_step = SubWorkflowStep(
            name=self._name,
            workflow=workflow,
            inputs=inputs or {},
        )
        return self._wrap_step(base_step)


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


def branch(
    name: str,
    *options: tuple[Predicate, StepDefinition],
) -> BranchStep:
    """Create a branch step that selects one option to execute.

    Args:
        name: Step name for the branch.
        *options: Variable number of (predicate, step) tuples.
            Predicates are evaluated in order; first True wins.
            If no predicate matches, workflow fails.

    Returns:
        BranchStep definition.

    Raises:
        ValueError: If name is empty or no options provided.

    Example:
        yield branch(
            "route",
            (lambda ctx: ctx.inputs["type"] == "a", step("a").python(handle_a)),
            (lambda ctx: ctx.inputs["type"] == "b", step("b").python(handle_b)),
            (lambda ctx: True, step("default").python(handle_default)),
        )
    """
    if not name or not name.strip():
        raise ValueError("Branch name cannot be empty or whitespace")
    if not options:
        raise ValueError("Branch must have at least one option")

    branch_options = tuple(
        BranchOption(predicate=pred, step=step_def) for pred, step_def in options
    )
    return BranchStep(name=name, options=branch_options)


def parallel(
    name: str,
    *steps: StepDefinition,
) -> ParallelStep:
    """Create a parallel step that executes multiple steps.

    Initial implementation executes sequentially but interface is
    compatible with future concurrent execution.

    Args:
        name: Step name for the parallel group.
        *steps: Variable number of steps to execute.
            All step names must be unique (validated before execution).

    Returns:
        ParallelStep definition.

    Raises:
        ValueError: If name is empty or no steps provided.

    Example:
        result = yield parallel(
            "reviews",
            step("lint").python(run_lint),
            step("typecheck").python(run_typecheck),
            step("test").python(run_tests),
        )
        # Access results:
        lint_output = result.get_output("lint")
    """
    if not name or not name.strip():
        raise ValueError("Parallel name cannot be empty or whitespace")
    if not steps:
        raise ValueError("Parallel must have at least one step")

    return ParallelStep(name=name, step_type=StepType.PARALLEL, children=steps)
