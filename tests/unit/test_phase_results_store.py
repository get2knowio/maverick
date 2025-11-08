"""Unit tests for phase result persistence utilities."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from src.models.phase_automation import PhaseResult
from src.utils.phase_results_store import (
    deserialize_phase_result,
    load_phase_result,
    save_phase_result,
    serialize_phase_result,
)


@pytest.fixture
def sample_phase_result() -> PhaseResult:
    """Create a sample PhaseResult for testing."""
    started = datetime(2025, 11, 8, 10, 0, 0, tzinfo=UTC)
    finished = datetime(2025, 11, 8, 10, 5, 30, tzinfo=UTC)
    duration_ms = int((finished - started).total_seconds() * 1000)

    return PhaseResult(
        phase_id="phase-1",
        status="success",
        completed_task_ids=["T001", "T002", "T003"],
        started_at=started,
        finished_at=finished,
        duration_ms=duration_ms,
        tasks_md_hash="abc123def456",
        stdout_path="/tmp/logs/phase-1-stdout.log",
        stderr_path="/tmp/logs/phase-1-stderr.log",
        artifact_paths=["/tmp/artifacts/result.json"],
        summary=["Task T001 completed", "Task T002 completed", "All tasks successful"],
        error=None,
    )


@pytest.fixture
def failed_phase_result() -> PhaseResult:
    """Create a failed PhaseResult for testing."""
    started = datetime(2025, 11, 8, 11, 0, 0, tzinfo=UTC)
    finished = datetime(2025, 11, 8, 11, 2, 15, tzinfo=UTC)
    duration_ms = int((finished - started).total_seconds() * 1000)

    return PhaseResult(
        phase_id="phase-2",
        status="failed",
        completed_task_ids=["T004"],
        started_at=started,
        finished_at=finished,
        duration_ms=duration_ms,
        tasks_md_hash="xyz789ghi012",
        stdout_path="/tmp/logs/phase-2-stdout.log",
        stderr_path="/tmp/logs/phase-2-stderr.log",
        artifact_paths=[],
        summary=["Task T004 completed", "Task T005 failed with error"],
        error="Activity execution timeout after 30 minutes",
    )


class TestSerializePhaseResult:
    """Test serialization of PhaseResult to JSON-compatible dict."""

    def test_serialize_successful_result(self, sample_phase_result: PhaseResult) -> None:
        """Should serialize a successful phase result to dict with ISO timestamps."""
        result = serialize_phase_result(sample_phase_result)

        assert result["phase_id"] == "phase-1"
        assert result["status"] == "success"
        assert result["completed_task_ids"] == ["T001", "T002", "T003"]
        assert result["started_at"] == "2025-11-08T10:00:00+00:00"
        assert result["finished_at"] == "2025-11-08T10:05:30+00:00"
        assert result["duration_ms"] == 330000
        assert result["tasks_md_hash"] == "abc123def456"
        assert result["stdout_path"] == "/tmp/logs/phase-1-stdout.log"
        assert result["stderr_path"] == "/tmp/logs/phase-1-stderr.log"
        assert result["artifact_paths"] == ["/tmp/artifacts/result.json"]
        assert len(result["summary"]) == 3
        assert result["error"] is None

    def test_serialize_failed_result(self, failed_phase_result: PhaseResult) -> None:
        """Should serialize a failed phase result with error field populated."""
        result = serialize_phase_result(failed_phase_result)

        assert result["phase_id"] == "phase-2"
        assert result["status"] == "failed"
        assert result["error"] == "Activity execution timeout after 30 minutes"
        assert result["completed_task_ids"] == ["T004"]

    def test_serialize_with_none_paths(self) -> None:
        """Should handle None stdout/stderr paths gracefully."""
        started = datetime(2025, 11, 8, 12, 0, 0, tzinfo=UTC)
        finished = datetime(2025, 11, 8, 12, 1, 0, tzinfo=UTC)
        duration_ms = int((finished - started).total_seconds() * 1000)

        result = PhaseResult(
            phase_id="phase-3",
            status="skipped",
            completed_task_ids=[],
            started_at=started,
            finished_at=finished,
            duration_ms=duration_ms,
            tasks_md_hash="skip123",
            stdout_path=None,
            stderr_path=None,
            artifact_paths=[],
            summary=["Phase skipped due to checkpoint"],
            error=None,
        )

        serialized = serialize_phase_result(result)
        assert serialized["stdout_path"] is None
        assert serialized["stderr_path"] is None


class TestDeserializePhaseResult:
    """Test deserialization of dict back to PhaseResult."""

    def test_deserialize_successful_result(self, sample_phase_result: PhaseResult) -> None:
        """Should reconstruct PhaseResult from serialized dict."""
        serialized = serialize_phase_result(sample_phase_result)
        deserialized = deserialize_phase_result(serialized)

        assert deserialized.phase_id == sample_phase_result.phase_id
        assert deserialized.status == sample_phase_result.status
        assert deserialized.completed_task_ids == sample_phase_result.completed_task_ids
        assert deserialized.started_at == sample_phase_result.started_at
        assert deserialized.finished_at == sample_phase_result.finished_at
        assert deserialized.duration_ms == sample_phase_result.duration_ms
        assert deserialized.tasks_md_hash == sample_phase_result.tasks_md_hash
        assert deserialized.stdout_path == sample_phase_result.stdout_path
        assert deserialized.stderr_path == sample_phase_result.stderr_path
        assert deserialized.artifact_paths == sample_phase_result.artifact_paths
        assert deserialized.summary == sample_phase_result.summary
        assert deserialized.error == sample_phase_result.error

    def test_deserialize_failed_result(self, failed_phase_result: PhaseResult) -> None:
        """Should reconstruct failed PhaseResult with error preserved."""
        serialized = serialize_phase_result(failed_phase_result)
        deserialized = deserialize_phase_result(serialized)

        assert deserialized.status == "failed"
        assert deserialized.error == failed_phase_result.error

    def test_deserialize_invalid_timestamp_format(self) -> None:
        """Should raise ValueError for invalid ISO timestamp format."""
        invalid_data = {
            "phase_id": "phase-1",
            "status": "success",
            "completed_task_ids": [],
            "started_at": "not-a-timestamp",
            "finished_at": "2025-11-08T10:00:00+00:00",
            "duration_ms": 0,
            "tasks_md_hash": "hash",
            "stdout_path": None,
            "stderr_path": None,
            "artifact_paths": [],
            "summary": [],
            "error": None,
        }

        with pytest.raises(ValueError, match="Invalid timestamp format"):
            deserialize_phase_result(invalid_data)

    def test_deserialize_missing_required_field(self) -> None:
        """Should raise ValueError for missing required fields."""
        incomplete_data: dict[str, Any] = {
            "phase_id": "phase-1",
            "status": "success",
            # Missing many required fields
        }

        with pytest.raises((ValueError, KeyError)):
            deserialize_phase_result(incomplete_data)


class TestSavePhaseResult:
    """Test persisting PhaseResult to JSON file."""

    def test_save_creates_parent_directories(self, tmp_path: Path, sample_phase_result: PhaseResult) -> None:
        """Should create parent directories if they don't exist."""
        output_dir = tmp_path / "results" / "workflow-123" / "nested"
        output_file = output_dir / "phase-1.json"

        save_phase_result(sample_phase_result, output_file)

        assert output_file.exists()
        assert output_file.is_file()

    def test_save_writes_valid_json(self, tmp_path: Path, sample_phase_result: PhaseResult) -> None:
        """Should write valid JSON that can be loaded back."""
        output_file = tmp_path / "phase-1.json"

        save_phase_result(sample_phase_result, output_file)

        import json

        with output_file.open("r") as f:
            data = json.load(f)

        assert data["phase_id"] == "phase-1"
        assert data["status"] == "success"
        assert data["tasks_md_hash"] == "abc123def456"

    def test_save_sanitizes_log_paths(self, tmp_path: Path, sample_phase_result: PhaseResult) -> None:
        """Should preserve absolute log paths as strings."""
        output_file = tmp_path / "phase-1.json"

        save_phase_result(sample_phase_result, output_file)

        import json

        with output_file.open("r") as f:
            data = json.load(f)

        assert isinstance(data["stdout_path"], str)
        assert data["stdout_path"] == "/tmp/logs/phase-1-stdout.log"
        assert isinstance(data["stderr_path"], str)
        assert data["stderr_path"] == "/tmp/logs/phase-1-stderr.log"

    def test_save_overwrites_existing_file(
        self, tmp_path: Path, sample_phase_result: PhaseResult, failed_phase_result: PhaseResult
    ) -> None:
        """Should overwrite existing file without error."""
        output_file = tmp_path / "phase-1.json"

        save_phase_result(sample_phase_result, output_file)

        save_phase_result(failed_phase_result, output_file)

        # File should be rewritten (likely different size)
        assert output_file.exists()
        # Verify content matches second save
        loaded = load_phase_result(output_file)
        assert loaded.phase_id == "phase-2"


class TestLoadPhaseResult:
    """Test loading PhaseResult from JSON file."""

    def test_load_existing_file(self, tmp_path: Path, sample_phase_result: PhaseResult) -> None:
        """Should load PhaseResult from previously saved file."""
        output_file = tmp_path / "phase-1.json"
        save_phase_result(sample_phase_result, output_file)

        loaded = load_phase_result(output_file)

        assert loaded.phase_id == sample_phase_result.phase_id
        assert loaded.status == sample_phase_result.status
        assert loaded.completed_task_ids == sample_phase_result.completed_task_ids
        assert loaded.duration_ms == sample_phase_result.duration_ms

    def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError for missing file."""
        nonexistent = tmp_path / "does-not-exist.json"

        with pytest.raises(FileNotFoundError):
            load_phase_result(nonexistent)

    def test_load_corrupted_json(self, tmp_path: Path) -> None:
        """Should raise ValueError for invalid JSON content."""
        corrupted_file = tmp_path / "corrupted.json"
        corrupted_file.write_text("{ not valid json ")

        with pytest.raises(ValueError, match="Failed to parse JSON"):
            load_phase_result(corrupted_file)

    def test_load_round_trip_preserves_data(self, tmp_path: Path, failed_phase_result: PhaseResult) -> None:
        """Should preserve all data through save/load cycle."""
        output_file = tmp_path / "phase-2.json"

        save_phase_result(failed_phase_result, output_file)
        loaded = load_phase_result(output_file)

        assert loaded.phase_id == failed_phase_result.phase_id
        assert loaded.status == failed_phase_result.status
        assert loaded.error == failed_phase_result.error
        assert loaded.completed_task_ids == failed_phase_result.completed_task_ids
        assert loaded.stdout_path == failed_phase_result.stdout_path
        assert loaded.stderr_path == failed_phase_result.stderr_path
        assert loaded.artifact_paths == failed_phase_result.artifact_paths
        assert loaded.summary == failed_phase_result.summary
        assert loaded.started_at == failed_phase_result.started_at
        assert loaded.finished_at == failed_phase_result.finished_at
        assert loaded.duration_ms == failed_phase_result.duration_ms
        assert loaded.tasks_md_hash == failed_phase_result.tasks_md_hash
