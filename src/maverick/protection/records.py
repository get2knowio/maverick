"""``BlockRecord`` + ``BlockCollector`` — the audit trail for protection.

``BlockRecord.to_dict()`` is the single projection shared by the
``ContextFileWriteBlocked`` event payload and the
``protection-blocks.json`` run artifact — see
``specs/056-context-file-protection/contracts/block-event.md``.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from maverick.logging import get_logger
from maverick.utils.atomic import atomic_write_json

logger = get_logger(__name__)

__all__ = [
    "BlockCollector",
    "BlockRecord",
    "blocks_artifact_dict",
    "drain_and_report",
    "persist_blocks_artifact",
]


@dataclass(frozen=True, slots=True)
class BlockRecord:
    """One prevented write attempt or backstop-undone mutation.

    ``to_dict()`` is the single projection shared by the
    ``ContextFileWriteBlocked`` event payload and a
    ``protection-blocks.json`` ``blocks[]`` entry — they cannot drift.

    Attributes:
        agent_role: Role of the agent that attempted the write, e.g.
            ``"implement"``, ``"review"``, ``"generate"``.
        workflow: Name of the owning workflow, e.g. ``"fly-beads"``,
            ``"spec-chain"``, ``"reconcile"``.
        operation: The write operation attempted or undone. ``"restore"``
            means the backstop undid a mutation that slipped past layer 1;
            its ``detail`` names the inferred original operation.
        path: Repo-relative posix path (resolved).
        destination_path: Destination path for a rename; ``None`` otherwise.
        layer: Which enforcement layer acted — ``"pre-write"`` (the
            permission callback) or ``"backstop"`` (the post-step
            snapshot/restore pass).
        bead_id: The bead this happened inside of, if any.
        detail: Reason or inferred-operation note. Agent-authored strings
            are escaped at render time, not here.
        timestamp: Unix timestamp of the record, defaults to ``time.time()``.
    """

    agent_role: str
    workflow: str
    operation: Literal["create", "edit", "delete", "rename", "restore"]
    path: str
    layer: Literal["pre-write", "backstop"]
    destination_path: str | None = None
    bead_id: str | None = None
    detail: str | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain, JSON-compatible dictionary.

        Returns:
            A dict with exactly the field names of this dataclass as keys —
            no wrapping ``"event"`` key. This is both the
            ``ContextFileWriteBlocked`` event payload projection and a
            ``protection-blocks.json`` ``blocks[]`` entry.
        """
        return {
            "agent_role": self.agent_role,
            "workflow": self.workflow,
            "operation": self.operation,
            "path": self.path,
            "destination_path": self.destination_path,
            "layer": self.layer,
            "bead_id": self.bead_id,
            "detail": self.detail,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BlockRecord:
        """Reconstruct a :class:`BlockRecord` from :meth:`to_dict`'s output.

        Inverse of :meth:`to_dict` — used when a record round-trips
        through a Burr state slot (serialized as a plain dict for
        checkpointing) before being persisted to
        ``protection-blocks.json``.
        """
        return cls(
            agent_role=data["agent_role"],
            workflow=data["workflow"],
            operation=data["operation"],
            path=data["path"],
            layer=data["layer"],
            destination_path=data.get("destination_path"),
            bead_id=data.get("bead_id"),
            detail=data.get("detail"),
            timestamp=data.get("timestamp", time.time()),
        )


class BlockCollector:
    """Mutable per-squadron sink for :class:`BlockRecord`\\ s.

    Same DI shape as ``cost_sink``: constructed once per run, injected into
    every agent, appended to synchronously as blocks occur, and drained by
    the owning workflow at its reporting boundaries.

    Thread-safety is not required — Maverick runs a single event loop — but
    :meth:`append` must be safe to call synchronously from within a
    permission callback mid-execution.
    """

    def __init__(self) -> None:
        """Initialize an empty collector."""
        self._records: list[BlockRecord] = []

    def append(self, record: BlockRecord) -> None:
        """Append ``record`` to the collector.

        Args:
            record: The block record to accumulate.
        """
        self._records.append(record)

    def drain(self) -> list[BlockRecord]:
        """Return all accumulated records and empty the collector.

        Returns:
            The records accumulated since the last :meth:`drain` call, in
            append order. A subsequent call returns an empty list until
            more records are appended.
        """
        records = self._records
        self._records = []
        return records


#: ``protection-blocks.json`` schema version — bump on a breaking shape
#: change; see contracts/block-event.md.
_ARTIFACT_SCHEMA_VERSION = 1


def blocks_artifact_dict(
    *, run_id: str, workflow: str, records: list[BlockRecord]
) -> dict[str, Any]:
    """Build the ``protection-blocks.json`` artifact body.

    Args:
        run_id: The owning run's id (``.maverick/runs/<run_id>/``).
        workflow: The owning workflow's name, e.g. ``"fly-beads"``.
        records: The blocks to include — ``blocks[*]`` is exactly
            ``BlockRecord.to_dict()``, so this artifact and the
            ``ContextFileWriteBlocked`` event stream can never drift.

    Returns:
        The JSON-serializable artifact body per contracts/block-event.md.
    """
    return {
        "schema_version": _ARTIFACT_SCHEMA_VERSION,
        "run_id": run_id,
        "workflow": workflow,
        "generated_at": datetime.now(UTC).isoformat(),
        "blocks": [r.to_dict() for r in records],
    }


async def persist_blocks_artifact(
    *, run_dir: Path, run_id: str, workflow: str, records: list[BlockRecord]
) -> Path | None:
    """Write ``protection-blocks.json`` under ``run_dir``, when non-empty.

    Follows the ``refuel-report.json``/``land-report.json`` precedent:
    one artifact per run, written at completion. Per contracts/block-event.md,
    an empty ``records`` list writes nothing (no empty files) — every
    caller can call this unconditionally at workflow end. A write failure
    degrades to a warning and never fails the run (FR-004's "blocked
    write != bead failure" extends to "can't persist the audit trail !=
    bead failure" too).

    Args:
        run_dir: ``.maverick/runs/<run_id>/`` directory.
        run_id: The owning run's id.
        workflow: The owning workflow's name.
        records: Every block this run accumulated (already drained from
            whatever collector(s)/state slots held them).

    Returns:
        The written path, or ``None`` when there was nothing to write or
        the write failed.
    """
    if not records:
        return None
    path = run_dir / "protection-blocks.json"
    body = blocks_artifact_dict(run_id=run_id, workflow=workflow, records=records)
    try:
        await asyncio.to_thread(atomic_write_json, path, body)
    except OSError as exc:
        logger.warning(
            "protection_blocks_artifact_write_failed",
            run_id=run_id,
            workflow=workflow,
            path=str(path),
            error=str(exc),
        )
        return None
    return path


async def drain_and_report(
    collector: BlockCollector | None,
    *,
    cwd: Path,
    run_id: str,
    workflow: str,
) -> list[BlockRecord]:
    """Drain ``collector`` and persist ``protection-blocks.json``, in one call.

    The shared one-liner for the "remaining agent-bearing workflows"
    (reconcile, refuel ``--enrich``, ``generate_flight_plan``, land
    curation — 056-context-file-protection T025) that build a single
    Squadron/Agent for one workflow run rather than looping through a
    Burr graph: drain at workflow end, persist the artifact when
    non-empty, and hand back the records so the caller emits its own
    one-line warning through whatever output channel it already uses
    (``PythonWorkflow.emit_output`` or a bare console print).

    ``collector=None`` (a squadron whose protection setup degraded) is a
    safe no-op, matching every other degrade path in this feature.

    Args:
        collector: The squadron's block collector, or ``None``.
        cwd: The workflow's cwd — ``.maverick/runs/<run_id>/`` hangs off it.
        run_id: The owning run's id.
        workflow: The owning workflow's name.

    Returns:
        The drained records (empty when there was nothing to drain).
    """
    if collector is None:
        return []
    records = collector.drain()
    if not records:
        return []
    run_dir = cwd / ".maverick" / "runs" / run_id
    await persist_blocks_artifact(
        run_dir=run_dir, run_id=run_id, workflow=workflow, records=records
    )
    return records
