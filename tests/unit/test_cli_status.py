"""Unit tests for CLI status command functionality.

Tests the `maverick status` command behavior, including:
- Successful status queries with mocked workflow handle
- JSON output format validation
- Human-readable output format
- Error handling for invalid workflow IDs

Note: These tests mock the Temporal client and workflow handle
to avoid requiring a running Temporal server.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from src.cli.maverick import cli


@pytest.fixture
def mock_workflow_info():
    """Create a mock WorkflowInfo object."""
    info = MagicMock()
    info.run_id = "test-run-123"
    info.status = MagicMock()
    info.status.name = "RUNNING"
    return info


@pytest.fixture
def mock_workflow_handle(mock_workflow_info):
    """Create a mock workflow handle with async methods."""
    handle = AsyncMock()
    handle.id = "maverick-run-1234567890"
    handle.describe = AsyncMock(return_value=mock_workflow_info)

    # Mock query responses
    handle.query = AsyncMock(side_effect=lambda query_name: {
        "get_progress": {
            "current_task": "001-test-feature",
            "current_phase": "setup",
            "last_activity": "task_execution",
        },
        "get_task_results": [
            {
                "task_id": "001-test-feature",
                "status": "running",
                "message": "Executing phase setup",
            }
        ],
    }.get(query_name, {}))

    return handle


def test_status_command_human_readable(mock_workflow_handle):
    """Test status command with human-readable output."""
    with patch("src.cli.maverick.Client") as mock_client:
        # Setup mock client
        client_instance = AsyncMock()
        client_instance.get_workflow_handle = MagicMock(return_value=mock_workflow_handle)
        mock_client.connect = AsyncMock(return_value=client_instance)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["status", "maverick-run-1234567890"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0

        # Verify output contains key information
        assert "Workflow Status:" in result.output
        assert "maverick-run-1234567890" in result.output
        assert "test-run-123" in result.output
        assert "running" in result.output
        assert "001-test-feature" in result.output
        assert "setup" in result.output
        assert "task_execution" in result.output


def test_status_command_json_output(mock_workflow_handle):
    """Test status command with JSON output format."""
    with patch("src.cli.maverick.Client") as mock_client:
        # Setup mock client
        client_instance = AsyncMock()
        client_instance.get_workflow_handle = MagicMock(return_value=mock_workflow_handle)
        mock_client.connect = AsyncMock(return_value=client_instance)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["status", "maverick-run-1234567890", "--json"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0

        # Parse JSON output
        output = json.loads(result.output)

        # Verify required fields per contracts/openapi.yaml
        assert "workflow_id" in output
        assert "run_id" in output
        assert "state" in output
        assert "current_task_id" in output
        assert "current_phase" in output
        assert "last_activity" in output
        assert "updated_at" in output
        assert "tasks" in output

        # Verify values
        assert output["workflow_id"] == "maverick-run-1234567890"
        assert output["run_id"] == "test-run-123"
        assert output["state"] == "running"
        assert output["current_task_id"] == "001-test-feature"
        assert output["current_phase"] == "setup"
        assert output["last_activity"] == "task_execution"

        # Verify tasks array structure
        assert isinstance(output["tasks"], list)
        assert len(output["tasks"]) == 1

        task = output["tasks"][0]
        assert "task_id" in task
        assert "status" in task
        assert "last_message" in task
        assert task["task_id"] == "001-test-feature"
        assert task["status"] == "running"



def test_status_command_completed_workflow():
    """Test status command for completed workflow."""
    # Create mock for completed workflow
    mock_info = MagicMock()
    mock_info.run_id = "test-run-456"
    mock_info.status = MagicMock()
    mock_info.status.name = "COMPLETED"

    mock_handle = AsyncMock()
    mock_handle.id = "maverick-run-completed"
    mock_handle.describe = AsyncMock(return_value=mock_info)
    mock_handle.query = AsyncMock(side_effect=lambda query_name: {
        "get_progress": None,
        "get_task_results": [
            {
                "task_id": "001-feature",
                "status": "success",
                "message": "Completed successfully",
            }
        ],
    }.get(query_name, {}))

    with patch("src.cli.maverick.Client") as mock_client:
        client_instance = AsyncMock()
        client_instance.get_workflow_handle = MagicMock(return_value=mock_handle)
        mock_client.connect = AsyncMock(return_value=client_instance)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["status", "maverick-run-completed", "--json"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert output["state"] == "completed"
        assert output["current_task_id"] is None
        assert output["current_phase"] is None
        assert len(output["tasks"]) == 1
        assert output["tasks"][0]["status"] == "success"



def test_status_command_failed_workflow():
    """Test status command for failed workflow."""
    # Create mock for failed workflow
    mock_info = MagicMock()
    mock_info.run_id = "test-run-789"
    mock_info.status = MagicMock()
    mock_info.status.name = "FAILED"

    mock_handle = AsyncMock()
    mock_handle.id = "maverick-run-failed"
    mock_handle.describe = AsyncMock(return_value=mock_info)
    mock_handle.query = AsyncMock(side_effect=lambda query_name: {
        "get_progress": {
            "current_task": "002-feature",
            "current_phase": "execution",
            "last_activity": "task_failed",
        },
        "get_task_results": [
            {
                "task_id": "002-feature",
                "status": "failed",
                "message": "Task execution failed",
            }
        ],
    }.get(query_name, {}))

    with patch("src.cli.maverick.Client") as mock_client:
        client_instance = AsyncMock()
        client_instance.get_workflow_handle = MagicMock(return_value=mock_handle)
        mock_client.connect = AsyncMock(return_value=client_instance)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["status", "maverick-run-failed", "--json"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert output["state"] == "failed"
        assert output["tasks"][0]["status"] == "failed"



def test_status_command_temporal_connection_error():
    """Test status command when Temporal server is unavailable."""
    with patch("src.cli.maverick.Client") as mock_client:
        # Simulate connection failure
        mock_client.connect = AsyncMock(side_effect=Exception("Connection refused"))

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["status", "maverick-run-1234567890"],
            catch_exceptions=False,
        )

        assert result.exit_code == 1
        assert "Error:" in result.output or "Failed to connect" in result.output



def test_status_command_temporal_connection_error_json():
    """Test status command JSON error output when Temporal is unavailable."""
    with patch("src.cli.maverick.Client") as mock_client:
        # Simulate connection failure
        mock_client.connect = AsyncMock(side_effect=Exception("Connection refused"))

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["status", "maverick-run-1234567890", "--json"],
            catch_exceptions=False,
        )

        assert result.exit_code == 1

        # Parse JSON error output
        output = json.loads(result.output)
        assert "error" in output
        assert "error_type" in output
        assert "workflow_id" in output
        assert output["workflow_id"] == "maverick-run-1234567890"



def test_status_command_query_progress_error(mock_workflow_info):
    """Test status command handles query errors gracefully."""
    # Create mock that fails on query
    mock_handle = AsyncMock()
    mock_handle.id = "maverick-run-query-error"
    mock_handle.describe = AsyncMock(return_value=mock_workflow_info)
    mock_handle.query = AsyncMock(side_effect=Exception("Query failed"))

    with patch("src.cli.maverick.Client") as mock_client:
        client_instance = AsyncMock()
        client_instance.get_workflow_handle = MagicMock(return_value=mock_handle)
        mock_client.connect = AsyncMock(return_value=client_instance)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["status", "maverick-run-query-error", "--json"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0  # Should still succeed with partial data

        output = json.loads(result.output)
        # Should have workflow info even if queries fail
        assert output["workflow_id"] == "maverick-run-query-error"
        assert output["state"] == "running"
        # Query-dependent fields should be None or empty
        assert output["current_task_id"] is None
        assert output["tasks"] == []



def test_status_command_multiple_tasks():
    """Test status command with multiple tasks in progress."""
    mock_info = MagicMock()
    mock_info.run_id = "test-run-multi"
    mock_info.status = MagicMock()
    mock_info.status.name = "RUNNING"

    mock_handle = AsyncMock()
    mock_handle.id = "maverick-run-multi"
    mock_handle.describe = AsyncMock(return_value=mock_info)
    mock_handle.query = AsyncMock(side_effect=lambda query_name: {
        "get_progress": {
            "current_task": "003-feature",
            "current_phase": "core",
            "last_activity": "implementing",
        },
        "get_task_results": [
            {
                "task_id": "001-feature",
                "status": "success",
                "message": "Completed",
            },
            {
                "task_id": "002-feature",
                "status": "success",
                "message": "Completed",
            },
            {
                "task_id": "003-feature",
                "status": "running",
                "message": "In progress",
            }
        ],
    }.get(query_name, []))

    with patch("src.cli.maverick.Client") as mock_client:
        client_instance = AsyncMock()
        client_instance.get_workflow_handle = MagicMock(return_value=mock_handle)
        mock_client.connect = AsyncMock(return_value=client_instance)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["status", "maverick-run-multi", "--json"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        assert len(output["tasks"]) == 3
        assert output["tasks"][0]["status"] == "success"
        assert output["tasks"][1]["status"] == "success"
        assert output["tasks"][2]["status"] == "running"



def test_status_command_invalid_task_status_filtered():
    """Test status command filters out invalid task statuses."""
    mock_info = MagicMock()
    mock_info.run_id = "test-run-invalid"
    mock_info.status = MagicMock()
    mock_info.status.name = "RUNNING"

    mock_handle = AsyncMock()
    mock_handle.id = "maverick-run-invalid"
    mock_handle.describe = AsyncMock(return_value=mock_info)
    mock_handle.query = AsyncMock(side_effect=lambda query_name: {
        "get_progress": None,
        "get_task_results": [
            {
                "task_id": "001-feature",
                "status": "success",
                "message": "Valid",
            },
            {
                "task_id": "002-feature",
                "status": "invalid_status",  # Invalid status
                "message": "Should be filtered",
            },
            {
                "task_id": "003-feature",
                "status": "running",
                "message": "Valid",
            }
        ],
    }.get(query_name, []))

    with patch("src.cli.maverick.Client") as mock_client:
        client_instance = AsyncMock()
        client_instance.get_workflow_handle = MagicMock(return_value=mock_handle)
        mock_client.connect = AsyncMock(return_value=client_instance)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["status", "maverick-run-invalid", "--json"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0

        output = json.loads(result.output)
        # Should only include valid statuses
        assert len(output["tasks"]) == 2
        assert all(t["status"] in ("success", "running", "pending", "failed", "skipped")
                   for t in output["tasks"])


# T039: Negative test for invalid workflow_id

def test_status_command_nonexistent_workflow():
    """Test status command with non-existent workflow ID returns error."""
    with patch("src.cli.maverick.Client") as mock_client:
        # Setup mock client
        client_instance = AsyncMock()

        # Mock workflow handle that fails on describe
        mock_handle = AsyncMock()
        mock_handle.describe = AsyncMock(
            side_effect=Exception("Workflow not found")
        )

        client_instance.get_workflow_handle = MagicMock(return_value=mock_handle)
        mock_client.connect = AsyncMock(return_value=client_instance)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["status", "nonexistent-workflow-id"],
            catch_exceptions=False,
        )

        # Should exit with non-zero code
        assert result.exit_code == 1

        # Should contain error message
        assert "Error:" in result.output or "failed" in result.output.lower()



def test_status_command_nonexistent_workflow_json():
    """Test status command with invalid workflow ID returns JSON error payload."""
    with patch("src.cli.maverick.Client") as mock_client:
        # Setup mock client
        client_instance = AsyncMock()

        # Mock workflow handle that fails on describe
        mock_handle = AsyncMock()
        mock_handle.describe = AsyncMock(
            side_effect=Exception("Workflow not found")
        )

        client_instance.get_workflow_handle = MagicMock(return_value=mock_handle)
        mock_client.connect = AsyncMock(return_value=client_instance)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["status", "nonexistent-workflow-id", "--json"],
            catch_exceptions=False,
        )

        # Should exit with non-zero code
        assert result.exit_code == 1

        # Should output valid JSON error payload
        output = json.loads(result.output)
        assert "error" in output
        assert "error_type" in output
        assert "workflow_id" in output
        assert output["workflow_id"] == "nonexistent-workflow-id"
        assert output["error_type"] == "ClickException"

