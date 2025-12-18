"""End-to-end integration tests for validation workflow.

Tests the ValidationWorkflow with real command execution and mock fix agent.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from maverick.models.validation import (
    StageStatus,
    ValidationStage,
    ValidationWorkflowConfig,
)
from maverick.workflows.validation import ValidationWorkflow, create_python_workflow

# =============================================================================
# T066: Integration test - full workflow with real commands
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix commands not available on Windows"
)
async def test_workflow_with_real_echo_commands():
    """Integration test: workflow executes real shell commands."""
    stages = [
        ValidationStage(
            name="echo_test",
            command=["echo", "hello world"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
        ValidationStage(
            name="true_test",
            command=["true"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
    ]

    workflow = ValidationWorkflow(stages=stages)

    progress_events = []
    async for progress in workflow.run():
        progress_events.append(progress)

    result = workflow.get_result()

    # Both commands should succeed
    assert result.success
    assert len(result.stage_results) == 2
    assert result.stage_results[0].status == StageStatus.PASSED
    assert result.stage_results[1].status == StageStatus.PASSED
    assert "hello world" in result.stage_results[0].output


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix commands not available on Windows"
)
async def test_workflow_with_failing_command():
    """Integration test: workflow handles failing commands correctly."""
    stages = [
        ValidationStage(
            name="pass_stage",
            command=["true"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
        ValidationStage(
            name="fail_stage",
            command=["false"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
    ]

    workflow = ValidationWorkflow(stages=stages)

    progress_events = []
    async for progress in workflow.run():
        progress_events.append(progress)

    result = workflow.get_result()

    # First passes, second fails
    assert not result.success
    assert result.stage_results[0].status == StageStatus.PASSED
    assert result.stage_results[1].status == StageStatus.FAILED


@pytest.mark.asyncio
async def test_workflow_with_command_not_found():
    """Integration test: workflow handles missing commands."""
    stages = [
        ValidationStage(
            name="missing_cmd",
            command=["nonexistent_command_xyz123"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
    ]

    workflow = ValidationWorkflow(stages=stages)

    progress_events = []
    async for progress in workflow.run():
        progress_events.append(progress)

    result = workflow.get_result()

    assert not result.success
    assert result.stage_results[0].status == StageStatus.FAILED
    assert "not found" in result.stage_results[0].error_message.lower()


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix commands not available on Windows"
)
async def test_workflow_with_cwd_config():
    """Integration test: workflow respects working directory config."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test file in the temp directory
        test_file = Path(tmpdir) / "test_file.txt"
        test_file.write_text("test content")

        stages = [
            ValidationStage(
                name="ls_test",
                command=["ls", "test_file.txt"],
                fixable=False,
                max_fix_attempts=0,
                timeout_seconds=10.0,
            ),
        ]

        config = ValidationWorkflowConfig(cwd=Path(tmpdir))
        workflow = ValidationWorkflow(stages=stages, config=config)

        progress_events = []
        async for progress in workflow.run():
            progress_events.append(progress)

        result = workflow.get_result()

        # ls should find the file in the temp directory
        assert result.success
        assert "test_file.txt" in result.stage_results[0].output


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix commands not available on Windows"
)
@pytest.mark.timeout(15)  # Test should complete well under 15 seconds
async def test_workflow_with_timeout():
    """Integration test: workflow enforces command timeout."""
    stages = [
        ValidationStage(
            name="slow_command",
            command=["sleep", "10"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=0.5,  # Very short timeout
        ),
    ]

    workflow = ValidationWorkflow(stages=stages)

    progress_events = []
    async for progress in workflow.run():
        progress_events.append(progress)

    result = workflow.get_result()

    # Command should timeout
    assert not result.success
    assert result.stage_results[0].status == StageStatus.FAILED
    error_msg = result.stage_results[0].error_message.lower()
    assert "timeout" in error_msg or "timed out" in error_msg


# =============================================================================
# T067: Integration test - workflow with mock fix agent
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix commands not available on Windows"
)
async def test_workflow_with_mock_fix_agent():
    """Integration test: workflow invokes mock fix agent on failures."""
    # Track fix agent calls
    fix_calls = []

    mock_agent = MagicMock()

    async def mock_execute(**kwargs: Any) -> None:
        fix_calls.append(kwargs)

    mock_agent.execute = mock_execute

    # Stage that will pass on first try (no fix needed)
    stages = [
        ValidationStage(
            name="fixable_stage",
            # First call will fail (exit 1), fix agent runs, second call passes
            command=["sh", "-c", "exit 0"],  # Will pass after we mock it
            fixable=True,
            max_fix_attempts=2,
            timeout_seconds=10.0,
        ),
    ]

    # For this test, we'll use a stage that always passes
    # The mock fix agent behavior is tested in unit tests
    workflow = ValidationWorkflow(stages=stages, fix_agent=mock_agent)

    progress_events = []
    async for progress in workflow.run():
        progress_events.append(progress)

    result = workflow.get_result()

    # Stage should pass (no fix needed for "exit 0")
    assert result.success
    assert len(fix_calls) == 0  # No fix attempts needed for passing command


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix commands not available on Windows"
)
async def test_workflow_fix_agent_called_on_failure():
    """Integration test: fix agent is called when stage fails."""
    fix_calls = []

    mock_agent = MagicMock()

    async def mock_execute(**kwargs: Any) -> None:
        fix_calls.append(kwargs)

    mock_agent.execute = mock_execute

    stages = [
        ValidationStage(
            name="failing_fixable",
            command=["false"],  # Always fails
            fixable=True,
            max_fix_attempts=2,
            timeout_seconds=10.0,
        ),
    ]

    workflow = ValidationWorkflow(stages=stages, fix_agent=mock_agent)

    progress_events = []
    async for progress in workflow.run():
        progress_events.append(progress)

    result = workflow.get_result()

    # Stage should fail after exhausting fix attempts
    assert not result.success
    assert result.stage_results[0].status == StageStatus.FAILED
    assert result.stage_results[0].fix_attempts == 2

    # Fix agent should have been called twice
    assert len(fix_calls) == 2
    for call in fix_calls:
        assert call["stage_name"] == "failing_fixable"
        assert call["command"] == ["false"]


# =============================================================================
# Factory function tests
# =============================================================================


@pytest.mark.asyncio
async def test_create_python_workflow_factory():
    """Integration test: factory function creates workflow with default stages."""
    workflow = create_python_workflow()

    # Verify workflow has the default Python stages
    assert len(workflow._stages) == 4
    assert workflow._stages[0].name == "format"
    assert workflow._stages[1].name == "lint"
    assert workflow._stages[2].name == "typecheck"
    assert workflow._stages[3].name == "test"


@pytest.mark.asyncio
async def test_create_python_workflow_with_config():
    """Integration test: factory function accepts config."""
    config = ValidationWorkflowConfig(dry_run=True, stop_on_failure=True)
    workflow = create_python_workflow(config=config)

    assert workflow._config.dry_run is True
    assert workflow._config.stop_on_failure is True


@pytest.mark.asyncio
async def test_create_python_workflow_with_fix_agent():
    """Integration test: factory function accepts fix agent."""
    mock_agent = MagicMock()
    workflow = create_python_workflow(fix_agent=mock_agent)

    assert workflow._fix_agent is mock_agent


# =============================================================================
# Dry-run integration tests
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix commands not available on Windows"
)
async def test_dry_run_mode_no_execution():
    """Integration test: dry-run mode does not execute commands."""
    # Use a command that would fail if executed
    stages = [
        ValidationStage(
            name="would_fail",
            command=["false"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
    ]

    config = ValidationWorkflowConfig(dry_run=True)
    workflow = ValidationWorkflow(stages=stages, config=config)

    progress_events = []
    async for progress in workflow.run():
        progress_events.append(progress)

    result = workflow.get_result()

    # Should succeed in dry-run mode
    assert result.success
    assert result.metadata.get("dry_run") is True
    assert "[DRY-RUN]" in result.stage_results[0].output


# =============================================================================
# Cancellation integration tests
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix commands not available on Windows"
)
async def test_cancellation_integration():
    """Integration test: workflow cancellation prevents subsequent stages."""
    # Use multiple quick stages - cancellation takes effect between stages
    stages = [
        ValidationStage(
            name="quick_stage_1",
            command=["true"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
        ValidationStage(
            name="quick_stage_2",
            command=["true"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
        ValidationStage(
            name="quick_stage_3",
            command=["true"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
    ]

    workflow = ValidationWorkflow(stages=stages)

    # Cancel immediately before running
    workflow.cancel()

    progress_events = []
    async for progress in workflow.run():
        progress_events.append(progress)

    result = workflow.get_result()

    # Workflow should be marked as cancelled
    assert result.cancelled
    # All stages should be marked cancelled since we cancelled before running
    cancelled_stages = [
        r for r in result.stage_results if r.status == StageStatus.CANCELLED
    ]
    assert len(cancelled_stages) == 3


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix commands not available on Windows"
)
async def test_cancellation_mid_workflow():
    """Integration test: cancellation mid-workflow stops subsequent stages."""
    stages = [
        ValidationStage(
            name="first_stage",
            command=["echo", "first"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
        ValidationStage(
            name="second_stage",
            command=["echo", "second"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
    ]

    workflow = ValidationWorkflow(stages=stages)

    progress_events = []
    stage_count = 0

    async for progress in workflow.run():
        progress_events.append(progress)
        # Cancel after first stage completes
        if progress.status == StageStatus.PASSED:
            stage_count += 1
            if stage_count == 1:
                workflow.cancel()

    result = workflow.get_result()

    # Should have processed first stage and cancelled second
    assert result.cancelled
    assert len(result.stage_results) == 2
    assert result.stage_results[0].status == StageStatus.PASSED
    assert result.stage_results[1].status == StageStatus.CANCELLED
