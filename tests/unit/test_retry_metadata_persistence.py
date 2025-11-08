"""Unit tests for retry metadata persistence and surfacing."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.models.review_fix import RetryMetadata, ReviewLoopOutcome
from src.utils.phase_results_store import (
    deserialize_retry_metadata,
    load_retry_metadata,
    save_retry_metadata,
    serialize_retry_metadata,
)


def test_serialize_retry_metadata():
    """Test serialization of RetryMetadata to dictionary."""
    metadata = RetryMetadata(
        previous_fingerprint="a" * 64,
        attempt_counter=2,
        last_status="failed",
        artifacts_path="/tmp/artifacts/abc123",
    )

    serialized = serialize_retry_metadata(metadata)

    assert serialized["previous_fingerprint"] == "a" * 64
    assert serialized["attempt_counter"] == 2
    assert serialized["last_status"] == "failed"
    assert serialized["artifacts_path"] == "/tmp/artifacts/abc123"


def test_serialize_retry_metadata_no_artifacts():
    """Test serialization with no artifacts path."""
    metadata = RetryMetadata(
        previous_fingerprint="b" * 64,
        attempt_counter=1,
        last_status="clean",
    )

    serialized = serialize_retry_metadata(metadata)

    assert serialized["previous_fingerprint"] == "b" * 64
    assert serialized["attempt_counter"] == 1
    assert serialized["last_status"] == "clean"
    assert serialized["artifacts_path"] is None


def test_deserialize_retry_metadata():
    """Test deserialization of RetryMetadata from dictionary."""
    data = {
        "previous_fingerprint": "c" * 64,
        "attempt_counter": 3,
        "last_status": "fixed",
        "artifacts_path": "/tmp/artifacts/def456",
    }

    metadata = deserialize_retry_metadata(data)

    assert metadata.previous_fingerprint == "c" * 64
    assert metadata.attempt_counter == 3
    assert metadata.last_status == "fixed"
    assert metadata.artifacts_path == "/tmp/artifacts/def456"


def test_deserialize_retry_metadata_no_artifacts():
    """Test deserialization without artifacts path."""
    data = {
        "previous_fingerprint": "d" * 64,
        "attempt_counter": 1,
        "last_status": "clean",
    }

    metadata = deserialize_retry_metadata(data)

    assert metadata.previous_fingerprint == "d" * 64
    assert metadata.attempt_counter == 1
    assert metadata.last_status == "clean"
    assert metadata.artifacts_path is None


def test_save_and_load_retry_metadata(tmp_path: Path):
    """Test round-trip persistence of RetryMetadata."""
    metadata = RetryMetadata(
        previous_fingerprint="e" * 64,
        attempt_counter=5,
        last_status="failed",
        artifacts_path="/tmp/artifacts/ghi789",
    )

    output_file = tmp_path / "retry_metadata.json"
    save_retry_metadata(metadata, output_file)

    assert output_file.exists()

    loaded_metadata = load_retry_metadata(output_file)

    assert loaded_metadata.previous_fingerprint == metadata.previous_fingerprint
    assert loaded_metadata.attempt_counter == metadata.attempt_counter
    assert loaded_metadata.last_status == metadata.last_status
    assert loaded_metadata.artifacts_path == metadata.artifacts_path


def test_load_retry_metadata_file_not_found():
    """Test loading retry metadata from non-existent file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="Retry metadata file not found"):
        load_retry_metadata(Path("/nonexistent/retry_metadata.json"))


def test_load_retry_metadata_invalid_json(tmp_path: Path):
    """Test loading retry metadata from invalid JSON raises ValueError."""
    invalid_file = tmp_path / "invalid.json"
    with invalid_file.open("w") as f:
        f.write("{ invalid json }")

    with pytest.raises(ValueError, match="Failed to parse JSON"):
        load_retry_metadata(invalid_file)


def test_retry_metadata_from_outcome():
    """Test creating RetryMetadata from ReviewLoopOutcome."""
    outcome = ReviewLoopOutcome(
        status="clean",
        fingerprint="f" * 64,
        completed_at=datetime.now(UTC),
        issues_fixed=0,
        artifacts_path="/tmp/artifacts/clean",
    )

    metadata = RetryMetadata.from_outcome(outcome)

    assert metadata.previous_fingerprint == outcome.fingerprint
    assert metadata.attempt_counter == 1
    assert metadata.last_status == outcome.status
    assert metadata.artifacts_path == outcome.artifacts_path


def test_retry_metadata_from_outcome_custom_counter():
    """Test creating RetryMetadata with custom attempt counter."""
    outcome = ReviewLoopOutcome(
        status="clean",
        fingerprint="1" * 64,
        completed_at=datetime.now(UTC),
        issues_fixed=0,
        artifacts_path="/tmp/artifacts/clean",
    )

    metadata = RetryMetadata.from_outcome(outcome, attempt_counter=5)

    assert metadata.previous_fingerprint == outcome.fingerprint
    assert metadata.attempt_counter == 5
    assert metadata.last_status == outcome.status
    assert metadata.artifacts_path == outcome.artifacts_path


def test_retry_metadata_from_outcome_no_artifacts():
    """Test creating RetryMetadata from outcome without artifacts path."""
    outcome = ReviewLoopOutcome(
        status="failed",
        fingerprint="2" * 64,
        completed_at=datetime.now(UTC),
        issues_fixed=0,
        artifacts_path="",
    )

    metadata = RetryMetadata.from_outcome(outcome)

    assert metadata.previous_fingerprint == outcome.fingerprint
    assert metadata.attempt_counter == 1
    assert metadata.last_status == outcome.status
    assert metadata.artifacts_path is None


def test_retry_metadata_round_trip_with_outcome(tmp_path: Path):
    """Test full workflow: outcome -> metadata -> save -> load -> validate."""
    # Create outcome
    outcome = ReviewLoopOutcome(
        status="failed",
        fingerprint="3" * 64,
        completed_at=datetime.now(UTC),
        issues_fixed=0,
        artifacts_path="/tmp/artifacts/test",
    )

    # Create metadata from outcome
    metadata = RetryMetadata.from_outcome(outcome, attempt_counter=3)

    # Save metadata
    output_file = tmp_path / "retry_test.json"
    save_retry_metadata(metadata, output_file)

    # Load metadata
    loaded_metadata = load_retry_metadata(output_file)

    # Validate
    assert loaded_metadata.previous_fingerprint == outcome.fingerprint
    assert loaded_metadata.attempt_counter == 3
    assert loaded_metadata.last_status == outcome.status
    assert loaded_metadata.artifacts_path == outcome.artifacts_path
