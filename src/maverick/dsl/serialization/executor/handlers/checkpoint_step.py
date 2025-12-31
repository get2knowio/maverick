"""Checkpoint step handler for saving workflow state.

This module handles execution of CheckpointStepRecord steps.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from maverick.dsl.checkpoint.data import CheckpointData, compute_inputs_hash
from maverick.dsl.checkpoint.store import CheckpointStore
from maverick.dsl.context import WorkflowContext
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import CheckpointStepRecord
from maverick.logging import get_logger

logger = get_logger(__name__)


async def execute_checkpoint_step(
    step: CheckpointStepRecord,
    resolved_inputs: dict[str, Any],
    context: WorkflowContext,
    registry: ComponentRegistry,
    config: Any = None,
    checkpoint_store: CheckpointStore | None = None,
) -> Any:
    """Execute a checkpoint step.

    A checkpoint step marks a workflow state boundary for resumability.
    When executed, it saves the current workflow state (inputs, completed
    steps, outputs) to the checkpoint store. Returns success indicator.

    Args:
        step: CheckpointStepRecord containing checkpoint configuration.
        resolved_inputs: Resolved values (unused for checkpoint).
        context: WorkflowContext with inputs and step results.
        registry: Component registry (unused).
        config: Optional configuration (unused).
        checkpoint_store: CheckpointStore to save to (required).

    Returns:
        Dictionary with checkpoint status:
            - saved: Boolean indicating checkpoint was saved
            - checkpoint_id: The checkpoint identifier used
            - timestamp: ISO 8601 timestamp of save

    Raises:
        ValueError: If checkpoint_store is not provided.
    """
    if checkpoint_store is None:
        raise ValueError("checkpoint_store is required for checkpoint step execution")

    # Determine checkpoint ID (use explicit ID or step name)
    checkpoint_id = step.checkpoint_id or step.name

    # Get workflow name and inputs from context
    workflow_name = context.workflow_name or "unknown"
    workflow_inputs = context.inputs

    # Compute input hash for validation on resume
    inputs_hash = compute_inputs_hash(workflow_inputs)

    # Serialize step results for persistence
    # Convert StepResult objects to dicts
    step_results_dicts = []
    for step_name, step_result in context.results.items():
        output = step_result.output
        # If output has a to_dict() method, use it for serialization
        if hasattr(output, "to_dict") and callable(output.to_dict):
            output = output.to_dict()
        # Store minimal data needed for resume
        step_results_dicts.append(
            {
                "name": step_name,
                "output": output,
            }
        )

    # Create checkpoint data
    timestamp = datetime.now(UTC).isoformat()
    checkpoint_data = CheckpointData(
        checkpoint_id=checkpoint_id,
        workflow_name=workflow_name,
        inputs_hash=inputs_hash,
        step_results=tuple(step_results_dicts),
        saved_at=timestamp,
    )

    # Save checkpoint to store
    try:
        await checkpoint_store.save(workflow_name, checkpoint_data)
        logger.info(
            f"Checkpoint '{checkpoint_id}' saved for workflow '{workflow_name}'"
        )
    except Exception as e:
        logger.error(
            f"Failed to save checkpoint '{checkpoint_id}' for workflow "
            f"'{workflow_name}': {e}"
        )
        # Don't fail workflow on checkpoint save error (best effort)

    return {
        "saved": True,
        "checkpoint_id": checkpoint_id,
        "timestamp": timestamp,
    }
