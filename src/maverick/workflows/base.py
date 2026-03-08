"""PythonWorkflow abstract base class.

Provides the template-method infrastructure for Python-native workflow
implementations:

- Configuration resolution via resolve_step_config()
- Progress event emission via emit_* helpers
- Step result tracking and WorkflowResult aggregation
- Rollback registration and reverse-order execution
- Checkpoint save/load delegation
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import TYPE_CHECKING, Any, Literal

from maverick.events import (
    CheckpointSaved,
    ProgressEvent,
    RollbackCompleted,
    RollbackStarted,
    StepCompleted,
    StepOutput,
    StepStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.exceptions import WorkflowError
from maverick.executor.config import (
    StepConfig,
)
from maverick.executor.config import (
    resolve_step_config as _resolve_step_config,
)
from maverick.logging import get_logger
from maverick.results import StepResult, WorkflowResult
from maverick.types import StepType

if TYPE_CHECKING:
    from maverick.checkpoint.store import CheckpointStore
    from maverick.config import MaverickConfig
    from maverick.executor.protocol import StepExecutor
    from maverick.registry import ComponentRegistry

logger = get_logger(__name__)

# Python workflow rollback callable — no WorkflowContext needed.
# Do NOT reuse maverick.types.RollbackAction which requires WorkflowContext.
PythonRollbackAction = Callable[[], Awaitable[None]]


class PythonWorkflow(ABC):
    """Abstract base class for Python-native workflows.

    Provides:
    - Configuration resolution via resolve_step_config()
    - Progress event emission via emit_* helpers
    - Step result tracking and WorkflowResult aggregation
    - Rollback registration and execution
    - Checkpoint save/load delegation

    Subclasses implement _run() with their workflow logic.

    Args:
        config: Project configuration (MaverickConfig).
        registry: Component registry for action/agent dispatch.
        checkpoint_store: Optional checkpoint persistence backend.
        step_executor: Optional agent step executor (StepExecutor protocol).
        workflow_name: Identifier for this workflow instance.

    Raises:
        TypeError: If config or registry is None.
    """

    def __init__(
        self,
        *,
        config: MaverickConfig,
        registry: ComponentRegistry,
        checkpoint_store: CheckpointStore | None = None,
        step_executor: StepExecutor | None = None,
        workflow_name: str,
    ) -> None:
        if config is None:
            raise TypeError("config must not be None")
        if registry is None:
            raise TypeError("registry must not be None")

        self._config = config
        self._registry = registry
        self._checkpoint_store = checkpoint_store
        self._step_executor = step_executor
        self._workflow_name = workflow_name

        # Public result attribute — populated after execute() completes.
        self.result: WorkflowResult | None = None

        # Internal state (initialised properly in execute()).
        self._event_queue: asyncio.Queue[ProgressEvent | None]
        self._step_results: list[StepResult]
        self._step_start_times: dict[str, float]
        self._current_step: str | None
        self._rollback_stack: list[tuple[str, PythonRollbackAction]]

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def config(self) -> MaverickConfig:
        """Read-only access to the project configuration."""
        return self._config

    @property
    def registry(self) -> ComponentRegistry:
        """Read-only access to the component registry."""
        return self._registry

    @property
    def step_executor(self) -> StepExecutor | None:
        """Read-only access to the optional step executor."""
        return self._step_executor

    def _resolve_display_provider(self) -> str | None:
        """Return the default provider name for display purposes."""
        try:
            providers = self._config.agent_providers
            for name, pcfg in providers.items():
                if pcfg.default:
                    return name
            # No default marked — try first provider
            for name in providers:
                return name
        except (AttributeError, TypeError):
            pass
        return None

    def _resolve_display_model(self) -> str | None:
        """Resolve the effective model ID for display purposes.

        Returns the explicitly-configured model_id, or the default
        provider's default_model, or None if neither is available.
        """
        try:
            model_cfg = self._config.model
            fields_set = getattr(model_cfg, "model_fields_set", set())
            if "model_id" in fields_set:
                return model_cfg.model_id
        except (AttributeError, TypeError):
            return None

        try:
            providers = self._config.agent_providers
            for _name, pcfg in providers.items():
                if pcfg.default:
                    return pcfg.default_model
            for _name, pcfg in providers.items():
                return pcfg.default_model
        except (AttributeError, TypeError):
            pass
        return None

    # ------------------------------------------------------------------
    # Public template method
    # ------------------------------------------------------------------

    async def execute(
        self, inputs: dict[str, Any]
    ) -> AsyncGenerator[ProgressEvent, None]:
        """Execute the workflow, yielding progress events.

        Template method pattern:
        1. Emits WorkflowStarted
        2. Runs _run() in a background asyncio Task
        3. Yields ProgressEvents from an internal queue
        4. On completion: aggregates WorkflowResult into self.result,
           emits WorkflowCompleted
        5. On failure: executes rollbacks in reverse order,
           stores failure result in self.result, emits WorkflowCompleted(success=False)

        Args:
            inputs: Workflow input parameters.

        Yields:
            ProgressEvent instances. Final event is always WorkflowCompleted.
        """
        # Reset per-execution state
        self._event_queue = asyncio.Queue()
        self._step_results = []
        self._step_start_times = {}
        self._current_step = None
        self._rollback_stack = []
        self.result = None

        start_time = time.time()

        # Emit WorkflowStarted synchronously before spawning the background task
        await self._event_queue.put(
            WorkflowStarted(workflow_name=self._workflow_name, inputs=inputs)
        )

        # Spawn background task that runs _run() and always puts a sentinel
        run_task = asyncio.create_task(self._run_with_cleanup(inputs))

        # Drain queue until sentinel (None)
        while True:
            event = await self._event_queue.get()
            if event is None:
                break
            yield event

        # _run_with_cleanup is guaranteed to be done at this point.
        total_ms = int((time.time() - start_time) * 1000)

        # Determine success and collect any exception.
        # NOTE: task.exception() raises CancelledError if the task was cancelled,
        # so we must check cancelled() first in a separate branch.
        final_output: Any = None
        if run_task.cancelled():  # noqa: SIM114 — task.exception() raises if cancelled
            success = False
        elif run_task.exception() is not None:
            success = False
        else:
            success = True
            final_output = run_task.result()

        self.result = WorkflowResult(
            workflow_name=self._workflow_name,
            success=success,
            step_results=tuple(self._step_results),
            total_duration_ms=total_ms,
            final_output=final_output,
        )

        yield WorkflowCompleted(
            workflow_name=self._workflow_name,
            success=success,
            total_duration_ms=total_ms,
        )

        # Re-raise if _run() raised an exception so callers can distinguish
        # "workflow completed with failures" from "workflow crashed" (R-012).
        if not run_task.cancelled() and run_task.exception() is not None:
            raise run_task.exception()  # type: ignore[misc]

    # ------------------------------------------------------------------
    # Configuration resolution
    # ------------------------------------------------------------------

    def resolve_step_config(
        self,
        step_name: str,
        step_type: StepType = StepType.PYTHON,
        agent_name: str | None = None,
    ) -> StepConfig:
        """Resolve per-step configuration by merging defaults with overrides.

        Uses the 5-layer resolution from maverick.executor.config:
        - inline_config: None (Python workflows have no YAML inline config)
        - project_step_config: from self._config.steps.get(step_name)
        - agent_config: from self._config.agents.get(agent_name) when provided
        - global_model: from self._config.model
        - provider_default_model: from the default provider config

        Args:
            step_name: The step name to resolve config for.
            step_type: Step type for mode inference. Defaults to StepType.PYTHON.
            agent_name: Optional agent name for agent-level config lookup.

        Returns:
            Resolved StepConfig with merged values.
        """
        agent_config = (
            self._config.agents.get(agent_name) if agent_name else None
        )
        return _resolve_step_config(
            inline_config=None,
            project_step_config=self._config.steps.get(step_name),
            agent_config=agent_config,
            global_model=self._config.model,
            step_type=step_type,
            step_name=step_name,
        )

    # ------------------------------------------------------------------
    # Event emission helpers
    # ------------------------------------------------------------------

    async def emit_step_started(
        self,
        name: str,
        step_type: StepType = StepType.PYTHON,
        provider: str | None = None,
        model_id: str | None = None,
    ) -> None:
        """Emit a StepStarted event and record the step start time.

        Args:
            name: Step name (unique within this workflow execution).
            step_type: Step type for the event. Defaults to StepType.PYTHON.
            provider: Optional provider name for display.
            model_id: Optional model identifier for display.
        """
        self._current_step = name
        self._step_start_times[name] = time.time()
        await self._event_queue.put(
            StepStarted(
                step_name=name,
                step_type=step_type,
                step_path=f"{self._workflow_name}.{name}",
                provider=provider,
                model_id=model_id,
            )
        )

    async def emit_step_completed(
        self,
        name: str,
        output: Any = None,
        step_type: StepType = StepType.PYTHON,
    ) -> None:
        """Emit a StepCompleted event with success=True.

        Also creates a StepResult and appends it to the internal results list.

        Args:
            name: Step name (must match a prior emit_step_started call).
            output: Step output value (stored in StepResult).
            step_type: Step type for the event.
        """
        duration_ms = self._compute_duration_ms(name)
        if self._current_step == name:
            self._current_step = None

        step_result = StepResult.create_success(
            name=name,
            step_type=step_type,
            output=output,
            duration_ms=duration_ms,
        )
        self._step_results.append(step_result)

        await self._event_queue.put(
            StepCompleted(
                step_name=name,
                step_type=step_type,
                success=True,
                duration_ms=duration_ms,
                step_path=f"{self._workflow_name}.{name}",
            )
        )

    async def emit_step_failed(
        self,
        name: str,
        error: str,
        step_type: StepType = StepType.PYTHON,
    ) -> None:
        """Emit a StepCompleted event with success=False.

        Also creates a failure StepResult and appends it to the internal
        results list.

        Args:
            name: Step name (must match a prior emit_step_started call).
            error: Error description.
            step_type: Step type for the event.
        """
        duration_ms = self._compute_duration_ms(name)
        if self._current_step == name:
            self._current_step = None

        step_result = StepResult.create_failure(
            name=name,
            step_type=step_type,
            duration_ms=duration_ms,
            error=error,
        )
        self._step_results.append(step_result)

        await self._event_queue.put(
            StepCompleted(
                step_name=name,
                step_type=step_type,
                success=False,
                duration_ms=duration_ms,
                error=error,
                step_path=f"{self._workflow_name}.{name}",
            )
        )

    async def execute_agent(
        self,
        *,
        step_name: str,
        agent_name: str,
        label: str,
        prompt: Any,
        output_schema: type[Any] | None = None,
        parent_step: str | None = None,
        timeout: int = 300,
        max_retries: int = 3,
    ) -> Any:
        """Execute an agent with retry, progress messaging, and timing.

        Wraps ``self._step_executor.execute()`` with:
        - R4/R8 agent lifecycle interims (🤖 start, ✓ end)
        - Exponential-backoff retry on transient/timeout errors
        - Retry progress messages (↻ label retry N/max...)

        Args:
            step_name: Executor step name for observability.
            agent_name: Registry key of the agent.
            label: Human-readable label for progress messages.
            prompt: Prompt passed to the agent.
            output_schema: Optional Pydantic model for structured output.
            parent_step: Step name for emitting progress events.
                Defaults to ``step_name``.
            timeout: Per-attempt timeout in seconds.
            max_retries: Maximum number of attempts.

        Returns:
            The ``ExecutorResult`` from the executor.

        Raises:
            WorkflowError: If no step executor is configured.
        """
        from tenacity import (
            AsyncRetrying,
            retry_if_exception_type,
            stop_after_attempt,
            wait_exponential,
        )

        from maverick.exceptions.agent import MaverickTimeoutError

        if self._step_executor is None:
            raise WorkflowError(f"step_executor required for agent step '{step_name}'")

        emit_step = parent_step or step_name

        # Resolve per-step config (provider, model, timeout, etc.) from the
        # 5-layer precedence chain so that per-step YAML overrides are honoured.
        resolved = self.resolve_step_config(
            step_name, StepType.PYTHON, agent_name=agent_name
        )
        # Config timeout takes precedence; fall back to caller-supplied value.
        effective_timeout = resolved.timeout if resolved.timeout is not None else timeout
        resolved = resolved.model_copy(update={"timeout": effective_timeout})

        provider = resolved.provider or self._resolve_display_provider() or "default"
        model = resolved.model_id or self._resolve_display_model() or "default"

        # R4/R8: 🤖 start
        await self.emit_output(
            emit_step,
            f"\U0001f916 {label}... ({provider}/{model})",
            level="info",
        )

        async def _event_cb(event: Any) -> None:
            await self._event_queue.put(event)

        _transient = (
            TimeoutError,
            ConnectionError,
            OSError,
            MaverickTimeoutError,
        )

        t0 = time.monotonic()
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=2, min=2, max=30),
            retry=retry_if_exception_type(_transient),
            reraise=True,
        ):
            with attempt:
                if attempt.retry_state.attempt_number > 1:
                    n = attempt.retry_state.attempt_number
                    await self.emit_output(
                        emit_step,
                        f"\u21bb {label} retry {n}/{max_retries}...",
                        level="warning",
                    )
                result = await self._step_executor.execute(
                    step_name=step_name,
                    agent_name=agent_name,
                    prompt=prompt,
                    output_schema=output_schema,
                    event_callback=_event_cb,
                    config=resolved,
                )

        elapsed = time.monotonic() - t0
        # R4: ✓ end
        await self.emit_output(
            emit_step,
            f"\u2713 {label} ({elapsed:.1f}s)",
            level="success",
        )
        return result

    async def emit_output(
        self,
        step_name: str,
        message: str,
        level: Literal["info", "success", "warning", "error"] = "info",
        source: str | None = None,
    ) -> None:
        """Emit a StepOutput event for informational messages.

        Args:
            step_name: Name of the step producing the output.
            message: Human-readable message.
            level: One of "info", "success", "warning", "error".
            source: Optional source identifier (e.g., "github", "jj").
        """
        await self._event_queue.put(
            StepOutput(
                step_name=step_name,
                message=message,
                level=level,
                source=source,
                step_path=f"{self._workflow_name}.{step_name}",
            )
        )

    # ------------------------------------------------------------------
    # Rollback
    # ------------------------------------------------------------------

    def register_rollback(
        self,
        name: str,
        action: PythonRollbackAction,
    ) -> None:
        """Register a rollback action to execute on workflow failure.

        Rollbacks execute in reverse registration order (LIFO).

        Args:
            name: Identifier for the rollback (used for logging/events).
            action: Async callable (no params) to execute during rollback.
        """
        self._rollback_stack.append((name, action))

    # ------------------------------------------------------------------
    # Checkpointing
    # ------------------------------------------------------------------

    async def save_checkpoint(self, data: dict[str, Any]) -> None:
        """Save a checkpoint via the configured CheckpointStore.

        No-op if checkpoint_store is None.

        Args:
            data: Checkpoint data to persist.
        """
        if self._checkpoint_store is None:
            return

        from datetime import UTC, datetime

        from maverick.checkpoint.data import CheckpointData, compute_inputs_hash

        checkpoint_id = self._current_step or "checkpoint"
        cp = CheckpointData(
            checkpoint_id=checkpoint_id,
            workflow_name=self._workflow_name,
            inputs_hash=compute_inputs_hash(data),
            step_results=tuple(r.to_dict() for r in self._step_results),
            saved_at=datetime.now(tz=UTC).isoformat(),
            user_data=data,
        )
        await self._checkpoint_store.save(self._workflow_name, cp)

        await self._event_queue.put(
            CheckpointSaved(
                step_name=self._current_step or "checkpoint",
                workflow_id=self._workflow_name,
            )
        )

    async def load_checkpoint(self) -> dict[str, Any] | None:
        """Load the latest checkpoint for this workflow.

        Returns:
            Checkpoint data dict, or None if no checkpoint exists or
            checkpoint_store is None.
        """
        if self._checkpoint_store is None:
            return None

        cp = await self._checkpoint_store.load_latest(self._workflow_name)
        if cp is None:
            return None

        # Return the user-provided data from the checkpoint (not the metadata)
        return cp.user_data

    # ------------------------------------------------------------------
    # Abstract method
    # ------------------------------------------------------------------

    @abstractmethod
    async def _run(self, inputs: dict[str, Any]) -> Any:
        """Implement workflow logic.

        Subclasses call self.emit_* helpers to report progress.
        The return value becomes the WorkflowResult.final_output.

        Args:
            inputs: Workflow input parameters.

        Returns:
            Final output value for the WorkflowResult.
        """

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_duration_ms(self, step_name: str) -> int:
        """Compute elapsed time for a step in milliseconds.

        Args:
            step_name: Step name whose start time was recorded.

        Returns:
            Duration in milliseconds (0 if start time not recorded).
        """
        start = self._step_start_times.get(step_name)
        if start is None:
            return 0
        return max(0, int((time.time() - start) * 1000))

    async def _run_with_cleanup(self, inputs: dict[str, Any]) -> Any:
        """Run _run() with error handling and always signal completion.

        Puts a sentinel None into the event queue when done (success or
        failure) so the execute() generator can exit its drain loop.

        Args:
            inputs: Workflow input parameters forwarded to _run().

        Returns:
            Return value of _run() on success.

        Raises:
            Re-raises any exception from _run() after cleanup.
        """
        try:
            return await self._run(inputs)
        except asyncio.CancelledError:
            if self._current_step:
                await self.emit_step_failed(self._current_step, "Workflow cancelled")
                self._current_step = None
            await self._execute_rollbacks()
            raise
        except Exception as exc:
            if self._current_step:
                await self.emit_step_failed(self._current_step, str(exc))
                self._current_step = None
            await self._execute_rollbacks()
            raise
        finally:
            # Always signal to execute() that the background task is done.
            await self._event_queue.put(None)

    async def _execute_rollbacks(self) -> None:
        """Execute all registered rollbacks in reverse order (LIFO).

        Emits RollbackStarted and RollbackCompleted events for each action.
        Errors in individual rollbacks are captured and reported but do NOT
        prevent remaining rollbacks from running.
        """
        for name, action in reversed(self._rollback_stack):
            await self._event_queue.put(RollbackStarted(step_name=name))
            try:
                await action()
                await self._event_queue.put(
                    RollbackCompleted(step_name=name, success=True)
                )
            except Exception as rb_exc:
                logger.warning(
                    "rollback_action_failed",
                    step_name=name,
                    error=str(rb_exc),
                )
                await self._event_queue.put(
                    RollbackCompleted(
                        step_name=name,
                        success=False,
                        error=str(rb_exc),
                    )
                )
