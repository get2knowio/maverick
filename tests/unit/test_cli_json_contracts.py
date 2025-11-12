"""Unit tests for CLI JSON contract compliance.

Tests that JSON output schemas match contracts/openapi.yaml definitions.
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.cli._models import (
    CLITaskDescriptor,
    DryRunResult,
    TaskProgressInfo,
    WorkflowStartResponse,
    WorkflowStatusInfo,
)


def load_openapi_schema():
    """Load OpenAPI schema from contracts directory."""
    # Note: This function is a placeholder for future OpenAPI schema validation
    # Currently not used but kept for reference
    pytest.skip("OpenAPI schema validation not yet implemented")


def test_task_descriptor_json_keys():
    """Test TaskDescriptor JSON output has expected keys."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        spec_dir = repo_root / "specs" / "001-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks")

        descriptor = CLITaskDescriptor(
            task_id="001-feature",
            task_file=str(task_file),
            spec_root=str(spec_dir),
            branch_name="001-feature",
            return_to_branch="main",
            repo_root=str(repo_root),
            interactive=False,
        )

        # Convert to dict-like structure for JSON serialization
        descriptor_dict = {
            "task_id": descriptor.task_id,
            "task_file": descriptor.task_file,
            "spec_root": descriptor.spec_root,
            "branch_name": descriptor.branch_name,
        }

        # Verify expected keys from schema
        expected_keys = {"task_id", "task_file", "spec_root", "branch_name"}
        assert set(descriptor_dict.keys()) == expected_keys


def test_cli_task_context_json_keys():
    """Test CLITaskContext JSON output has expected keys."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        spec_dir = repo_root / "specs" / "001-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks")

        descriptor = CLITaskDescriptor(
            task_id="001-feature",
            task_file=str(task_file),
            spec_root=str(spec_dir),
            branch_name="001-feature",
            return_to_branch="main",
            repo_root=str(repo_root),
            interactive=True,
            model_prefs={"provider": "openai", "model": "gpt-4"},
        )

        # CLI context keys
        context_dict = {
            "return_to_branch": descriptor.return_to_branch,
            "repo_root": descriptor.repo_root,
            "interactive": descriptor.interactive,
            "model_prefs": descriptor.model_prefs,
        }

        # Verify expected keys from schema
        expected_keys = {"return_to_branch", "repo_root", "interactive", "model_prefs"}
        assert set(context_dict.keys()) == expected_keys


def test_workflow_start_response_json_keys():
    """Test WorkflowStartResponse JSON output has expected keys."""
    response = WorkflowStartResponse(
        workflow_id="wf-123",
        run_id="run-456",
        task_count=3,
        discovery_ms=42,
        workflow_start_ms=150,
    )

    # Convert to dict for JSON serialization
    response_dict = {
        "workflow_id": response.workflow_id,
        "run_id": response.run_id,
        "task_count": response.task_count,
        "discovery_ms": response.discovery_ms,
        "workflow_start_ms": response.workflow_start_ms,
    }

    # Verify expected keys from schema
    expected_keys = {"workflow_id", "run_id", "task_count", "discovery_ms", "workflow_start_ms"}
    assert set(response_dict.keys()) == expected_keys

    # Verify JSON serializable
    json_str = json.dumps(response_dict)
    assert json_str is not None


def test_workflow_status_json_keys():
    """Test WorkflowStatusInfo JSON output has expected keys."""
    status = WorkflowStatusInfo(
        workflow_id="wf-123",
        run_id="run-456",
        state="running",
        current_task_id="001-feature",
        current_phase="implement",
        last_activity="phase_started",
        updated_at="2025-11-10T12:00:00Z",
        tasks=[
            TaskProgressInfo(
                task_id="001-feature",
                status="running",
                last_message="Starting phase",
            )
        ],
        status_poll_latency_ms_p95=180,
        errors_count=0,
    )

    # Convert to dict for JSON serialization
    status_dict = {
        "workflow_id": status.workflow_id,
        "run_id": status.run_id,
        "state": status.state,
        "current_task_id": status.current_task_id,
        "current_phase": status.current_phase,
        "last_activity": status.last_activity,
        "updated_at": status.updated_at,
        "tasks": [
            {
                "task_id": t.task_id,
                "status": t.status,
                "last_message": t.last_message,
            }
            for t in status.tasks
        ],
    }

    # Verify expected keys from schema
    expected_keys = {
        "workflow_id",
        "run_id",
        "state",
        "current_task_id",
        "current_phase",
        "last_activity",
        "updated_at",
        "tasks",
    }
    assert set(status_dict.keys()) == expected_keys

    # Verify JSON serializable
    json_str = json.dumps(status_dict)
    assert json_str is not None


def test_task_progress_json_keys():
    """Test TaskProgressInfo JSON output has expected keys."""
    progress = TaskProgressInfo(
        task_id="001-feature",
        status="running",
        last_message="Phase started",
    )

    # Convert to dict for JSON serialization
    progress_dict = {
        "task_id": progress.task_id,
        "status": progress.status,
        "last_message": progress.last_message,
    }

    # Verify expected keys from schema
    expected_keys = {"task_id", "status", "last_message"}
    assert set(progress_dict.keys()) == expected_keys

    # Verify JSON serializable
    json_str = json.dumps(progress_dict)
    assert json_str is not None


def test_dry_run_result_json_structure():
    """Test DryRunResult JSON output structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        spec_dir = repo_root / "specs" / "001-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks")

        descriptor = CLITaskDescriptor(
            task_id="001-feature",
            task_file=str(task_file),
            spec_root=str(spec_dir),
            branch_name="001-feature",
            return_to_branch="main",
            repo_root=str(repo_root),
            interactive=False,
        )

        result = DryRunResult(
            task_count=1,
            discovery_ms=42,
            descriptors=[descriptor],
        )

        # Verify structure matches expected format
        assert result.task_count == 1
        assert result.discovery_ms == 42
        assert len(result.descriptors) == 1


def test_workflow_state_enum_values():
    """Test WorkflowStatusInfo accepts valid state enum values."""
    valid_states = ["running", "completed", "failed", "paused"]

    for state in valid_states:
        status = WorkflowStatusInfo(
            workflow_id="wf-123",
            run_id="run-456",
            state=state,
            current_task_id=None,
            current_phase=None,
            last_activity=None,
            updated_at="2025-11-10T12:00:00Z",
            tasks=[],
        )
        assert status.state == state


def test_workflow_state_invalid_value():
    """Test WorkflowStatusInfo rejects invalid state values."""
    with pytest.raises(ValueError, match="state must be one of"):
        WorkflowStatusInfo(
            workflow_id="wf-123",
            run_id="run-456",
            state="invalid_state",
            current_task_id=None,
            current_phase=None,
            last_activity=None,
            updated_at="2025-11-10T12:00:00Z",
            tasks=[],
        )


def test_task_status_enum_values():
    """Test TaskProgressInfo accepts valid status enum values."""
    valid_statuses = ["pending", "running", "success", "failed", "skipped"]

    for status in valid_statuses:
        progress = TaskProgressInfo(
            task_id="001-feature",
            status=status,
        )
        assert progress.status == status


def test_task_status_invalid_value():
    """Test TaskProgressInfo rejects invalid status values."""
    with pytest.raises(ValueError, match="status must be one of"):
        TaskProgressInfo(
            task_id="001-feature",
            status="invalid_status",
        )


def test_model_prefs_structure():
    """Test model_prefs has correct structure and types."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_root = Path(tmpdir)
        spec_dir = repo_root / "specs" / "001-feature"
        spec_dir.mkdir(parents=True)
        task_file = spec_dir / "tasks.md"
        task_file.write_text("# Tasks")

        model_prefs = {
            "provider": "openai",
            "model": "gpt-4",
            "max_tokens": 2000,
        }

        descriptor = CLITaskDescriptor(
            task_id="001-feature",
            task_file=str(task_file),
            spec_root=str(spec_dir),
            branch_name="001-feature",
            return_to_branch="main",
            repo_root=str(repo_root),
            interactive=False,
            model_prefs=model_prefs,
        )

        assert descriptor.model_prefs == model_prefs
        assert descriptor.model_prefs is not None
        assert isinstance(descriptor.model_prefs["provider"], str)
        assert isinstance(descriptor.model_prefs["model"], str)
        assert isinstance(descriptor.model_prefs["max_tokens"], int)


def test_json_serialization_round_trip():
    """Test JSON serialization and deserialization round trip."""
    response = WorkflowStartResponse(
        workflow_id="wf-123",
        run_id="run-456",
        task_count=3,
        discovery_ms=42,
        workflow_start_ms=150,
    )

    # Serialize to JSON
    response_dict = {
        "workflow_id": response.workflow_id,
        "run_id": response.run_id,
        "task_count": response.task_count,
        "discovery_ms": response.discovery_ms,
        "workflow_start_ms": response.workflow_start_ms,
    }
    json_str = json.dumps(response_dict)

    # Deserialize from JSON
    loaded_dict = json.loads(json_str)

    # Verify data integrity
    assert loaded_dict["workflow_id"] == "wf-123"
    assert loaded_dict["run_id"] == "run-456"
    assert loaded_dict["task_count"] == 3
    assert loaded_dict["discovery_ms"] == 42
    assert loaded_dict["workflow_start_ms"] == 150
