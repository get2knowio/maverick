"""Unit tests for CLI logging fields.

Verifies that JSON logs include correlation and metrics fields as per FR-013.
"""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import jsonschema
import pytest
import yaml

OPENAPI_SCHEMA_PATH = Path("specs/001-maverick-cli/contracts/openapi.yaml")
_COMPONENT_SCHEMAS: dict[str, Any] | None = None


def _build_schema(schema_name: str) -> dict[str, Any]:
    """Load a component schema from the OpenAPI document for validation."""
    global _COMPONENT_SCHEMAS

    if _COMPONENT_SCHEMAS is None:
        if not OPENAPI_SCHEMA_PATH.exists():
            raise AssertionError(f"Missing OpenAPI contract at {OPENAPI_SCHEMA_PATH}")
        with OPENAPI_SCHEMA_PATH.open(encoding="utf-8") as handle:
            document = yaml.safe_load(handle)
        components = document.get("components", {}).get("schemas", {})
        if not components:
            raise AssertionError("OpenAPI document missing components.schemas section")
        _COMPONENT_SCHEMAS = components

    if schema_name not in _COMPONENT_SCHEMAS:
        raise AssertionError(f"Schema {schema_name} not found in OpenAPI components")

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "components": {"schemas": _COMPONENT_SCHEMAS},
        "$ref": f"#/components/schemas/{schema_name}",
    }


@pytest.mark.asyncio
async def test_cli_run_includes_metrics_in_logs(tmp_path: Path, capsys):
    """Test that CLI run command includes metrics fields in logs."""
    from src.cli.maverick import _run_workflow

    # Mock repository setup
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()

    # Create a simple tasks.md file
    specs_dir = repo_root / "specs" / "001-test"
    specs_dir.mkdir(parents=True)
    tasks_file = specs_dir / "tasks.md"
    tasks_file.write_text("# Test Tasks\n\n## Phase 1\n- Task 1\n")

    # Mock dependencies
    with patch("src.cli.maverick.validate_repo_root"), \
         patch("src.cli.maverick.is_working_tree_dirty", return_value=False), \
         patch("src.cli.maverick.get_current_branch", return_value="main"), \
         patch("src.cli.maverick.discover_tasks") as mock_discover, \
         patch("src.cli.maverick.build_cli_descriptor") as mock_build_descriptor, \
         patch("src.cli.maverick.adapt_to_orchestration_input") as mock_adapt, \
         patch("src.cli.maverick.Client") as mock_client_class:

        # Setup mocks
        mock_discover.return_value = [
            MagicMock(file_path=str(tasks_file), spec_dir=str(specs_dir))
        ]

        mock_descriptor = MagicMock()
        mock_descriptor.task_id = "001-test-tasks"
        mock_build_descriptor.return_value = mock_descriptor

        mock_adapt.return_value = MagicMock()

        # Mock Temporal client and workflow handle
        mock_client = AsyncMock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        mock_handle = AsyncMock()
        mock_handle.id = "test-workflow-id"
        mock_handle.result_run_id = "test-run-id"
        mock_handle.describe = AsyncMock(return_value=MagicMock(
            status=MagicMock(name="COMPLETED")
        ))
        mock_handle.query = AsyncMock(return_value={})
        mock_client.start_workflow = AsyncMock(return_value=mock_handle)

        # Run the workflow
        await _run_workflow(
            task=None,
            interactive=False,
            dry_run=False,
            json_output=False,
            allow_dirty=False,
            compact=False,
        )

        captured = capsys.readouterr().out
        assert captured, "Expected CLI logs to be printed to stdout"

        # Check for metrics fields in logs
        assert "Discovered 1 task(s)" in captured or "discovery_ms" in captured, "Logs should include discovery timing"
        assert "test-workflow-id" in captured, "Logs should include workflow_id after start"
        assert "task_count=1" in captured or "Tasks: 1" in captured, "Logs should include task count"


@pytest.mark.asyncio
async def test_cli_status_includes_correlation_fields(tmp_path: Path):
    """Test that CLI status command includes correlation fields."""
    import sys
    from io import StringIO

    from src.cli.maverick import _get_workflow_status

    # Mock Temporal client
    with patch("src.cli.maverick.Client") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.connect = AsyncMock(return_value=mock_client)

        # Mock workflow handle
        mock_handle = AsyncMock()
        mock_workflow_info = MagicMock()
        mock_workflow_info.run_id = "test-run-id-123"
        mock_workflow_info.status = MagicMock(name="RUNNING")
        mock_handle.describe = AsyncMock(return_value=mock_workflow_info)
        mock_handle.query = AsyncMock(side_effect=[
            {"current_task": "task-1", "current_phase": "phase-1"},  # get_progress
            [{"task_id": "task-1", "status": "running"}],  # get_task_results
        ])

        mock_client.get_workflow_handle = MagicMock(return_value=mock_handle)

        # Capture JSON output
        captured_output = StringIO()
        original_stdout = sys.stdout

        try:
            sys.stdout = captured_output
            await _get_workflow_status("test-workflow-123", json_output=True)
        finally:
            sys.stdout = original_stdout

        # Parse JSON output
        output = captured_output.getvalue()
        assert output.strip(), "Expected JSON output from _get_workflow_status but got empty output"
        data = json.loads(output)

        # Verify correlation fields
        assert "workflow_id" in data, "JSON output should include workflow_id"
        assert "run_id" in data, "JSON output should include run_id"
        assert data["workflow_id"] == "test-workflow-123"
        assert data["run_id"] == "test-run-id-123"

        # Verify structure includes other expected fields
        assert "state" in data
        assert "tasks" in data
        assert "updated_at" in data


def test_json_output_schema_matches_contracts():
    """Test that JSON output structure matches contracts/openapi.yaml schema."""
    from src.cli._models import TaskProgressInfo, WorkflowStartResponse, WorkflowStatusInfo

    # Test WorkflowStartResponse structure
    start_response = WorkflowStartResponse(
        workflow_id="wf-123",
        run_id="run-abc",
        task_count=3,
        discovery_ms=42,
        workflow_start_ms=150,
    )

    start_payload = asdict(start_response)
    jsonschema.validate(instance=start_payload, schema=_build_schema("RunStartResponse"))
    assert isinstance(start_payload["task_count"], int), "task_count must serialize as integer"
    assert isinstance(start_payload["discovery_ms"], int)
    assert isinstance(start_payload["workflow_start_ms"], int)

    # Test WorkflowStatusInfo structure
    task_progress = TaskProgressInfo(
        task_id="task-1",
        status="running",
        last_message="Processing",
    )

    status_info = WorkflowStatusInfo(
        workflow_id="wf-123",
        run_id="run-abc",
        state="running",
        current_task_id="task-1",
        current_phase="phase-1",
        last_activity="activity-1",
        updated_at="2025-11-10T12:00:00Z",
        tasks=[task_progress],
    )

    status_payload = asdict(status_info)
    jsonschema.validate(instance=status_payload, schema=_build_schema("WorkflowStatus"))

    # Explicit type/format assertions to ensure JSON contract compliance
    assert status_payload["state"] in {"running", "completed", "failed", "paused"}
    assert isinstance(status_payload["errors_count"], int)
    assert isinstance(status_payload["tasks"], list)
    assert status_payload["tasks"], "Expected at least one task entry in serialized payload"
    datetime_value = datetime.fromisoformat(status_payload["updated_at"].replace("Z", "+00:00"))
    assert datetime_value.tzinfo is not None, "updated_at must include timezone information"

    task_entry = status_payload["tasks"][0]
    assert isinstance(task_entry["task_id"], str)
    assert task_entry["status"] in {"pending", "running", "success", "failed", "skipped"}
    assert isinstance(task_entry.get("last_message"), (str, type(None)))
