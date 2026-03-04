"""Unit tests for render_workflow_events in workflow_executor.

Tests verify that RollbackStarted, RollbackCompleted, and CheckpointSaved
events are rendered correctly to the console.
"""

from __future__ import annotations

import io
from typing import Any

from rich.console import Console

from maverick.events import (
    CheckpointSaved,
    RollbackCompleted,
    RollbackStarted,
    WorkflowCompleted,
    WorkflowStarted,
)


async def _render_events(events: list[Any]) -> str:
    """Render a sequence of events through render_workflow_events and capture output.

    Wraps events in WorkflowStarted/WorkflowCompleted framing so the renderer
    does not error on missing lifecycle events. Returns the captured console
    output as a plain string (no ANSI codes).

    Args:
        events: List of ProgressEvent instances to render (excluding
            WorkflowStarted/WorkflowCompleted which are added automatically).

    Returns:
        Captured console output as a string.
    """
    from maverick.cli.workflow_executor import render_workflow_events

    all_events = [
        WorkflowStarted(workflow_name="test-wf", inputs={}),
        *events,
        WorkflowCompleted(workflow_name="test-wf", success=True, total_duration_ms=100),
    ]

    async def _event_iter():  # noqa: ANN202
        for event in all_events:
            yield event

    buf = io.StringIO()
    test_console = Console(file=buf, force_terminal=False, no_color=True, width=120)

    await render_workflow_events(
        _event_iter(),
        test_console,
    )

    return buf.getvalue()


class TestRollbackStartedRendering:
    """RollbackStarted event rendering."""

    async def test_rollback_started_renders_step_name(self) -> None:
        """RollbackStarted event renders the step name."""
        output = await _render_events(
            [
                RollbackStarted(step_name="create_workspace"),
            ]
        )
        assert "create_workspace" in output

    async def test_rollback_started_contains_rolling_back_text(self) -> None:
        """RollbackStarted event includes 'Rolling back' indicator."""
        output = await _render_events(
            [
                RollbackStarted(step_name="setup_branch"),
            ]
        )
        assert "Rolling back" in output

    async def test_rollback_started_contains_arrow_icon(self) -> None:
        """RollbackStarted event includes the rollback arrow icon."""
        output = await _render_events(
            [
                RollbackStarted(step_name="setup_branch"),
            ]
        )
        assert "\u21a9" in output


class TestRollbackCompletedRendering:
    """RollbackCompleted event rendering."""

    async def test_rollback_completed_success_renders_check(self) -> None:
        """RollbackCompleted with success=True renders a check mark."""
        output = await _render_events(
            [
                RollbackCompleted(step_name="cleanup", success=True),
            ]
        )
        assert "\u2713" in output
        assert "cleanup" in output

    async def test_rollback_completed_success_text(self) -> None:
        """RollbackCompleted with success=True includes 'succeeded' text."""
        output = await _render_events(
            [
                RollbackCompleted(step_name="cleanup", success=True),
            ]
        )
        assert "succeeded" in output

    async def test_rollback_completed_failure_renders_x(self) -> None:
        """RollbackCompleted with success=False renders an X mark."""
        output = await _render_events(
            [
                RollbackCompleted(step_name="cleanup", success=False),
            ]
        )
        assert "\u2717" in output
        assert "cleanup" in output

    async def test_rollback_completed_failure_text(self) -> None:
        """RollbackCompleted with success=False includes 'failed' text."""
        output = await _render_events(
            [
                RollbackCompleted(step_name="cleanup", success=False),
            ]
        )
        assert "failed" in output

    async def test_rollback_completed_failure_shows_error(self) -> None:
        """RollbackCompleted with error shows the error message."""
        output = await _render_events(
            [
                RollbackCompleted(
                    step_name="cleanup",
                    success=False,
                    error="permission denied",
                ),
            ]
        )
        assert "permission denied" in output

    async def test_rollback_completed_failure_without_error(self) -> None:
        """RollbackCompleted with success=False and no error still renders."""
        output = await _render_events(
            [
                RollbackCompleted(step_name="cleanup", success=False, error=None),
            ]
        )
        assert "cleanup" in output
        assert "failed" in output


class TestCheckpointSavedRendering:
    """CheckpointSaved event rendering."""

    async def test_checkpoint_saved_renders_step_name(self) -> None:
        """CheckpointSaved event renders the step name."""
        output = await _render_events(
            [
                CheckpointSaved(step_name="after_install", workflow_id="fly-beads"),
            ]
        )
        assert "after_install" in output

    async def test_checkpoint_saved_contains_checkpoint_text(self) -> None:
        """CheckpointSaved event includes 'Checkpoint saved' text."""
        output = await _render_events(
            [
                CheckpointSaved(step_name="after_install", workflow_id="fly-beads"),
            ]
        )
        assert "Checkpoint saved" in output

    async def test_checkpoint_saved_contains_floppy_icon(self) -> None:
        """CheckpointSaved event includes the floppy disk icon."""
        output = await _render_events(
            [
                CheckpointSaved(step_name="after_install", workflow_id="fly-beads"),
            ]
        )
        assert "\U0001f4be" in output
