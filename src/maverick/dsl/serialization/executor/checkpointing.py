"""Checkpoint handling for workflow execution.

This module provides utilities for saving and resuming workflow execution state.
"""

from __future__ import annotations

from typing import Any

from maverick.dsl.checkpoint.data import CheckpointData, compute_inputs_hash
from maverick.dsl.checkpoint.store import CheckpointStore
from maverick.dsl.serialization.schema import CheckpointStepRecord, WorkflowFile
from maverick.logging import get_logger

logger = get_logger(__name__)


async def load_checkpoint_if_resuming(
    workflow: WorkflowFile,
    inputs: dict[str, Any],
    resume_from_checkpoint: bool,
    checkpoint_store: CheckpointStore,
) -> tuple[CheckpointData | None, str | None]:
    """Load checkpoint data if resuming execution.

    Args:
        workflow: Workflow being executed.
        inputs: Workflow inputs.
        resume_from_checkpoint: Whether to attempt resume.
        checkpoint_store: Store to load checkpoint from.

    Returns:
        Tuple of (checkpoint_data, resume_after_step).
        Both are None if not resuming.

    Raises:
        ValueError: If inputs don't match checkpoint inputs.
    """
    if not resume_from_checkpoint:
        return None, None

    checkpoint_data = await checkpoint_store.load_latest(workflow.name)

    if checkpoint_data is None:
        logger.info(
            f"No checkpoint found for workflow '{workflow.name}', executing from start"
        )
        return None, None

    # Validate inputs match checkpoint (FR-025b)
    current_inputs_hash = compute_inputs_hash(inputs)
    if current_inputs_hash != checkpoint_data.inputs_hash:
        raise ValueError(
            f"Cannot resume workflow '{workflow.name}' from checkpoint "
            f"'{checkpoint_data.checkpoint_id}': Current workflow "
            f"inputs differ from checkpoint inputs. To resume, use "
            f"the same inputs as the original run. Checkpoint was "
            f"saved at {checkpoint_data.saved_at}. "
            f"Use `maverick workflow run {workflow.name} --help` "
            f"to see required inputs."
        )

    resume_after_step = checkpoint_data.checkpoint_id
    logger.info(
        f"Resuming workflow '{workflow.name}' from checkpoint "
        f"'{checkpoint_data.checkpoint_id}' "
        f"(saved at {checkpoint_data.saved_at})"
    )

    return checkpoint_data, resume_after_step


def restore_context_from_checkpoint(
    checkpoint_data: CheckpointData | None,
    context: Any,  # WorkflowContext but avoiding circular import
) -> None:
    """Restore step results from checkpoint data into context.

    Args:
        checkpoint_data: Checkpoint data containing saved step results.
        context: WorkflowContext to restore into (modified in-place).
    """
    if checkpoint_data is None:
        return

    for step_result_dict in checkpoint_data.step_results:
        step_name = step_result_dict["name"]
        step_output = step_result_dict["output"]
        # Store as StepResult in context (step_type is unknown from checkpoint)
        context.store_step_output(step_name, step_output, step_type="python")
        logger.debug(f"Restored step output for '{step_name}' from checkpoint")


def should_skip_step(
    step: Any,
    resume_after_step: str | None,
    past_resume_point: bool,
) -> tuple[bool, bool]:
    """Determine if a step should be skipped during resume.

    Args:
        step: Step record to check.
        resume_after_step: The checkpoint ID to resume from.
        past_resume_point: Whether we've already passed the resume point.

    Returns:
        Tuple of (should_skip, new_past_resume_point).
    """
    if past_resume_point:
        return False, True

    # Check if this is a checkpoint step that matches our resume point
    if isinstance(step, CheckpointStepRecord):
        checkpoint_id = step.checkpoint_id or step.name
        if checkpoint_id == resume_after_step:
            # We've reached the resume checkpoint, start executing after this
            logger.info(
                f"Reached resume checkpoint '{checkpoint_id}', "
                f"continuing execution from next step"
            )
            return True, True  # Skip this checkpoint step, but mark past resume

    # Skip all steps before resume point
    logger.debug(f"Skipping step '{step.name}' (before resume checkpoint)")
    return True, False
