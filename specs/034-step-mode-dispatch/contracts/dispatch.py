"""Contract definitions for mode-aware step dispatch.

These type stubs define the public API contracts for the dispatch module.
Implementation lives in src/maverick/dsl/serialization/executor/handlers/dispatch.py.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from maverick.dsl.context import WorkflowContext
from maverick.dsl.executor.config import StepConfig
from maverick.dsl.serialization.executor.handlers.base import EventCallback
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import PythonStepRecord
from maverick.dsl.types import AutonomyLevel, StepMode


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
        """Serialize to a JSON-compatible dictionary."""
        return {
            "mode_used": self.mode_used.value,
            "fallback_used": self.fallback_used,
            "autonomy_level": self.autonomy_level.value,
            "agent_result_accepted": self.agent_result_accepted,
            "validation_details": self.validation_details,
        }


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
        RuntimeError: If both agent and deterministic execution fail.
    """
    ...


async def apply_autonomy_gate(
    *,
    agent_result: Any,
    autonomy_level: AutonomyLevel,
    deterministic_action: Callable[..., Any],
    resolved_inputs: dict[str, Any],
    step_name: str,
) -> DispatchResult:
    """Apply autonomy-level validation/verification to agent result.

    Args:
        agent_result: The result produced by the agent.
        autonomy_level: The configured autonomy level.
        deterministic_action: The deterministic handler for validation.
        resolved_inputs: Inputs for deterministic re-execution.
        step_name: Step name for logging.

    Returns:
        DispatchResult indicating acceptance or rejection.
    """
    ...


def build_agent_prompt(
    *,
    intent: str,
    resolved_inputs: dict[str, Any],
    prompt_suffix: str | None = None,
    prompt_file_content: str | None = None,
) -> tuple[str, str]:
    """Construct agent prompt from intent and inputs.

    Args:
        intent: Plain-language intent description.
        resolved_inputs: Step inputs as structured context.
        prompt_suffix: Optional inline prompt extension.
        prompt_file_content: Optional file-based prompt content.

    Returns:
        Tuple of (instructions, prompt) for StepExecutor.execute().
    """
    ...
