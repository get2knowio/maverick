"""Unit tests for session journal and event serialization.

Tests cover:
- ``_event_to_dict`` helper and ``to_dict()`` on all event dataclasses
- ``SessionJournal`` lifecycle, recording, filtering, and context-manager
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maverick.dsl.events import (
    AgentStreamChunk,
    CheckpointSaved,
    LoopIterationCompleted,
    LoopIterationStarted,
    PreflightCheckFailed,
    PreflightCheckPassed,
    PreflightCompleted,
    PreflightStarted,
    RollbackCompleted,
    RollbackStarted,
    StepCompleted,
    StepOutput,
    StepStarted,
    ValidationCompleted,
    ValidationFailed,
    ValidationStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.dsl.results import RollbackError
from maverick.dsl.types import StepType
from maverick.session_journal import SessionJournal

# =========================================================================
# _event_to_dict helper tests
# =========================================================================


class TestEventToDict:
    """Tests for the ``_event_to_dict`` serialization helper."""

    def test_step_started_basic(self) -> None:
        """StepStarted produces correct dict with StepType converted."""
        event = StepStarted(
            step_name="build",
            step_type=StepType.PYTHON,
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["event"] == "StepStarted"
        assert d["step_name"] == "build"
        assert d["step_type"] == "python"
        assert d["timestamp"] == 1000.0

    def test_step_completed_all_fields(self) -> None:
        """StepCompleted includes all fields."""
        event = StepCompleted(
            step_name="review",
            step_type=StepType.AGENT,
            success=True,
            duration_ms=1500,
            error=None,
            timestamp=2000.0,
        )
        d = event.to_dict()
        assert d["event"] == "StepCompleted"
        assert d["step_type"] == "agent"
        assert d["success"] is True
        assert d["duration_ms"] == 1500

    def test_preflight_started_tuple_to_list(self) -> None:
        """PreflightStarted converts prerequisites tuple to list."""
        event = PreflightStarted(
            prerequisites=("git", "python"),
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["event"] == "PreflightStarted"
        assert d["prerequisites"] == ["git", "python"]
        assert isinstance(d["prerequisites"], list)

    def test_preflight_check_passed(self) -> None:
        """PreflightCheckPassed serializes correctly."""
        event = PreflightCheckPassed(
            name="git_identity",
            display_name="Git Identity",
            duration_ms=12,
            message="OK",
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["event"] == "PreflightCheckPassed"
        assert d["name"] == "git_identity"
        assert d["duration_ms"] == 12

    def test_preflight_check_failed_with_affected_steps(self) -> None:
        """PreflightCheckFailed converts affected_steps tuple to list."""
        event = PreflightCheckFailed(
            name="docker",
            display_name="Docker",
            duration_ms=5,
            message="Not found",
            remediation="Install Docker",
            affected_steps=("build", "deploy"),
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["affected_steps"] == ["build", "deploy"]
        assert isinstance(d["affected_steps"], list)

    def test_preflight_completed(self) -> None:
        """PreflightCompleted serializes correctly."""
        event = PreflightCompleted(
            success=True,
            total_duration_ms=50,
            passed_count=3,
            failed_count=0,
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["event"] == "PreflightCompleted"
        assert d["success"] is True
        assert d["passed_count"] == 3

    def test_workflow_started_dict_copied(self) -> None:
        """WorkflowStarted copies dict inputs for safety."""
        original_inputs = {"branch": "main"}
        event = WorkflowStarted(
            workflow_name="fly",
            inputs=original_inputs,
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["inputs"] == {"branch": "main"}
        # Modifying the serialized dict should not affect the original
        d["inputs"]["branch"] = "dev"
        assert original_inputs["branch"] == "main"

    def test_workflow_completed(self) -> None:
        """WorkflowCompleted serializes correctly."""
        event = WorkflowCompleted(
            workflow_name="fly",
            success=False,
            total_duration_ms=5000,
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["event"] == "WorkflowCompleted"
        assert d["success"] is False
        assert d["total_duration_ms"] == 5000

    def test_rollback_started(self) -> None:
        """RollbackStarted serializes correctly."""
        event = RollbackStarted(
            step_name="deploy",
            timestamp=1000.0,
            step_path="loop/[0]/deploy",
        )
        d = event.to_dict()
        assert d["event"] == "RollbackStarted"
        assert d["step_path"] == "loop/[0]/deploy"

    def test_rollback_completed(self) -> None:
        """RollbackCompleted serializes correctly."""
        event = RollbackCompleted(
            step_name="deploy",
            success=False,
            error="Rollback failed",
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["event"] == "RollbackCompleted"
        assert d["error"] == "Rollback failed"

    def test_checkpoint_saved(self) -> None:
        """CheckpointSaved serializes correctly."""
        event = CheckpointSaved(
            step_name="save_state",
            workflow_id="wf-123",
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["event"] == "CheckpointSaved"
        assert d["workflow_id"] == "wf-123"

    def test_validation_started(self) -> None:
        """ValidationStarted serializes correctly."""
        event = ValidationStarted(
            workflow_name="fly",
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["event"] == "ValidationStarted"

    def test_validation_completed(self) -> None:
        """ValidationCompleted serializes correctly."""
        event = ValidationCompleted(
            workflow_name="fly",
            warnings_count=2,
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["event"] == "ValidationCompleted"
        assert d["warnings_count"] == 2

    def test_validation_failed_errors_tuple_to_list(self) -> None:
        """ValidationFailed converts errors tuple to list."""
        event = ValidationFailed(
            workflow_name="fly",
            errors=("Missing step", "Bad ref"),
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["errors"] == ["Missing step", "Bad ref"]
        assert isinstance(d["errors"], list)

    def test_loop_iteration_started(self) -> None:
        """LoopIterationStarted serializes correctly."""
        event = LoopIterationStarted(
            step_name="process_items",
            iteration_index=1,
            total_iterations=5,
            item_label="Item 2",
            parent_step_name="outer_loop",
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["event"] == "LoopIterationStarted"
        assert d["iteration_index"] == 1
        assert d["total_iterations"] == 5
        assert d["parent_step_name"] == "outer_loop"

    def test_loop_iteration_completed(self) -> None:
        """LoopIterationCompleted serializes correctly."""
        event = LoopIterationCompleted(
            step_name="process_items",
            iteration_index=2,
            success=True,
            duration_ms=300,
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["event"] == "LoopIterationCompleted"
        assert d["duration_ms"] == 300

    def test_agent_stream_chunk(self) -> None:
        """AgentStreamChunk serializes correctly."""
        event = AgentStreamChunk(
            step_name="impl",
            agent_name="ImplementerAgent",
            text="Hello world",
            chunk_type="output",
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["event"] == "AgentStreamChunk"
        assert d["text"] == "Hello world"
        assert d["chunk_type"] == "output"

    def test_step_output(self) -> None:
        """StepOutput serializes correctly with metadata."""
        event = StepOutput(
            step_name="fetch_pr",
            message="Fetching PR #123",
            level="info",
            source="github",
            metadata={"pr_number": 123},
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["event"] == "StepOutput"
        assert d["message"] == "Fetching PR #123"
        assert d["source"] == "github"
        assert d["metadata"] == {"pr_number": 123}

    def test_step_output_none_metadata(self) -> None:
        """StepOutput with None metadata serializes correctly."""
        event = StepOutput(
            step_name="test",
            message="testing",
            timestamp=1000.0,
        )
        d = event.to_dict()
        assert d["metadata"] is None

    def test_event_to_dict_produces_json_serializable_output(self) -> None:
        """All event to_dict outputs must be JSON-serializable."""
        events = [
            StepStarted("s", StepType.PYTHON, 1.0),
            StepCompleted("s", StepType.AGENT, True, 100, timestamp=1.0),
            PreflightStarted(("a", "b"), 1.0),
            PreflightCheckPassed("n", "N", 10, "ok", 1.0),
            PreflightCheckFailed("n", "N", 10, "bad", timestamp=1.0),
            PreflightCompleted(True, 50, 2, 0, 1.0),
            WorkflowStarted("w", {"k": "v"}, 1.0),
            WorkflowCompleted("w", True, 1000, 1.0),
            RollbackStarted("s", 1.0),
            RollbackCompleted("s", True, timestamp=1.0),
            CheckpointSaved("s", "wf-1", 1.0),
            ValidationStarted("w", 1.0),
            ValidationCompleted("w", 0, 1.0),
            ValidationFailed("w", ("err",), 1.0),
            LoopIterationStarted("l", 0, 3, "Item 1", timestamp=1.0),
            LoopIterationCompleted("l", 0, True, 100, timestamp=1.0),
            AgentStreamChunk("s", "Agent", "hi", "output", 1.0),
            StepOutput("s", "msg", timestamp=1.0),
        ]
        for event in events:
            d = event.to_dict()
            # Must not raise
            serialized = json.dumps(d, default=str)
            assert isinstance(serialized, str)


# =========================================================================
# SessionJournal tests
# =========================================================================


class TestSessionJournal:
    """Tests for the ``SessionJournal`` JSONL writer."""

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Journal creates parent directories on init."""
        log_path = tmp_path / "deep" / "nested" / "session.jsonl"
        journal = SessionJournal(log_path)
        assert log_path.parent.exists()
        journal.close()

    def test_write_header(self, tmp_path: Path) -> None:
        """write_header writes a session_start record."""
        log_path = tmp_path / "session.jsonl"
        journal = SessionJournal(log_path)
        journal.write_header("my-workflow", {"branch": "main"})
        journal.close()

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "session_start"
        assert record["workflow_name"] == "my-workflow"
        assert record["inputs"] == {"branch": "main"}
        assert "ts" in record

    def test_write_summary(self, tmp_path: Path) -> None:
        """write_summary writes a session_end record with event count."""
        log_path = tmp_path / "session.jsonl"
        journal = SessionJournal(log_path)
        journal.write_summary({"success": True, "total_duration_ms": 5000})
        journal.close()

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "session_end"
        assert record["success"] is True
        assert record["event_count"] == 0

    @pytest.mark.asyncio
    async def test_record_event_with_to_dict(self, tmp_path: Path) -> None:
        """record() serializes events that have to_dict()."""
        log_path = tmp_path / "session.jsonl"
        journal = SessionJournal(log_path)

        event = StepStarted(
            step_name="test_step",
            step_type=StepType.PYTHON,
            timestamp=1000.0,
        )
        await journal.record(event)
        journal.close()

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "StepStarted"
        assert record["step_name"] == "test_step"
        assert record["step_type"] == "python"
        assert journal.event_count == 1

    @pytest.mark.asyncio
    async def test_record_rollback_error_fallback(self, tmp_path: Path) -> None:
        """record() handles RollbackError which has its own to_dict()."""
        log_path = tmp_path / "session.jsonl"
        journal = SessionJournal(log_path)

        event = RollbackError(step_name="deploy", error="Failed")
        await journal.record(event)
        journal.close()

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["step_name"] == "deploy"
        assert record["error"] == "Failed"

    @pytest.mark.asyncio
    async def test_filter_agent_stream_chunks(self, tmp_path: Path) -> None:
        """When include_agent_text=False, AgentStreamChunk events are dropped."""
        log_path = tmp_path / "session.jsonl"
        journal = SessionJournal(log_path, include_agent_text=False)

        chunk = AgentStreamChunk(
            step_name="impl",
            agent_name="Agent",
            text="Hello",
            chunk_type="output",
            timestamp=1000.0,
        )
        step = StepStarted(
            step_name="impl",
            step_type=StepType.AGENT,
            timestamp=1000.0,
        )

        await journal.record(chunk)
        await journal.record(step)
        journal.close()

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 1  # Only the StepStarted
        record = json.loads(lines[0])
        assert record["event"] == "StepStarted"
        assert journal.event_count == 1

    @pytest.mark.asyncio
    async def test_include_agent_text_default(self, tmp_path: Path) -> None:
        """Default include_agent_text=True keeps AgentStreamChunk events."""
        log_path = tmp_path / "session.jsonl"
        journal = SessionJournal(log_path)

        chunk = AgentStreamChunk(
            step_name="impl",
            agent_name="Agent",
            text="Hello",
            chunk_type="output",
            timestamp=1000.0,
        )
        await journal.record(chunk)
        journal.close()

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 1
        assert journal.event_count == 1

    def test_context_manager(self, tmp_path: Path) -> None:
        """Context manager closes the journal on exit."""
        log_path = tmp_path / "session.jsonl"
        with SessionJournal(log_path) as journal:
            journal.write_header("test", {})
            assert journal.is_open

        assert not journal.is_open

    def test_close_is_idempotent(self, tmp_path: Path) -> None:
        """Calling close() multiple times does not raise."""
        log_path = tmp_path / "session.jsonl"
        journal = SessionJournal(log_path)
        journal.close()
        journal.close()  # Should not raise
        assert not journal.is_open

    def test_write_after_close_is_noop(self, tmp_path: Path) -> None:
        """Writing to a closed journal is silently ignored."""
        log_path = tmp_path / "session.jsonl"
        journal = SessionJournal(log_path)
        journal.close()
        journal.write_header("test", {})
        # File should be empty (no data written after close)
        content = log_path.read_text()
        assert content == ""

    def test_path_property(self, tmp_path: Path) -> None:
        """path property returns the configured file path."""
        log_path = tmp_path / "session.jsonl"
        journal = SessionJournal(log_path)
        assert journal.path == log_path
        journal.close()

    @pytest.mark.asyncio
    async def test_event_count_increments(self, tmp_path: Path) -> None:
        """event_count tracks the number of recorded events."""
        log_path = tmp_path / "session.jsonl"
        journal = SessionJournal(log_path)

        assert journal.event_count == 0

        await journal.record(StepStarted("s1", StepType.PYTHON, 1.0))
        assert journal.event_count == 1

        await journal.record(
            StepCompleted("s1", StepType.PYTHON, True, 100, timestamp=1.0)
        )
        assert journal.event_count == 2

        journal.close()

    @pytest.mark.asyncio
    async def test_full_session_roundtrip(self, tmp_path: Path) -> None:
        """End-to-end test: header, events, summary, then read back."""
        log_path = tmp_path / "session.jsonl"

        with SessionJournal(log_path) as journal:
            journal.write_header("test-workflow", {"key": "value"})

            await journal.record(
                WorkflowStarted("test-workflow", {"key": "value"}, 1000.0)
            )
            await journal.record(StepStarted("step1", StepType.PYTHON, 1001.0))
            await journal.record(
                StepCompleted("step1", StepType.PYTHON, True, 500, timestamp=1002.0)
            )
            await journal.record(WorkflowCompleted("test-workflow", True, 2000, 1003.0))

            journal.write_summary(
                {
                    "success": True,
                    "total_duration_ms": 2000,
                }
            )

        # Read back and verify
        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 6  # header + 4 events + summary

        header = json.loads(lines[0])
        assert header["event"] == "session_start"

        wf_started = json.loads(lines[1])
        assert wf_started["event"] == "WorkflowStarted"

        step_started = json.loads(lines[2])
        assert step_started["event"] == "StepStarted"
        assert step_started["step_type"] == "python"

        step_completed = json.loads(lines[3])
        assert step_completed["event"] == "StepCompleted"
        assert step_completed["success"] is True

        wf_completed = json.loads(lines[4])
        assert wf_completed["event"] == "WorkflowCompleted"

        summary = json.loads(lines[5])
        assert summary["event"] == "session_end"
        assert summary["event_count"] == 4
        assert summary["success"] is True

    @pytest.mark.asyncio
    async def test_crash_safety_flush(self, tmp_path: Path) -> None:
        """Each record is flushed immediately so data survives crashes."""
        log_path = tmp_path / "session.jsonl"
        journal = SessionJournal(log_path)

        journal.write_header("wf", {})
        await journal.record(StepStarted("s1", StepType.PYTHON, 1.0))

        # Without closing, data should already be on disk
        content = log_path.read_text()
        lines = content.strip().splitlines()
        assert len(lines) == 2

        journal.close()
