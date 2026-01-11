"""Checkpoint handling for workflow execution.

This module provides utilities for saving and resuming workflow execution state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from maverick.dsl.checkpoint.data import CheckpointData, compute_inputs_hash
from maverick.dsl.checkpoint.store import CheckpointStore
from maverick.dsl.serialization.schema import (
    CheckpointStepRecord,
    LoopStepRecord,
    WorkflowFile,
)
from maverick.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class CheckpointLocation:
    """Location of a checkpoint within a workflow.

    Tracks where a checkpoint is located, including whether it's nested
    inside a loop and which iteration it belongs to.

    Attributes:
        step_index: Index of the top-level step containing the checkpoint.
        step_name: Name of the containing step.
        is_nested: True if the checkpoint is inside a loop or branch.
        iteration_index: For loop checkpoints, the iteration index (0-based).
        nested_step_index: Index of the checkpoint step within the container.
        nested_step_name: Name of the nested checkpoint step.
    """

    step_index: int
    step_name: str
    is_nested: bool
    iteration_index: int | None = None
    nested_step_index: int | None = None
    nested_step_name: str | None = None


def find_checkpoint_location(
    workflow: WorkflowFile,
    checkpoint_id: str,
) -> CheckpointLocation | None:
    """Find the location of a checkpoint by its ID.

    Searches through the workflow's steps, including nested steps in loops,
    to find where the checkpoint with the given ID is defined.

    For loop checkpoints with dynamic IDs (e.g., "phase_${{ index }}_complete"),
    this function extracts the iteration index from the checkpoint ID.

    Args:
        workflow: Workflow to search.
        checkpoint_id: The checkpoint ID to find.

    Returns:
        CheckpointLocation if found, None otherwise.
    """
    for step_index, step in enumerate(workflow.steps):
        # Check top-level checkpoint steps
        if isinstance(step, CheckpointStepRecord):
            step_checkpoint_id = step.checkpoint_id or step.name
            if step_checkpoint_id == checkpoint_id:
                return CheckpointLocation(
                    step_index=step_index,
                    step_name=step.name,
                    is_nested=False,
                )

        # Search inside loop steps
        elif isinstance(step, LoopStepRecord):
            location = _find_checkpoint_in_loop(step, step_index, checkpoint_id)
            if location is not None:
                return location

    return None


def _find_checkpoint_in_loop(
    loop_step: LoopStepRecord,
    loop_step_index: int,
    checkpoint_id: str,
) -> CheckpointLocation | None:
    """Search for a checkpoint inside a loop step.

    Handles dynamic checkpoint IDs that contain ${{ index }} expressions
    by pattern matching to extract the iteration index.

    Args:
        loop_step: The loop step to search.
        loop_step_index: Index of the loop step in the workflow.
        checkpoint_id: The checkpoint ID to find.

    Returns:
        CheckpointLocation if found, None otherwise.
    """
    for nested_index, nested_step in enumerate(loop_step.steps):
        if not isinstance(nested_step, CheckpointStepRecord):
            continue

        # Get the checkpoint ID template
        template_id = nested_step.checkpoint_id or nested_step.name

        # Check for exact match (static checkpoint ID)
        if template_id == checkpoint_id:
            return CheckpointLocation(
                step_index=loop_step_index,
                step_name=loop_step.name,
                is_nested=True,
                iteration_index=None,
                nested_step_index=nested_index,
                nested_step_name=nested_step.name,
            )

        # Check for pattern match (dynamic checkpoint ID with ${{ index }})
        iteration_index = _extract_iteration_index(template_id, checkpoint_id)
        if iteration_index is not None:
            return CheckpointLocation(
                step_index=loop_step_index,
                step_name=loop_step.name,
                is_nested=True,
                iteration_index=iteration_index,
                nested_step_index=nested_index,
                nested_step_name=nested_step.name,
            )

    return None


def _extract_iteration_index(
    template_id: str,
    actual_id: str,
) -> int | None:
    """Extract iteration index from a checkpoint ID using the template pattern.

    Converts a template like "phase_${{ index }}_complete" to a regex pattern
    and matches it against the actual ID to extract the iteration index.

    Args:
        template_id: Checkpoint ID template with ${{ index }} placeholder.
        actual_id: Actual checkpoint ID to match.

    Returns:
        Iteration index (0-based) if pattern matches, None otherwise.
    """
    # Check if template contains index expression
    if "${{" not in template_id or "index" not in template_id:
        return None

    # Replace the ${{ index }} expression with a placeholder before escaping
    # This handles both ${{ index }} and ${{index}} (with/without spaces)
    placeholder = "__MAVERICK_INDEX_PLACEHOLDER__"
    template_with_placeholder = re.sub(
        r"\$\{\{\s*index\s*\}\}",
        placeholder,
        template_id,
    )

    # Escape regex special characters in the modified template
    escaped = re.escape(template_with_placeholder)

    # Replace the escaped placeholder with a capture group for digits
    pattern = escaped.replace(placeholder, r"(\d+)")

    # Match the pattern against the actual ID
    match = re.fullmatch(pattern, actual_id)
    if match:
        return int(match.group(1))

    return None


async def load_checkpoint_if_resuming(
    workflow: WorkflowFile,
    inputs: dict[str, Any],
    resume_from_checkpoint: bool,
    checkpoint_store: CheckpointStore,
) -> tuple[CheckpointData | None, str | None, CheckpointLocation | None]:
    """Load checkpoint data if resuming execution.

    Args:
        workflow: Workflow being executed.
        inputs: Workflow inputs.
        resume_from_checkpoint: Whether to attempt resume.
        checkpoint_store: Store to load checkpoint from.

    Returns:
        Tuple of (checkpoint_data, resume_after_step, checkpoint_location).
        All are None if not resuming. checkpoint_location may be None if
        the checkpoint is not found in the workflow (legacy/manual checkpoint).

    Raises:
        ValueError: If inputs don't match checkpoint inputs.
    """
    if not resume_from_checkpoint:
        return None, None, None

    checkpoint_data = await checkpoint_store.load_latest(workflow.name)

    if checkpoint_data is None:
        logger.info(
            f"No checkpoint found for workflow '{workflow.name}', executing from start"
        )
        return None, None, None

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

    # Find where the checkpoint is located in the workflow
    checkpoint_location = find_checkpoint_location(workflow, resume_after_step)
    if checkpoint_location:
        if checkpoint_location.is_nested:
            logger.debug(
                f"Checkpoint '{resume_after_step}' is nested in step "
                f"'{checkpoint_location.step_name}' at iteration "
                f"{checkpoint_location.iteration_index}"
            )
        else:
            logger.debug(
                f"Checkpoint '{resume_after_step}' is at top-level step index "
                f"{checkpoint_location.step_index}"
            )
    else:
        logger.warning(
            f"Could not find checkpoint '{resume_after_step}' in workflow "
            f"'{workflow.name}'. Resume may not work correctly."
        )

    return checkpoint_data, resume_after_step, checkpoint_location


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
    step_index: int | None = None,
    checkpoint_location: CheckpointLocation | None = None,
) -> tuple[bool, bool]:
    """Determine if a step should be skipped during resume.

    This function handles both top-level checkpoints (backward compatible)
    and nested checkpoints inside loops when checkpoint_location is provided.

    Args:
        step: Step record to check.
        resume_after_step: The checkpoint ID to resume from.
        past_resume_point: Whether we've already passed the resume point.
        step_index: Current step index in the workflow (for location matching).
        checkpoint_location: Location of the checkpoint if found in workflow.

    Returns:
        Tuple of (should_skip, new_past_resume_point).
    """
    if past_resume_point:
        return False, True

    # If we have a checkpoint location for a nested checkpoint, use it
    if checkpoint_location is not None and checkpoint_location.is_nested:
        if step_index is not None:
            # Skip steps before the container step
            if step_index < checkpoint_location.step_index:
                logger.debug(
                    f"Skipping step '{step.name}' (before container step "
                    f"'{checkpoint_location.step_name}')"
                )
                return True, False

            # This is the container step (loop) - execute it with resume info
            # The loop handler will skip to the right iteration
            if step_index == checkpoint_location.step_index:
                logger.info(
                    f"Resuming into step '{step.name}' which contains checkpoint"
                )
                # Don't skip this step, but also don't mark past resume yet
                # The loop handler will handle internal skipping
                return False, False

            # Steps after the container step should run normally
            # past_resume_point should be True after the loop completes
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
