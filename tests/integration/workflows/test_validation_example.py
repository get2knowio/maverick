"""Example integration test for validation workflow.

This file demonstrates simple testing patterns using TestWorkflowRunner
and AsyncGeneratorCapture for validation workflow integration tests.
"""

from __future__ import annotations

import sys

import pytest

from maverick.models.validation import (
    ProgressUpdate,
    StageStatus,
    ValidationStage,
    ValidationWorkflowConfig,
)
from maverick.workflows.validation import ValidationWorkflow
from tests.utils.async_helpers import AsyncGeneratorCapture
from tests.utils.workflow_helpers import TestWorkflowRunner

# =============================================================================
# Example: Simple workflow execution with TestWorkflowRunner
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix commands not available on Windows"
)
async def test_simple_workflow_with_runner():
    """Example: Simple workflow execution using TestWorkflowRunner.

    Demonstrates:
    - Creating a workflow with simple stages
    - Using TestWorkflowRunner to execute and capture events
    - Checking workflow result and duration
    - Using assert_stage_passed for validation
    """
    # Create a simple workflow with two passing stages
    stages = [
        ValidationStage(
            name="first",
            command=["echo", "Starting validation"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
        ValidationStage(
            name="second",
            command=["true"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
    ]

    workflow = ValidationWorkflow(stages=stages)

    # Use TestWorkflowRunner to execute and capture
    runner = TestWorkflowRunner()
    result = await runner.run(workflow)

    # Verify overall success
    assert result.success
    assert runner.duration_ms >= 0  # May be 0 if workflow runs very fast

    # Verify both stages passed using assert_stage_passed
    runner.assert_stage_passed("first")
    runner.assert_stage_passed("second")


# =============================================================================
# Example: Event filtering with get_events
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix commands not available on Windows"
)
async def test_workflow_event_filtering():
    """Example: Filter captured events by type using get_events.

    Demonstrates:
    - Capturing all workflow events
    - Filtering events by type using get_events()
    - Inspecting specific progress updates
    """
    stages = [
        ValidationStage(
            name="lint",
            command=["echo", "Running linter"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
    ]

    workflow = ValidationWorkflow(stages=stages)

    # Execute and capture
    runner = TestWorkflowRunner()
    await runner.run(workflow)

    # Get all events
    all_events = runner.get_events()
    assert len(all_events) > 0

    # Filter for ProgressUpdate events
    progress_events = runner.get_events(ProgressUpdate)
    assert len(progress_events) >= 2  # At least START and PASSED/FAILED

    # Verify we have expected progress transitions
    statuses = [event.status for event in progress_events]
    assert StageStatus.IN_PROGRESS in statuses
    assert StageStatus.PASSED in statuses or StageStatus.FAILED in statuses


# =============================================================================
# Example: Using AsyncGeneratorCapture directly
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix commands not available on Windows"
)
async def test_direct_async_generator_capture():
    """Example: Use AsyncGeneratorCapture for direct event capture.

    Demonstrates:
    - Direct use of AsyncGeneratorCapture for workflow events
    - Checking completion status
    - Using filter_by_type for event filtering
    """
    stages = [
        ValidationStage(
            name="build",
            command=["echo", "Building project"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
    ]

    workflow = ValidationWorkflow(stages=stages)

    # Capture events directly from workflow.run()
    capture = await AsyncGeneratorCapture.capture(workflow.run())

    # Verify capture completed successfully
    assert capture.completed
    assert capture.error is None
    assert len(capture) > 0

    # Filter for progress updates
    progress_updates = capture.filter_by_type(ProgressUpdate)
    assert len(progress_updates) >= 2

    # Get first and last progress update
    first_update = capture.first_of_type(ProgressUpdate)
    last_update = capture.last_of_type(ProgressUpdate)

    assert first_update is not None
    assert last_update is not None
    assert first_update.stage == "build"
    assert last_update.stage == "build"


# =============================================================================
# Example: Testing workflow with configuration
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix commands not available on Windows"
)
async def test_workflow_with_config():
    """Example: Test workflow with custom configuration.

    Demonstrates:
    - Creating workflow with ValidationWorkflowConfig
    - Testing dry-run mode behavior
    - Verifying metadata in results
    """
    stages = [
        ValidationStage(
            name="check",
            command=["echo", "Checking code"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
    ]

    # Create workflow with dry-run config
    config = ValidationWorkflowConfig(dry_run=True)
    workflow = ValidationWorkflow(stages=stages, config=config)

    runner = TestWorkflowRunner()
    result = await runner.run(workflow)

    # Verify dry-run behavior
    assert result.success
    assert result.metadata.get("dry_run") is True

    # Dry-run stages should show [DRY-RUN] in output
    assert "[DRY-RUN]" in result.stage_results[0].output


# =============================================================================
# Example: Testing stage failure scenarios
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix commands not available on Windows"
)
async def test_workflow_with_failure():
    """Example: Test workflow with expected stage failure.

    Demonstrates:
    - Testing failure scenarios
    - Inspecting stage results for failures
    - Verifying error messages
    """
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

    runner = TestWorkflowRunner()
    result = await runner.run(workflow)

    # Verify overall workflow failed
    assert not result.success

    # First stage should pass
    runner.assert_stage_passed("pass_stage")

    # Second stage should fail - verify using stage results
    fail_result = result.stage_results[1]
    assert fail_result.stage_name == "fail_stage"
    assert fail_result.status == StageStatus.FAILED
    assert not fail_result.passed


# =============================================================================
# Example: Testing multiple stages with assertions
# =============================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(
    sys.platform == "win32", reason="Unix commands not available on Windows"
)
async def test_multi_stage_workflow():
    """Example: Test workflow with multiple stages and various assertions.

    Demonstrates:
    - Testing multiple stages in sequence
    - Using assert_stage_passed for each stage
    - Verifying result summary and counts
    """
    stages = [
        ValidationStage(
            name="format",
            command=["echo", "Formatting code"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
        ValidationStage(
            name="lint",
            command=["echo", "Linting code"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
        ValidationStage(
            name="test",
            command=["echo", "Running tests"],
            fixable=False,
            max_fix_attempts=0,
            timeout_seconds=10.0,
        ),
    ]

    workflow = ValidationWorkflow(stages=stages)

    runner = TestWorkflowRunner()
    result = await runner.run(workflow)

    # Verify all stages passed
    assert result.success
    assert result.passed_count == 3
    assert result.failed_count == 0

    # Assert each stage individually
    runner.assert_stage_passed("format")
    runner.assert_stage_passed("lint")
    runner.assert_stage_passed("test")

    # Check summary string
    assert "3/3 passed" in result.summary
