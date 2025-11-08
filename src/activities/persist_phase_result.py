"""Activity for persisting phase results to disk.

Logging Events (structured logger):
    - persist_phase_result_started: Begin persisting phase result
    - persist_phase_result_completed: Successfully saved result to disk
    - persist_phase_result_failed: Failed to write result file
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from temporalio import activity

from src.models.phase_automation import PhaseResult
from src.utils.logging import get_structured_logger
from src.utils.phase_results_store import save_phase_result


logger = get_structured_logger("activity.persist_phase_result")


@dataclass(frozen=True)
class PersistPhaseResultRequest:
    """Request to persist a phase result to disk."""

    workflow_id: str
    phase_result: PhaseResult
    results_base_dir: str = "/tmp/phase-results"


@activity.defn(name="persist_phase_result")
async def persist_phase_result(request: PersistPhaseResultRequest) -> str:
    """Persist phase result to JSON file.

    Args:
        request: Contains workflow ID, phase result, and optional base directory

    Returns:
        Path to the persisted file as a string

    Raises:
        OSError: If file cannot be written
    """
    logger.info(
        "persist_phase_result_started",
        workflow_id=request.workflow_id,
        phase_id=request.phase_result.phase_id,
    )

    results_dir = Path(request.results_base_dir)
    workflow_dir = results_dir / request.workflow_id
    output_file = workflow_dir / f"{request.phase_result.phase_id}.json"

    try:
        save_phase_result(request.phase_result, output_file)

        logger.info(
            "persist_phase_result_completed",
            workflow_id=request.workflow_id,
            phase_id=request.phase_result.phase_id,
            output_path=str(output_file),
        )

        return str(output_file)

    except OSError as e:
        logger.error(
            "persist_phase_result_failed",
            workflow_id=request.workflow_id,
            phase_id=request.phase_result.phase_id,
            error=str(e),
        )
        raise


__all__ = ["PersistPhaseResultRequest", "persist_phase_result"]
