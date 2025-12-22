"""Workflow testing utilities.

This module provides utilities for testing workflow execution, particularly
for capturing progress events and validating workflow behavior.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from tests.utils.async_helpers import AsyncGeneratorCapture

__all__ = ["TestWorkflowRunner"]


@dataclass
class TestWorkflowRunner:
    """Utility for running workflows with mocked agents and capturing progress events.

    Executes a workflow's run() method (async generator), captures all yielded
    progress events, and provides convenient methods for filtering events and
    making assertions about workflow execution.

    Attributes:
        events: List of all captured progress events from the workflow
        result: Final workflow result (from get_result() if available)
        duration_ms: Total execution time in milliseconds

    Example:
        >>> @pytest.mark.asyncio
        ... async def test_validation_workflow():
        ...     workflow = ValidationWorkflow(stages=[...])
        ...     runner = TestWorkflowRunner()
        ...     result = await runner.run(workflow)
        ...
        ...     # Check execution succeeded
        ...     assert result.success
        ...     assert runner.duration_ms > 0
        ...
        ...     # Verify specific events were emitted
        ...     progress_events = runner.get_events(ProgressUpdate)
        ...     assert len(progress_events) >= 2
        ...
        ...     # Assert stages passed
        ...     runner.assert_stage_passed("lint")
        ...     runner.assert_stage_passed("test")
    """

    events: list[Any] = field(default_factory=list)
    result: Any | None = None
    duration_ms: int = 0

    async def run(self, workflow: Any) -> Any:
        """Execute a workflow and capture all progress events.

        Runs the workflow's run() method (which must be an async generator),
        captures all yielded events, and retrieves the final result if the
        workflow provides a get_result() method.

        Args:
            workflow: Workflow instance with a run() async generator method.
                     Optionally may have a get_result() method for final result.

        Returns:
            The workflow's final result (from get_result() if available),
            or None if the workflow doesn't provide a get_result() method.

        Raises:
            AttributeError: If workflow doesn't have a run() method.
            Any exception raised by the workflow during execution.

        Example:
            >>> workflow = ValidationWorkflow(stages=[...])
            >>> runner = TestWorkflowRunner()
            >>> result = await runner.run(workflow)
            >>> assert result.success
            >>> assert len(runner.events) > 0
        """
        start_time = time.time()

        # Capture all events from the workflow's async generator
        capture = await AsyncGeneratorCapture.capture(workflow.run())

        # Calculate duration
        self.duration_ms = int((time.time() - start_time) * 1000)

        # Store captured events
        self.events = capture.items

        # Try to get the final result if workflow provides get_result()
        if hasattr(workflow, "get_result"):
            # Some workflows may raise RuntimeError if get_result() called
            # before completion. In that case, result remains None
            try:
                self.result = workflow.get_result()
            except RuntimeError as e:
                # Only suppress expected "not complete" errors; re-raise others
                if "not complete" not in str(e).lower():
                    raise

        return self.result

    def get_events(self, event_type: type | None = None) -> list[Any]:
        """Filter captured events by type.

        Retrieves all events of a specific type, or all events if no type
        is specified.

        Args:
            event_type: The type to filter by, or None to return all events.

        Returns:
            List of events matching the specified type, or all events if
            event_type is None.

        Example:
            >>> from maverick.models.validation import ProgressUpdate, StageStatus
            >>> runner = TestWorkflowRunner()
            >>> await runner.run(workflow)
            >>>
            >>> # Get all progress updates
            >>> updates = runner.get_events(ProgressUpdate)
            >>> assert all(isinstance(e, ProgressUpdate) for e in updates)
            >>>
            >>> # Get all events
            >>> all_events = runner.get_events()
            >>> assert len(all_events) == len(runner.events)
        """
        if event_type is None:
            return self.events

        return [event for event in self.events if isinstance(event, event_type)]

    def assert_stage_passed(self, stage_name: str) -> None:
        """Assert that a specific stage passed during workflow execution.

        Searches through all stage results in the workflow result and asserts
        that the specified stage has a passing status (PASSED or FIXED).

        Args:
            stage_name: Name of the stage to check.

        Raises:
            AssertionError: If the stage did not pass or was not found.
            AttributeError: If workflow result doesn't have stage_results.

        Example:
            >>> runner = TestWorkflowRunner()
            >>> result = await runner.run(workflow)
            >>> runner.assert_stage_passed("lint")  # Passes if lint stage passed
            >>> runner.assert_stage_passed("test")  # Passes if test stage passed
        """
        if self.result is None:
            raise AssertionError(
                f"Cannot verify stage '{stage_name}': workflow result is None"
            )

        # Access stage_results from the workflow result
        if not hasattr(self.result, "stage_results"):
            raise AttributeError(
                f"Workflow result does not have 'stage_results' attribute. "
                f"Result type: {type(self.result).__name__}"
            )

        stage_results = self.result.stage_results

        # Find the stage in the results
        for stage_result in stage_results:
            if stage_result.stage_name == stage_name:
                # Check if stage passed (using the passed property if available)
                passed = (
                    stage_result.passed
                    if hasattr(stage_result, "passed")
                    else stage_result.status in ("passed", "fixed")
                )

                if not passed:
                    raise AssertionError(
                        f"Stage '{stage_name}' did not pass. "
                        f"Status: {stage_result.status}, "
                        f"Error: {getattr(stage_result, 'error_message', 'N/A')}"
                    )
                return

        # Stage not found in results
        raise AssertionError(
            f"Stage '{stage_name}' not found in workflow results. "
            f"Available stages: {[r.stage_name for r in stage_results]}"
        )
