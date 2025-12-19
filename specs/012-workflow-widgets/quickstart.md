# Quickstart: Workflow Visualization Widgets

**Feature**: 012-workflow-widgets
**Date**: 2025-12-16

This guide provides quick-reference patterns for implementing and using the workflow visualization widgets.

## Prerequisites

- Python 3.10+
- Textual 0.40+
- Maverick TUI foundation (spec 011)

## Widget Overview

| Widget | Purpose | Key Features |
|--------|---------|--------------|
| WorkflowProgress | Stage tracking | Status icons, duration, expandable details |
| AgentOutput | Message display | Streaming, syntax highlighting, search |
| ReviewFindings | Code review findings | Grouping, selection, bulk actions |
| ValidationStatus | Validation steps | Compact display, error expansion, re-run |
| PRSummary | PR metadata | Title, checks, browser link |

---

## WorkflowProgress Widget

### Basic Usage

```python
from maverick.tui.widgets import WorkflowProgress
from maverick.tui.models import WorkflowStage, StageStatus
from datetime import datetime

# Create widget
progress = WorkflowProgress(id="workflow-progress")

# Update with stages
stages = [
    WorkflowStage(
        name="setup",
        display_name="Setup",
        status=StageStatus.COMPLETED,
        started_at=datetime(2025, 1, 1, 10, 0, 0),
        completed_at=datetime(2025, 1, 1, 10, 0, 5),
    ),
    WorkflowStage(
        name="implementation",
        display_name="Implementation",
        status=StageStatus.ACTIVE,
        started_at=datetime(2025, 1, 1, 10, 0, 5),
    ),
    WorkflowStage(
        name="review",
        display_name="Code Review",
        status=StageStatus.PENDING,
    ),
]
progress.update_stages(stages)
```

### Update Single Stage

```python
# Update status with error
progress.update_stage_status(
    "implementation",
    StageStatus.FAILED,
    error_message="Build failed: missing dependency",
)
```

### Handle Stage Expansion

```python
def on_workflow_progress_stage_expanded(
    self, event: WorkflowProgress.StageExpanded
) -> None:
    self.log(f"Stage expanded: {event.stage_name}")
```

---

## AgentOutput Widget

### Basic Usage

```python
from maverick.tui.widgets import AgentOutput
from maverick.tui.models import AgentMessage, MessageType
from datetime import datetime

# Create widget
output = AgentOutput(id="agent-output")

# Add a text message
output.add_message(AgentMessage(
    id="msg-1",
    timestamp=datetime.now(),
    agent_id="implementer",
    agent_name="Implementer Agent",
    message_type=MessageType.TEXT,
    content="Starting implementation of feature...",
))

# Add a code block
output.add_message(AgentMessage(
    id="msg-2",
    timestamp=datetime.now(),
    agent_id="implementer",
    agent_name="Implementer Agent",
    message_type=MessageType.CODE,
    content="def hello():\n    print('Hello, World!')",
    language="python",
))

# Add a tool call
output.add_message(AgentMessage(
    id="msg-3",
    timestamp=datetime.now(),
    agent_id="implementer",
    agent_name="Implementer Agent",
    message_type=MessageType.TOOL_CALL,
    content="",
    tool_call=ToolCallInfo(
        tool_name="write_file",
        arguments='{"path": "src/main.py", "content": "..."}',
        result="File written successfully",
    ),
))
```

### Search and Filter

```python
# Enable search
output.set_search_query("error")

# Filter by agent
output.set_agent_filter("implementer")

# Clear filters
output.set_search_query(None)
output.set_agent_filter(None)
```

### Auto-scroll Control

```python
# Disable auto-scroll
output.set_auto_scroll(False)

# Scroll to bottom manually
output.scroll_to_bottom()
```

---

## ReviewFindings Widget

### Basic Usage

```python
from maverick.tui.widgets import ReviewFindings
from maverick.tui.models import ReviewFinding, FindingSeverity, CodeLocation

# Create widget
findings_widget = ReviewFindings(id="review-findings")

# Update with findings
findings = [
    ReviewFinding(
        id="f-1",
        severity=FindingSeverity.ERROR,
        location=CodeLocation(file_path="src/main.py", line_number=42),
        title="Unused import",
        description="The import 'os' is not used in this module.",
        suggested_fix="Remove the unused import statement.",
        source="coderabbit",
    ),
    ReviewFinding(
        id="f-2",
        severity=FindingSeverity.WARNING,
        location=CodeLocation(file_path="src/utils.py", line_number=15),
        title="Missing type hint",
        description="Function 'process' is missing return type annotation.",
        source="architecture",
    ),
]
findings_widget.update_findings(findings)
```

### Selection and Bulk Actions

```python
# Select individual findings
findings_widget.select_finding(0, selected=True)
findings_widget.select_finding(1, selected=True)

# Select all
findings_widget.select_all()

# Get selected findings
selected = findings_widget.selected_findings
print(f"Selected {len(selected)} findings")

# Deselect all
findings_widget.deselect_all()
```

### Handle Events

```python
def on_review_findings_bulk_dismiss_requested(
    self, event: ReviewFindings.BulkDismissRequested
) -> None:
    # Remove findings from list
    for finding_id in event.finding_ids:
        self.dismiss_finding(finding_id)

def on_review_findings_file_location_clicked(
    self, event: ReviewFindings.FileLocationClicked
) -> None:
    # Show code context panel
    self.show_code_context(event.file_path, event.line_number)
```

---

## ValidationStatus Widget

### Basic Usage

```python
from maverick.tui.widgets import ValidationStatus
from maverick.tui.models import ValidationStep, ValidationStepStatus

# Create widget
validation = ValidationStatus(id="validation-status")

# Update with steps
steps = [
    ValidationStep(
        name="format",
        display_name="Format",
        status=ValidationStepStatus.PASSED,
    ),
    ValidationStep(
        name="lint",
        display_name="Lint",
        status=ValidationStepStatus.FAILED,
        error_output="src/main.py:42: E501 line too long (120 > 100)",
        command="ruff check src/",
    ),
    ValidationStep(
        name="build",
        display_name="Build",
        status=ValidationStepStatus.PENDING,
    ),
    ValidationStep(
        name="test",
        display_name="Test",
        status=ValidationStepStatus.PENDING,
    ),
]
validation.update_steps(steps)
```

### Handle Re-run Request

```python
def on_validation_status_rerun_requested(
    self, event: ValidationStatus.RerunRequested
) -> None:
    # Disable button while running
    validation.set_rerun_enabled(event.step_name, False)

    # Re-run the validation step
    async def run_step():
        result = await self.run_validation_step(event.step_name)
        validation.update_step_status(
            event.step_name,
            ValidationStepStatus.PASSED if result.success else ValidationStepStatus.FAILED,
            error_output=result.error_output,
        )
        validation.set_rerun_enabled(event.step_name, True)

    asyncio.create_task(run_step())
```

---

## PRSummary Widget

### Basic Usage

```python
from maverick.tui.widgets import PRSummary
from maverick.tui.models import PRInfo, PRState, StatusCheck, CheckStatus

# Create widget
pr_summary = PRSummary(id="pr-summary")

# Update with PR data
pr = PRInfo(
    number=42,
    title="Add workflow visualization widgets",
    description="## Summary\n\nThis PR adds five widgets...",
    state=PRState.OPEN,
    url="https://github.com/owner/repo/pull/42",
    checks=(
        StatusCheck(name="CI / build", status=CheckStatus.PASSING),
        StatusCheck(name="CI / test", status=CheckStatus.PASSING),
        StatusCheck(name="CodeRabbit", status=CheckStatus.PENDING),
    ),
    branch="012-workflow-widgets",
    base_branch="main",
)
pr_summary.update_pr(pr)
```

### Loading State

```python
# Show loading indicator
pr_summary.set_loading(True)

# Fetch PR data...
pr_data = await fetch_pr_data()

# Update and clear loading
pr_summary.update_pr(pr_data)
pr_summary.set_loading(False)
```

### Handle Open PR

```python
def on_pr_summary_open_pr_requested(
    self, event: PRSummary.OpenPRRequested
) -> None:
    # Already opens browser by default, but can add logging
    self.log(f"Opening PR: {event.url}")
```

---

## Composing Widgets in a Screen

```python
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen

from maverick.tui.widgets import (
    WorkflowProgress,
    AgentOutput,
    ReviewFindings,
    ValidationStatus,
    PRSummary,
)


class WorkflowScreen(Screen):
    """Main workflow visualization screen."""

    def compose(self) -> ComposeResult:
        with Horizontal():
            # Left panel: Progress and validation
            with Vertical(id="left-panel"):
                yield WorkflowProgress(id="progress")
                yield ValidationStatus(id="validation")

            # Center panel: Agent output
            yield AgentOutput(id="output")

            # Right panel: Review findings
            yield ReviewFindings(id="findings")

        # Bottom: PR summary
        yield PRSummary(id="pr-summary")
```

---

## CSS Styling Reference

Widgets use CSS classes for status styling. Add these to your TCSS:

```css
/* Workflow stages */
.stage-pending { color: $text-muted; }
.stage-active { color: $accent; text-style: bold; }
.stage-completed { color: $success; }
.stage-failed { color: $error; }

/* Validation steps */
.validation-passed { color: $success; }
.validation-failed { color: $error; }
.validation-running { color: $accent; }
.validation-pending { color: $text-muted; }

/* Finding severity */
.severity-error { color: $error; text-style: bold; }
.severity-warning { color: $warning; }
.severity-suggestion { color: $info; }

/* Selection */
.--selected { background: $accent-muted; }

/* Empty states */
.empty-state { color: $text-muted; text-align: center; padding: 2; }

/* Loading states */
.loading { color: $text-muted; }
```

---

## Testing Widgets

```python
import pytest
from textual.app import App

from maverick.tui.widgets import WorkflowProgress
from maverick.tui.models import WorkflowStage, StageStatus


class TestApp(App):
    def compose(self):
        yield WorkflowProgress(id="progress")


@pytest.mark.asyncio
async def test_workflow_progress_displays_stages():
    """Test that stages are displayed correctly."""
    async with TestApp().run_test() as pilot:
        progress = pilot.app.query_one("#progress", WorkflowProgress)

        stages = [
            WorkflowStage(name="setup", display_name="Setup", status=StageStatus.PENDING),
            WorkflowStage(name="build", display_name="Build", status=StageStatus.PENDING),
        ]
        progress.update_stages(stages)

        # Verify stages are displayed
        assert progress.stage_count == 2


@pytest.mark.asyncio
async def test_workflow_progress_status_update():
    """Test that status updates are reflected."""
    async with TestApp().run_test() as pilot:
        progress = pilot.app.query_one("#progress", WorkflowProgress)

        stages = [WorkflowStage(name="setup", display_name="Setup", status=StageStatus.PENDING)]
        progress.update_stages(stages)

        # Update status
        progress.update_stage_status("setup", StageStatus.COMPLETED)

        # Verify status changed
        assert progress.get_stage("setup").status == StageStatus.COMPLETED
```

---

## Common Patterns

### Reactive Updates from Workflow

```python
async def run_workflow(self):
    """Run workflow and update widgets reactively."""
    progress = self.query_one(WorkflowProgress)
    output = self.query_one(AgentOutput)

    async for event in self.workflow.execute():
        match event:
            case FlyStageStarted(stage=stage):
                progress.update_stage_status(stage, StageStatus.ACTIVE)

            case FlyStageCompleted(stage=stage):
                progress.update_stage_status(stage, StageStatus.COMPLETED)

            case AgentMessageEvent(message=msg):
                output.add_message(msg)

            case ValidationResult(steps=steps):
                validation.update_steps(steps)
```

### Empty State Handling

Each widget handles empty state automatically:

```python
# WorkflowProgress with no stages shows: "No workflow stages"
# AgentOutput with no messages shows: "No agent output yet"
# ReviewFindings with no findings shows: "No review findings. All clear!"
# ValidationStatus with no steps shows: "No validation steps"
# PRSummary with no PR shows: "No pull request"
```

### Loading State Handling

```python
# Set loading before async operations
progress.set_loading(True)
validation.set_loading(True)
pr_summary.set_loading(True)

# Clear loading after data arrives
progress.update_stages(stages)  # Clears loading automatically
validation.update_steps(steps)  # Clears loading automatically
pr_summary.update_pr(pr)  # Clears loading automatically
```
