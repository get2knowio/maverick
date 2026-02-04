"""Session journal for logging workflow events to JSONL files.

Provides a ``SessionJournal`` that records every workflow progress event as
one JSON object per line.  Users can run a workflow, watch it live, then
come back later to analyse the log.

Usage::

    from maverick.session_journal import SessionJournal

    journal = SessionJournal(Path("session.jsonl"))
    journal.write_header("my-workflow", {"branch": "main"})
    async for event in executor.execute(workflow, inputs):
        await journal.record(event)
    journal.write_summary({"success": True, "duration_ms": 12345})
    journal.close()
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from maverick.dsl.events import ProgressEvent
from maverick.logging import get_logger

__all__ = ["SessionJournal"]

logger = get_logger(__name__)


class SessionJournal:
    """Append-only JSONL writer for workflow progress events.

    Each line written is a self-contained JSON object with at least an
    ``"event"`` key indicating the record type and a ``"ts"`` key with
    the Unix timestamp.

    The journal can optionally filter out ``AgentStreamChunk`` events
    (which can be very high-volume) via *include_agent_text*.

    Args:
        path: Destination file path.  Parent directories are created
            automatically if they do not exist.
        include_agent_text: When ``False``, ``AgentStreamChunk`` events
            are silently dropped.  Defaults to ``True``.
    """

    def __init__(
        self,
        path: Path,
        include_agent_text: bool = True,
    ) -> None:
        self._path = path
        self._include_agent_text = include_agent_text
        self._file: Any = None
        self._event_count: int = 0
        self._open()

    # ------------------------------------------------------------------
    # File lifecycle
    # ------------------------------------------------------------------

    def _open(self) -> None:
        """Open the JSONL file for appending."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self._path, "a", encoding="utf-8")  # noqa: SIM115
        logger.info(
            "session_journal_opened",
            path=str(self._path),
        )

    def close(self) -> None:
        """Flush and close the backing file.

        Safe to call multiple times.
        """
        if self._file is not None and not self._file.closed:
            self._file.flush()
            self._file.close()
            logger.info(
                "session_journal_closed",
                path=str(self._path),
                event_count=self._event_count,
            )
        self._file = None

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> SessionJournal:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Writing records
    # ------------------------------------------------------------------

    def _write_line(self, data: dict[str, Any]) -> None:
        """Serialize *data* as a single JSON line and write it."""
        if self._file is None or self._file.closed:
            return
        line = json.dumps(data, default=str, ensure_ascii=False)
        self._file.write(line + "\n")
        # Flush after each line so the journal is crash-safe
        self._file.flush()

    def write_header(
        self,
        workflow_name: str,
        inputs: dict[str, Any],
    ) -> None:
        """Write a session header record as the first line.

        Args:
            workflow_name: Name of the workflow being executed.
            inputs: Input parameters provided to the workflow.
        """
        self._write_line(
            {
                "event": "session_start",
                "ts": time.time(),
                "workflow_name": workflow_name,
                "inputs": inputs,
            }
        )

    def write_summary(self, summary: dict[str, Any]) -> None:
        """Write a session summary record as the last line.

        Args:
            summary: Arbitrary summary data (success flag, duration, etc.).
        """
        self._write_line(
            {
                "event": "session_end",
                "ts": time.time(),
                "event_count": self._event_count,
                **summary,
            }
        )

    async def record(self, event: ProgressEvent) -> None:
        """Serialize and write a single workflow event.

        Events that expose a ``to_dict()`` method are serialized via that
        method.  For any other event type (e.g. ``RollbackError`` from
        ``maverick.dsl.results``) we fall back to ``{"event": class_name}``.

        ``AgentStreamChunk`` events are skipped when *include_agent_text*
        is ``False``.

        Args:
            event: The workflow progress event to record.
        """
        from maverick.dsl.events import AgentStreamChunk

        if not self._include_agent_text and isinstance(event, AgentStreamChunk):
            return

        if hasattr(event, "to_dict"):
            data = event.to_dict()
        else:
            # Fallback for types without to_dict (e.g. RollbackError)
            data = {"event": type(event).__name__}
            if hasattr(event, "step_name"):
                data["step_name"] = event.step_name
            if hasattr(event, "error"):
                data["error"] = event.error

        self._write_line(data)
        self._event_count += 1

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def path(self) -> Path:
        """Return the path to the JSONL file."""
        return self._path

    @property
    def event_count(self) -> int:
        """Return the number of events recorded so far."""
        return self._event_count

    @property
    def is_open(self) -> bool:
        """Return whether the journal file is still open."""
        return self._file is not None and not self._file.closed
