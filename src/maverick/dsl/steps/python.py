"""Python callable step for the Maverick workflow DSL.

This module defines PythonStep, which executes arbitrary Python callables
(both sync and async) as part of a workflow.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from maverick.dsl.context import WorkflowContext
from maverick.dsl.results import StepResult
from maverick.dsl.steps.base import StepDefinition
from maverick.dsl.types import StepType


@dataclass(frozen=True, slots=True)
class PythonStep(StepDefinition):
    """Step that executes a Python callable.

    PythonStep allows workflows to execute arbitrary Python code by wrapping
    a callable (function, lambda, method, etc.). Both sync and async callables
    are supported. Sync callables are automatically offloaded to a thread via
    asyncio.to_thread to avoid blocking the event loop.

    Attributes:
        name: Step name.
        action: Callable to execute (sync or async).
        args: Positional arguments for action.
        kwargs: Keyword arguments for action.
        step_type: Always StepType.PYTHON (auto-set, do not pass).

    Example:
        >>> def parse_tasks(task_file: str) -> list[str]:
        ...     return task_file.split("\n")
        >>> step = PythonStep(
        ...     name="parse_tasks",
        ...     action=parse_tasks,
        ...     args=("task1\ntask2",)
        ... )
        >>> context = WorkflowContext(inputs={})
        >>> result = await step.execute(context)
        >>> result.output
        ["task1", "task2"]
    """

    name: str
    action: Callable[..., Any]
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    step_type: StepType = field(default=StepType.PYTHON, init=False)

    async def execute(self, context: WorkflowContext) -> StepResult:
        """Execute callable and return result.

        Handles both sync and async callables. Sync callables are offloaded
        to a thread via asyncio.to_thread to avoid blocking the event loop.
        Catches exceptions and returns failed StepResult with error message.

        Args:
            context: Workflow execution context (passed but not used directly
                in this step; callables can access it via args/kwargs if needed).

        Returns:
            StepResult with success=True and output=callable_result on success,
            or success=False and error message on failure.
        """
        start_time = time.perf_counter()

        try:
            # Check if the callable is async
            if inspect.iscoroutinefunction(self.action):
                # Direct await for async callables
                result = await self.action(*self.args, **self.kwargs)
            else:
                # Offload sync callables to thread to avoid blocking event loop
                result = await asyncio.to_thread(self.action, *self.args, **self.kwargs)

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
            Dictionary with step metadata. Note that we cannot serialize
            the actual callable, so we include its name and argument info
            for debugging purposes.
        """
        return {
            "name": self.name,
            "step_type": self.step_type.value,
            "action": (
                self.action.__name__
                if hasattr(self.action, "__name__")
                else str(self.action)
            ),
            "args_count": len(self.args),
            "kwargs_keys": list(self.kwargs.keys()),
        }
