"""Utilities for persisting and loading PhaseResult to/from JSON files."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.models.phase_automation import PhaseResult


def serialize_phase_result(result: PhaseResult) -> dict[str, Any]:
    """Convert PhaseResult to JSON-serializable dictionary.

    Args:
        result: PhaseResult instance to serialize

    Returns:
        Dictionary with all fields converted to JSON-compatible types
    """
    return {
        "phase_id": result.phase_id,
        "status": result.status,
        "completed_task_ids": list(result.completed_task_ids),
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat(),
        "duration_ms": result.duration_ms,
        "tasks_md_hash": result.tasks_md_hash,
        "stdout_path": result.stdout_path,
        "stderr_path": result.stderr_path,
        "artifact_paths": list(result.artifact_paths),
        "summary": list(result.summary),
        "error": result.error,
    }


def deserialize_phase_result(data: dict[str, Any]) -> PhaseResult:
    """Reconstruct PhaseResult from JSON dictionary.

    Args:
        data: Dictionary containing serialized PhaseResult fields

    Returns:
        PhaseResult instance

    Raises:
        ValueError: If data contains invalid timestamp format or missing required fields
        KeyError: If required fields are missing from data
    """
    try:
        started_at = datetime.fromisoformat(data["started_at"])
        finished_at = datetime.fromisoformat(data["finished_at"])
    except (ValueError, KeyError) as e:
        if isinstance(e, ValueError):
            raise ValueError(f"Invalid timestamp format: {e}") from e
        raise

    return PhaseResult(
        phase_id=data["phase_id"],
        status=data["status"],
        completed_task_ids=tuple(data["completed_task_ids"]),
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=data["duration_ms"],
        tasks_md_hash=data["tasks_md_hash"],
        stdout_path=data["stdout_path"],
        stderr_path=data["stderr_path"],
        artifact_paths=tuple(data["artifact_paths"]),
        summary=tuple(data["summary"]),
        error=data.get("error"),
    )


def save_phase_result(result: PhaseResult, output_path: Path) -> None:
    """Persist PhaseResult to JSON file.

    Creates parent directories if they don't exist. Overwrites existing file.

    Args:
        result: PhaseResult to save
        output_path: Target file path (will create parent directories)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    serialized = serialize_phase_result(result)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(serialized, f, indent=2, ensure_ascii=False)


def load_phase_result(input_path: Path) -> PhaseResult:
    """Load PhaseResult from JSON file.

    Args:
        input_path: Path to JSON file containing serialized PhaseResult

    Returns:
        Deserialized PhaseResult instance

    Raises:
        FileNotFoundError: If input_path does not exist
        ValueError: If file contains invalid JSON or cannot be deserialized
    """
    if not input_path.exists():
        raise FileNotFoundError(f"Phase result file not found: {input_path}")

    try:
        with input_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from {input_path}: {e}") from e

    return deserialize_phase_result(data)


__all__ = [
    "deserialize_phase_result",
    "load_phase_result",
    "save_phase_result",
    "serialize_phase_result",
]
