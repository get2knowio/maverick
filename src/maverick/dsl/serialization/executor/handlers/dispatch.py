"""Mode-aware dispatch for Python steps (Spec 034).

Routes Python step execution to either the deterministic action handler
or an AI agent via StepExecutor, based on the resolved StepConfig.mode.
Implements autonomy gates and fallback-to-deterministic on agent failure.
"""

from __future__ import annotations

import asyncio
import dataclasses
import inspect
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from maverick.dsl.context import WorkflowContext
from maverick.dsl.errors import ReferenceResolutionError
from maverick.dsl.executor.config import StepConfig
from maverick.dsl.serialization.executor.handlers.base import EventCallback
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import PythonStepRecord
from maverick.dsl.types import AutonomyLevel, StepMode
from maverick.library.actions.intents import get_intent
from maverick.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """Result of mode-aware step dispatch.

    Attributes:
        output: The step result (from agent or deterministic handler).
        mode_used: Actual execution mode used.
        fallback_used: True if agent mode failed and deterministic ran.
        autonomy_level: The autonomy level applied during dispatch.
        agent_result_accepted: None for deterministic, True/False for agent.
        validation_details: Human-readable validation/verification outcome.
    """

    output: Any
    mode_used: StepMode
    fallback_used: bool
    autonomy_level: AutonomyLevel
    agent_result_accepted: bool | None
    validation_details: str | None

    def to_dict(self) -> dict[str, Any]:
        """Serialize dispatch metadata to a JSON-compatible dictionary.

        Note: ``output`` is intentionally excluded — it may be large or
        non-serializable.  Use ``output`` directly when the full result
        is needed.
        """
        return {
            "mode_used": self.mode_used.value,
            "fallback_used": self.fallback_used,
            "autonomy_level": self.autonomy_level.value,
            "agent_result_accepted": self.agent_result_accepted,
            "validation_details": self.validation_details,
        }


def _structurally_equivalent(a: Any, b: Any) -> bool:
    """Check structural equivalence of two values (Collaborator-level comparison).

    Compares dicts, lists, dataclasses, and Pydantic models by structure
    rather than identity. Primitives are compared via equality.

    Args:
        a: First value.
        b: Second value.

    Returns:
        True if the values are structurally equivalent.
    """
    # Normalize dataclasses to dicts
    if dataclasses.is_dataclass(a) and not isinstance(a, type):
        a = dataclasses.asdict(a)
    if dataclasses.is_dataclass(b) and not isinstance(b, type):
        b = dataclasses.asdict(b)

    # Normalize Pydantic models to dicts
    if isinstance(a, BaseModel):
        a = a.model_dump()
    if isinstance(b, BaseModel):
        b = b.model_dump()

    # Type mismatch
    if type(a) is not type(b):
        return False

    # Dict comparison
    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_structurally_equivalent(a[k], b[k]) for k in a)

    # List/tuple comparison
    if isinstance(a, (list, tuple)):
        if len(a) != len(b):
            return False
        return all(_structurally_equivalent(x, y) for x, y in zip(a, b, strict=True))

    # Primitive equality
    return bool(a == b)


async def _call_action(action: Callable[..., Any], inputs: dict[str, Any]) -> Any:
    """Call an action callable, awaiting the result if it is a coroutine.

    Args:
        action: The action callable (sync or async).
        inputs: Keyword arguments to pass.

    Returns:
        The action result.
    """
    result = action(**inputs)
    if inspect.iscoroutine(result):
        result = await result
    return result


def build_agent_prompt(
    *,
    intent: str,
    resolved_inputs: dict[str, Any],
    prompt_suffix: str | None = None,
    prompt_file_content: str | None = None,
) -> tuple[str, str]:
    """Construct agent prompt from intent and inputs.

    Returns a tuple of (instructions, prompt) for StepExecutor.execute().

    Args:
        intent: Plain-language intent description.
        resolved_inputs: Step inputs as structured context.
        prompt_suffix: Optional inline prompt extension.
        prompt_file_content: Optional file-based prompt content.

    Returns:
        Tuple of (instructions, prompt).
    """
    # Build instructions (system-level)
    instructions = f"You are executing a workflow step. Your goal:\n\n{intent}"
    if prompt_suffix:
        instructions += f"\n\n{prompt_suffix}"
    if prompt_file_content:
        instructions += f"\n\n{prompt_file_content}"

    # Build prompt (user-level) from resolved inputs
    serialized_inputs = json.dumps(resolved_inputs, indent=2, default=str)
    prompt = (
        f"You have been given the following inputs:\n{serialized_inputs}\n\n"
        "Produce output that matches what the deterministic handler would produce.\n"
        "Output your result as valid JSON."
    )

    return instructions, prompt


async def dispatch_agent_mode(
    *,
    step: PythonStepRecord,
    resolved_inputs: dict[str, Any],
    context: WorkflowContext,
    registry: ComponentRegistry,
    step_config: StepConfig,
    event_callback: EventCallback | None = None,
) -> DispatchResult:
    """Execute a Python step via agent mode with autonomy gates.

    Constructs an intent-based prompt, delegates to StepExecutor, applies
    autonomy-level validation/verification, and falls back to deterministic
    execution on failure.

    Args:
        step: PythonStepRecord containing action reference.
        resolved_inputs: Already-resolved keyword arguments.
        context: WorkflowContext with step_executor and inputs.
        registry: Component registry for action lookup.
        step_config: Resolved StepConfig with mode, autonomy, timeout.
        event_callback: Optional callback for real-time event streaming.

    Returns:
        DispatchResult with output and dispatch metadata.

    Raises:
        ReferenceResolutionError: If action not found in registry.
        RuntimeError: If both agent and deterministic execution fail.
    """
    autonomy = step_config.autonomy or AutonomyLevel.OPERATOR

    # Validate action exists (defense-in-depth; caller already checks)
    if not registry.actions.has(step.action):
        raise ReferenceResolutionError(
            reference_type="action",
            reference_name=step.action,
            available_names=registry.actions.list_names(),
        )
    action_callable = registry.actions.get(step.action)

    # Operator: warn and fall back to deterministic (defense-in-depth)
    if autonomy == AutonomyLevel.OPERATOR:
        logger.warning(
            "dispatch.operator_fallback",
            step_name=step.name,
            action=step.action,
            message=(
                "Operator autonomy reached agent dispatch; "
                "falling back to deterministic"
            ),
        )
        return await _run_deterministic_fallback(
            action_callable=action_callable,
            resolved_inputs=resolved_inputs,
            step_name=step.name,
            autonomy=autonomy,
            fallback_used=True,
        )

    # Look up intent
    intent = get_intent(step.action)
    if intent is None:
        logger.warning(
            "dispatch.no_intent",
            step_name=step.name,
            action=step.action,
            message="No intent description found; falling back to deterministic",
        )
        return await _run_deterministic_fallback(
            action_callable=action_callable,
            resolved_inputs=resolved_inputs,
            step_name=step.name,
            autonomy=autonomy,
            fallback_used=True,
        )

    # Check StepExecutor availability
    if context.step_executor is None:
        logger.warning(
            "dispatch.no_executor",
            step_name=step.name,
            action=step.action,
            message="No StepExecutor available; falling back to deterministic",
        )
        return await _run_deterministic_fallback(
            action_callable=action_callable,
            resolved_inputs=resolved_inputs,
            step_name=step.name,
            autonomy=autonomy,
            fallback_used=True,
        )

    # Build prompt
    prompt_suffix = step_config.prompt_suffix
    prompt_file_content = None
    if step_config.prompt_file:
        try:
            prompt_file_content = Path(step_config.prompt_file).read_text()
        except OSError:
            logger.warning(
                "dispatch.prompt_file_error",
                step_name=step.name,
                prompt_file=step_config.prompt_file,
            )

    instructions, prompt = build_agent_prompt(
        intent=intent,
        resolved_inputs=resolved_inputs,
        prompt_suffix=prompt_suffix,
        prompt_file_content=prompt_file_content,
    )

    # Execute via StepExecutor with timeout
    start_time = time.monotonic()
    try:
        timeout = step_config.timeout
        coro = context.step_executor.execute(
            step_name=step.name,
            agent_name="dispatch",
            prompt=prompt,
            instructions=instructions,
            allowed_tools=step_config.allowed_tools,
            config=step_config,
            event_callback=event_callback,
        )
        if timeout is not None:
            executor_result = await asyncio.wait_for(coro, timeout=timeout)
        else:
            executor_result = await coro

        agent_result = executor_result.output
        duration_ms = int((time.monotonic() - start_time) * 1000)

        logger.info(
            "dispatch.agent_completed",
            step_name=step.name,
            action=step.action,
            autonomy=autonomy.value,
            duration_ms=duration_ms,
            accepted=True,
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        reason = "timeout" if isinstance(exc, TimeoutError) else "exception"
        logger.warning(
            "dispatch.fallback",
            step_name=step.name,
            action=step.action,
            reason=reason,
            error=str(exc),
            duration_ms=duration_ms,
        )
        # Fallback to deterministic
        try:
            return await _run_deterministic_fallback(
                action_callable=action_callable,
                resolved_inputs=resolved_inputs,
                step_name=step.name,
                autonomy=autonomy,
                fallback_used=True,
            )
        except Exception as det_exc:
            raise RuntimeError(
                f"Both agent and deterministic execution failed for step "
                f"'{step.name}': agent={exc}, deterministic={det_exc}"
            ) from det_exc

    # Apply autonomy gate
    return await apply_autonomy_gate(
        agent_result=agent_result,
        autonomy_level=autonomy,
        deterministic_action=action_callable,
        resolved_inputs=resolved_inputs,
        step_name=step.name,
    )


async def apply_autonomy_gate(
    *,
    agent_result: Any,
    autonomy_level: AutonomyLevel,
    deterministic_action: Callable[..., Any],
    resolved_inputs: dict[str, Any],
    step_name: str,
) -> DispatchResult:
    """Apply autonomy-level validation/verification to agent result.

    Operator is handled upstream by ``dispatch_agent_mode()`` and should
    never reach this function.  A defensive guard raises if it does.

    Args:
        agent_result: The result produced by the agent.
        autonomy_level: The configured autonomy level.
        deterministic_action: The deterministic handler for validation.
        resolved_inputs: Inputs for deterministic re-execution.
        step_name: Step name for logging.

    Returns:
        DispatchResult indicating acceptance or rejection.

    Raises:
        ValueError: If an unknown autonomy level is encountered.
    """
    if autonomy_level == AutonomyLevel.COLLABORATOR:
        # Check for side-effecting actions: auto-downgrade to Consultant
        action_metadata = getattr(deterministic_action, "_metadata", None)
        if action_metadata and getattr(action_metadata, "has_side_effects", False):
            logger.warning(
                "dispatch.collaborator_side_effect_guard",
                step_name=step_name,
                message="Side-effecting action; downgrading to Consultant verification",
            )
            return _make_consultant_result(
                agent_result=agent_result,
                deterministic_action=deterministic_action,
                step_name=step_name,
            )

        # Re-execute deterministic handler and compare
        det_result = await _call_action(deterministic_action, resolved_inputs)

        if _structurally_equivalent(agent_result, det_result):
            logger.info(
                "dispatch.autonomy_validation",
                step_name=step_name,
                autonomy=autonomy_level.value,
                outcome="accepted",
            )
            return DispatchResult(
                output=agent_result,
                mode_used=StepMode.AGENT,
                fallback_used=False,
                autonomy_level=autonomy_level,
                agent_result_accepted=True,
                validation_details=(
                    "Collaborator: agent result matches deterministic output"
                ),
            )
        else:
            logger.info(
                "dispatch.autonomy_validation",
                step_name=step_name,
                autonomy=autonomy_level.value,
                outcome="rejected",
            )
            return DispatchResult(
                output=det_result,
                mode_used=StepMode.DETERMINISTIC,
                fallback_used=False,
                autonomy_level=autonomy_level,
                agent_result_accepted=False,
                validation_details=(
                    "Collaborator: agent result differs; using deterministic output"
                ),
            )

    if autonomy_level == AutonomyLevel.CONSULTANT:
        return _make_consultant_result(
            agent_result=agent_result,
            deterministic_action=deterministic_action,
            step_name=step_name,
        )

    if autonomy_level == AutonomyLevel.APPROVER:
        logger.info(
            "dispatch.autonomy_validation",
            step_name=step_name,
            autonomy=autonomy_level.value,
            outcome="accepted",
        )
        return DispatchResult(
            output=agent_result,
            mode_used=StepMode.AGENT,
            fallback_used=False,
            autonomy_level=autonomy_level,
            agent_result_accepted=True,
            validation_details="Approver: agent result accepted directly",
        )

    # Unknown autonomy level — fail loudly rather than silently accepting
    raise ValueError(
        f"Unknown autonomy level {autonomy_level!r} in apply_autonomy_gate "
        f"for step '{step_name}'"
    )


def _make_consultant_result(
    *,
    agent_result: Any,
    deterministic_action: Callable[..., Any],
    step_name: str,
) -> DispatchResult:
    """Build a Consultant-level DispatchResult with output contract verification.

    Args:
        agent_result: The agent's output.
        deterministic_action: The deterministic handler (used for type hints).
        step_name: Step name for logging.

    Returns:
        DispatchResult with verification details.
    """
    # Verify output contract: check return type annotation if available
    discrepancies: list[str] = []
    sig = inspect.signature(deterministic_action)
    return_annotation = sig.return_annotation
    if (
        return_annotation is not inspect.Parameter.empty
        and return_annotation is not None
    ):
        try:
            if not isinstance(agent_result, return_annotation):
                discrepancies.append(
                    f"Expected type {return_annotation.__name__}, "
                    f"got {type(agent_result).__name__}"
                )
        except TypeError:
            # isinstance() can fail with complex type hints (generics, unions)
            pass

    if discrepancies:
        details = f"Consultant: verified with discrepancies: {'; '.join(discrepancies)}"
        logger.info(
            "dispatch.autonomy_validation",
            step_name=step_name,
            autonomy="consultant",
            outcome="verified",
            discrepancies=discrepancies,
        )
    else:
        details = "Consultant: output contract verified"
        logger.info(
            "dispatch.autonomy_validation",
            step_name=step_name,
            autonomy="consultant",
            outcome="verified",
        )

    return DispatchResult(
        output=agent_result,
        mode_used=StepMode.AGENT,
        fallback_used=False,
        autonomy_level=AutonomyLevel.CONSULTANT,
        agent_result_accepted=True,
        validation_details=details,
    )


async def _run_deterministic_fallback(
    *,
    action_callable: Callable[..., Any],
    resolved_inputs: dict[str, Any],
    step_name: str,
    autonomy: AutonomyLevel,
    fallback_used: bool,
) -> DispatchResult:
    """Execute deterministic handler as a fallback.

    Args:
        action_callable: The deterministic action.
        resolved_inputs: Already-resolved keyword arguments.
        step_name: Step name for logging.
        autonomy: The autonomy level that was in effect.
        fallback_used: Whether this is a fallback from agent failure.

    Returns:
        DispatchResult with deterministic output.
    """
    start_time = time.monotonic()
    result = await _call_action(action_callable, resolved_inputs)
    duration_ms = int((time.monotonic() - start_time) * 1000)

    logger.info(
        "dispatch.deterministic_completed",
        step_name=step_name,
        duration_ms=duration_ms,
    )

    return DispatchResult(
        output=result,
        mode_used=StepMode.DETERMINISTIC,
        fallback_used=fallback_used,
        autonomy_level=autonomy,
        agent_result_accepted=False if fallback_used else None,
        validation_details="Deterministic fallback" if fallback_used else None,
    )
