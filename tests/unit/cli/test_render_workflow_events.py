"""Unit tests for render_workflow_events in workflow_executor.

Tests verify that RollbackStarted, RollbackCompleted, CheckpointSaved,
AgentStreamChunk, LoopIterationStarted, and LoopIterationCompleted events
are rendered correctly to the console.
"""

from __future__ import annotations

import io
from typing import Any

from rich.console import Console

from maverick.events import (
    AgentStreamChunk,
    CheckpointSaved,
    LoopIterationCompleted,
    LoopIterationStarted,
    RollbackCompleted,
    RollbackStarted,
    StepCompleted,
    StepOutput,
    StepStarted,
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.types import StepType


async def _render_events(
    events: list[Any],
    *,
    verbosity: int = 0,
) -> str:
    """Render a sequence of events through render_workflow_events and capture output.

    Wraps events in WorkflowStarted/WorkflowCompleted framing so the renderer
    does not error on missing lifecycle events. Returns the captured console
    output as a plain string (no ANSI codes).

    Args:
        events: List of ProgressEvent instances to render (excluding
            WorkflowStarted/WorkflowCompleted which are added automatically).
        verbosity: Verbosity level (0=normal, 1+=verbose).

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
        verbosity=verbosity,
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
        assert "After Install" in output

    async def test_checkpoint_saved_contains_checkpoint_text(self) -> None:
        """CheckpointSaved event includes 'Checkpoint saved' text."""
        output = await _render_events(
            [
                CheckpointSaved(step_name="after_install", workflow_id="fly-beads"),
            ]
        )
        assert "Checkpoint saved" in output

    async def test_checkpoint_saved_contains_checkpoint_label(self) -> None:
        """CheckpointSaved event includes 'Checkpoint saved' text."""
        output = await _render_events(
            [
                CheckpointSaved(step_name="after_install", workflow_id="fly-beads"),
            ]
        )
        assert "Checkpoint saved" in output


class TestAgentStreamChunkRendering:
    """AgentStreamChunk event rendering with verbosity control."""

    async def test_agent_stream_suppressed_in_normal_mode(self) -> None:
        """Agent stream chunks are not shown in normal mode (verbosity=0)."""
        output = await _render_events(
            [
                AgentStreamChunk(
                    step_name="implement",
                    agent_name="implementer",
                    text='{"summary": "did stuff"}',
                    chunk_type="output",
                ),
            ],
            verbosity=0,
        )
        assert "did stuff" not in output

    async def test_agent_stream_shown_in_verbose_mode(self) -> None:
        """Agent stream chunks are shown in verbose mode (verbosity=1)."""
        output = await _render_events(
            [
                AgentStreamChunk(
                    step_name="implement",
                    agent_name="implementer",
                    text="Working on implementation...",
                    chunk_type="output",
                ),
            ],
            verbosity=1,
        )
        assert "Working on implementation..." in output

    async def test_tool_calls_rendered_as_dim_in_verbose(self) -> None:
        """[TOOL] markers are rendered as dim status lines in verbose mode."""
        output = await _render_events(
            [
                AgentStreamChunk(
                    step_name="implement",
                    agent_name="implementer",
                    text="[TOOL] Read\n",
                    chunk_type="output",
                ),
            ],
            verbosity=1,
        )
        # Should show the tool name but not the raw [TOOL] prefix
        assert "Read" in output
        assert "[TOOL]" not in output

    async def test_tool_calls_suppressed_in_normal_mode(self) -> None:
        """[TOOL] markers are suppressed in normal mode."""
        output = await _render_events(
            [
                AgentStreamChunk(
                    step_name="implement",
                    agent_name="implementer",
                    text="[TOOL] Read\n",
                    chunk_type="output",
                ),
            ],
            verbosity=0,
        )
        assert "Read" not in output

    async def test_agent_stream_newline_before_step_completed(self) -> None:
        """StepCompleted after agent stream adds a newline to separate."""
        output = await _render_events(
            [
                StepStarted(step_name="implement", step_type=StepType.AGENT),
                AgentStreamChunk(
                    step_name="implement",
                    agent_name="implementer",
                    text="some output",
                    chunk_type="output",
                ),
                StepCompleted(
                    step_name="implement",
                    step_type=StepType.AGENT,
                    success=True,
                    duration_ms=1234,
                ),
            ],
            verbosity=1,
        )
        assert "\u2713" in output


class TestStepDisplayNames:
    """StepStarted shows human-readable display names without type annotations."""

    async def test_python_step_shows_display_label(self) -> None:
        """Python step shows display_label from event, no (python) annotation."""
        output = await _render_events(
            [
                StepStarted(
                    step_name="preflight",
                    step_type=StepType.PYTHON,
                    display_label="Pre-flight checks",
                ),
                StepCompleted(
                    step_name="preflight",
                    step_type=StepType.PYTHON,
                    success=True,
                    duration_ms=10,
                    display_label="Pre-flight checks",
                ),
            ],
        )
        assert "Pre-flight checks" in output
        assert "(python)" not in output

    async def test_agent_step_shows_display_label(self) -> None:
        """Agent step shows display_label, no (agentic) annotation."""
        output = await _render_events(
            [
                StepStarted(
                    step_name="decompose",
                    step_type=StepType.AGENT,
                    display_label="Decomposing",
                    provider="copilot",
                    model_id="sonnet",
                ),
                StepCompleted(
                    step_name="decompose",
                    step_type=StepType.AGENT,
                    success=True,
                    duration_ms=10,
                    display_label="Decomposing",
                ),
            ],
        )
        assert "Decomposing" in output
        assert "(agentic)" not in output
        assert "copilot" not in output
        assert "sonnet" not in output

    async def test_no_display_label_falls_back_to_title_case(self) -> None:
        """Steps without display_label fall back to title-cased step name."""
        output = await _render_events(
            [
                StepStarted(step_name="custom_new_step", step_type=StepType.PYTHON),
                StepCompleted(
                    step_name="custom_new_step",
                    step_type=StepType.PYTHON,
                    success=True,
                    duration_ms=10,
                ),
            ],
        )
        assert "Custom New Step" in output


class TestLoopIterationRendering:
    """LoopIterationStarted and LoopIterationCompleted event rendering."""

    async def test_loop_iteration_started_shows_label(self) -> None:
        """LoopIterationStarted renders the item label."""
        output = await _render_events(
            [
                LoopIterationStarted(
                    step_name="bead_loop",
                    iteration_index=0,
                    total_iterations=3,
                    item_label="add-greet-command",
                ),
            ],
        )
        assert "add-greet-command" in output

    async def test_loop_iteration_started_shows_index(self) -> None:
        """LoopIterationStarted renders 1-based index."""
        output = await _render_events(
            [
                LoopIterationStarted(
                    step_name="bead_loop",
                    iteration_index=1,
                    total_iterations=5,
                    item_label="task-two",
                ),
            ],
        )
        assert "[2/5]" in output

    async def test_loop_iteration_completed_success(self) -> None:
        """LoopIterationCompleted with success shows completion message."""
        output = await _render_events(
            [
                LoopIterationCompleted(
                    step_name="bead_loop",
                    iteration_index=0,
                    success=True,
                    duration_ms=5000,
                ),
            ],
        )
        assert "completed" in output
        assert "5.00s" in output

    async def test_loop_iteration_completed_failure_shows_error(self) -> None:
        """LoopIterationCompleted with failure shows error message."""
        output = await _render_events(
            [
                LoopIterationCompleted(
                    step_name="bead_loop",
                    iteration_index=2,
                    success=False,
                    duration_ms=3000,
                    error="validation failed",
                ),
            ],
        )
        assert "failed" in output
        assert "validation failed" in output


class TestStepLifecycleRendering:
    """R1: Step lifecycle with start and completion lines."""

    async def test_completion_line_includes_step_name(self) -> None:
        """R1: Completion line includes display label and timing."""
        output = await _render_events(
            [
                StepStarted(
                    step_name="read_prd",
                    step_type=StepType.PYTHON,
                    display_label="Reading PRD",
                ),
                StepCompleted(
                    step_name="read_prd",
                    step_type=StepType.PYTHON,
                    success=True,
                    duration_ms=10,
                    display_label="Reading PRD",
                ),
            ],
        )
        assert "✓" in output
        assert "Reading PRD" in output
        assert "0.01s" in output

    async def test_step_output_shown_as_interim(self) -> None:
        """R2: StepOutput shown as interim line under header."""
        output = await _render_events(
            [
                StepStarted(
                    step_name="validate",
                    step_type=StepType.PYTHON,
                    display_label="Validating",
                ),
                StepOutput(step_name="validate", message="All checks passed"),
                StepCompleted(
                    step_name="validate",
                    step_type=StepType.PYTHON,
                    success=True,
                    duration_ms=10,
                    display_label="Validating",
                ),
            ],
        )
        assert "✓" in output
        assert "All checks passed" in output
        assert "0.01s" in output

    async def test_failed_step_shows_x_and_error(self) -> None:
        """R1: Failed step shows ✗ with error."""
        output = await _render_events(
            [
                StepStarted(
                    step_name="validate",
                    step_type=StepType.PYTHON,
                    display_label="Validating",
                ),
                StepCompleted(
                    step_name="validate",
                    step_type=StepType.PYTHON,
                    success=False,
                    duration_ms=500,
                    error="schema invalid",
                    display_label="Validating",
                ),
            ],
        )
        assert "✗" in output
        assert "Validating" in output
        assert "schema invalid" in output


class TestInterimPrefix:
    """R3: Interim lines use ∟ prefix."""

    async def test_step_output_renders_as_interim(self) -> None:
        """StepOutput renders as ∟ interim line under header."""
        output = await _render_events(
            [
                StepStarted(
                    step_name="read_prd",
                    step_type=StepType.PYTHON,
                    display_label="Reading PRD",
                ),
                StepOutput(
                    step_name="read_prd",
                    message='PRD: "Greet CLI" (3195 chars)',
                ),
                StepCompleted(
                    step_name="read_prd",
                    step_type=StepType.PYTHON,
                    success=True,
                    duration_ms=5,
                    display_label="Reading PRD",
                ),
            ],
        )
        assert 'PRD: "Greet CLI" (3195 chars)' in output
        assert "✓" in output
        # Header + interim + completion
        lines = output.strip().splitlines()
        interim_lines = [ln for ln in lines if "∟" in ln]
        assert len(interim_lines) == 1

    async def test_all_outputs_shown_as_interims(self) -> None:
        """R3: All StepOutputs shown as ∟ interims."""
        output = await _render_events(
            [
                StepStarted(
                    step_name="briefing",
                    step_type=StepType.AGENT,
                    display_label="Briefing",
                ),
                StepOutput(step_name="briefing", message="Agent A started"),
                StepOutput(step_name="briefing", message="Agent A done"),
                StepOutput(step_name="briefing", message="Briefing complete"),
                StepCompleted(
                    step_name="briefing",
                    step_type=StepType.AGENT,
                    success=True,
                    duration_ms=5000,
                    display_label="Briefing",
                ),
            ],
        )
        lines = output.strip().splitlines()
        interim_lines = [ln for ln in lines if "∟" in ln]
        assert len(interim_lines) == 3
        assert "Agent A started" in interim_lines[0]
        assert "Agent A done" in interim_lines[1]
        assert "Briefing complete" in interim_lines[2]
