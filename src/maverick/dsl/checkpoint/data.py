"""Checkpoint data structures.

This module defines the CheckpointData dataclass for persisting
workflow state at checkpoint boundaries.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


def compute_inputs_hash(inputs: dict[str, Any]) -> str:
    """Compute deterministic hash of workflow inputs.

    Args:
        inputs: Workflow input parameters.

    Returns:
        16-character hex hash of the inputs.
    """
    # Sort keys for determinism
    serialized = json.dumps(inputs, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class CheckpointData:
    """Data persisted at a workflow checkpoint.

    Attributes:
        checkpoint_id: Unique identifier for this checkpoint (step name).
        workflow_name: Name of the workflow being checkpointed.
        inputs_hash: SHA-256 hash (first 16 chars) of serialized inputs.
        step_results: Tuple of serialized StepResult dicts.
        saved_at: ISO 8601 timestamp of checkpoint creation.
    """

    checkpoint_id: str
    workflow_name: str
    inputs_hash: str
    step_results: tuple[dict[str, Any], ...]
    saved_at: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize for persistence."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "workflow_name": self.workflow_name,
            "inputs_hash": self.inputs_hash,
            "step_results": list(self.step_results),
            "saved_at": self.saved_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CheckpointData:
        """Deserialize from dictionary.

        Args:
            data: Dictionary representation.

        Returns:
            CheckpointData instance.
        """
        return cls(
            checkpoint_id=data["checkpoint_id"],
            workflow_name=data["workflow_name"],
            inputs_hash=data["inputs_hash"],
            step_results=tuple(data["step_results"]),
            saved_at=data["saved_at"],
        )
