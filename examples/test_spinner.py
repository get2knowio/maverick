"""Quick visual test for animated spinner in WorkflowProgress widget."""

from __future__ import annotations

from datetime import datetime, timedelta

from textual.app import App, ComposeResult

from maverick.tui.models import StageStatus, WorkflowStage
from maverick.tui.widgets.workflow_progress import WorkflowProgress


class SpinnerTestApp(App):
    """Test app to verify animated spinner on active stages."""

    CSS = """
    Screen {
        background: $surface;
    }

    WorkflowProgress {
        width: 100%;
        height: 100%;
        border: solid $primary;
    }

    .stage-spinner {
        width: 3;
        margin-right: 1;
    }

    .stage-label {
        content-align: left middle;
    }

    .status-active {
        color: $accent;
    }

    .status-completed {
        color: $success;
    }

    .status-failed {
        color: $error;
    }

    .status-pending {
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the test app."""
        yield WorkflowProgress(id="workflow-progress")

    def on_mount(self) -> None:
        """Set up test stages when app is mounted."""
        now = datetime.now()

        stages = [
            WorkflowStage(
                name="setup",
                display_name="Setup Environment",
                status=StageStatus.COMPLETED,
                started_at=now - timedelta(seconds=30),
                completed_at=now - timedelta(seconds=20),
                detail_content="Branch synced with origin/main",
            ),
            WorkflowStage(
                name="implementation",
                display_name="Implementation",
                status=StageStatus.ACTIVE,
                started_at=now - timedelta(seconds=10),
                detail_content="Running task T001: Implement feature X\nProcessing files...",
            ),
            WorkflowStage(
                name="review",
                display_name="Code Review",
                status=StageStatus.PENDING,
                detail_content="Awaiting implementation completion",
            ),
            WorkflowStage(
                name="validation",
                display_name="Validation",
                status=StageStatus.PENDING,
            ),
        ]

        widget = self.query_one("#workflow-progress", WorkflowProgress)
        widget.update_stages(stages)


if __name__ == "__main__":
    app = SpinnerTestApp()
    app.run()
