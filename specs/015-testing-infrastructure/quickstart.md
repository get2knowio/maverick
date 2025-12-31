# Quickstart: Testing Infrastructure

**Feature Branch**: `015-testing-infrastructure`
**Date**: 2025-12-17

## Overview

This guide provides quick examples for writing tests using Maverick's testing infrastructure.

---

## Running Tests

### Full Test Suite

```bash
# Run all tests with coverage
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/unit/agents/test_base.py

# Run tests matching pattern
pytest -k "test_agent"
```

### By Test Type

```bash
# Unit tests only
pytest tests/unit/

# Integration tests only
pytest tests/integration/

# TUI tests only
pytest tests/tui/
```

### Coverage Report

```bash
# Terminal report with missing lines
pytest --cov=maverick --cov-report=term-missing

# HTML report
pytest --cov=maverick --cov-report=html
open htmlcov/index.html
```

---

## Writing Agent Tests

### Basic Agent Test

```python
"""Test example for agent functionality."""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tests.fixtures.agents import MockSDKClient, MockMessage


@pytest.mark.asyncio
async def test_agent_returns_success(mock_sdk_client, mock_text_message, mock_result_message):
    """Test agent completes successfully with mocked SDK."""
    from maverick.agents.code_reviewer import CodeReviewerAgent

    # Setup mock responses
    mock_sdk_client.queue_response([
        mock_text_message("Review complete. No issues found."),
        mock_result_message(input_tokens=150, output_tokens=200),
    ])

    # Create agent
    agent = CodeReviewerAgent()

    # Execute with mocked SDK
    with patch.dict("sys.modules", {"claude_agent_sdk": mock_sdk_module()}):
        context = create_test_context(branch="feature-123")
        result = await agent.execute(context)

    # Verify
    assert result.success
    assert "No issues" in result.output
    assert mock_sdk_client.query_calls[0]  # Prompt was sent
```

### Testing Error Handling

```python
@pytest.mark.asyncio
async def test_agent_handles_streaming_error(mock_sdk_client, mock_text_message):
    """Test agent handles mid-stream failures gracefully."""
    from maverick.agents.base import MaverickAgent
    from maverick.exceptions import StreamingError

    # Queue partial response then error
    mock_sdk_client.queue_response([mock_text_message("Partial")])
    mock_sdk_client.queue_error(ValueError("Connection lost"))

    agent = create_test_agent()

    with pytest.raises(StreamingError) as exc_info:
        async for _ in agent.query("Test prompt"):
            pass

    assert len(exc_info.value.partial_messages) == 1
```

---

## Writing Workflow Tests

### Basic Workflow Test

```python
"""Test example for workflow functionality."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from maverick.workflows.validation import ValidationWorkflow
from maverick.models.validation import ValidationStage, StageStatus


@pytest.mark.asyncio
async def test_workflow_executes_stages_in_order():
    """Test workflow runs stages sequentially."""
    stages = [
        ValidationStage(name="lint", command=["ruff", "check", "."], fixable=True),
        ValidationStage(name="test", command=["pytest"], fixable=False),
    ]

    workflow = ValidationWorkflow(stages=stages)

    # Collect progress events
    events = []
    async for event in workflow.run():
        events.append(event)

    result = workflow.get_result()

    assert result.success
    assert len(result.stage_results) == 2
    assert result.stage_results[0].name == "lint"
    assert result.stage_results[1].name == "test"
```

### Using AsyncGeneratorCapture

```python
from tests.utils.async_helpers import AsyncGeneratorCapture

@pytest.mark.asyncio
async def test_workflow_yields_expected_events():
    """Test workflow emits correct progress events."""
    workflow = create_test_workflow()

    capture = await AsyncGeneratorCapture.capture(workflow.run())

    assert capture.completed
    assert len(capture) >= 2  # At least started and completed

    # Find specific events
    started_events = [e for e in capture if hasattr(e, 'started_at')]
    assert len(started_events) == 1
```

---

## Writing TUI Tests

### Screen Test with Pilot

```python
"""Test example for TUI screen."""
from __future__ import annotations

import pytest
from textual.app import App

from maverick.tui.screens.home import HomeScreen


class HomeScreenTestApp(App):
    """Test app for HomeScreen."""

    def compose(self):
        yield HomeScreen()


@pytest.mark.asyncio
async def test_home_screen_shows_workflows():
    """Test home screen displays workflow buttons."""
    async with HomeScreenTestApp().run_test() as pilot:
        screen = pilot.app.screen

        # Verify workflow buttons exist
        fly_btn = screen.query_one("#fly-btn")
        refuel_btn = screen.query_one("#refuel-btn")

        assert fly_btn is not None
        assert refuel_btn is not None


@pytest.mark.asyncio
async def test_button_click_navigates():
    """Test clicking fly button navigates to fly screen."""
    async with HomeScreenTestApp().run_test() as pilot:
        # Click fly button
        await pilot.click("#fly-btn")
        await pilot.pause()

        # Verify navigation (check screen type or title)
        assert pilot.app.screen.__class__.__name__ == "FlyScreen"
```

### Widget Test

```python
from maverick.tui.widgets.workflow_list import WorkflowList


@pytest.mark.asyncio
async def test_workflow_list_updates_on_data_change():
    """Test widget updates when data changes."""
    async with WorkflowListTestApp().run_test() as pilot:
        widget = pilot.app.query_one(WorkflowList)

        # Set data
        workflows = [
            {"branch_name": "feature-1", "status": "completed"},
            {"branch_name": "feature-2", "status": "running"},
        ]
        widget.set_workflows(workflows)
        await pilot.pause()

        # Verify rendering
        items = widget.query(".workflow-item")
        assert len(items) == 2
```

---

## Writing CLI Tests

### Basic Command Test

```python
"""Test example for CLI commands."""
from __future__ import annotations

import pytest
from click.testing import CliRunner

from maverick.main import cli


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


def test_version_command(cli_runner: CliRunner):
    """Test --version outputs version info."""
    result = cli_runner.invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert "maverick" in result.output.lower()


def test_help_command(cli_runner: CliRunner):
    """Test --help shows all commands."""
    result = cli_runner.invoke(cli, ["--help"])

    assert result.exit_code == 0
    assert "fly" in result.output
    assert "refuel" in result.output
```

### Async Command Test

```python
from unittest.mock import AsyncMock, patch


def test_fly_command_executes_workflow(cli_runner, temp_dir, monkeypatch):
    """Test fly command runs FlyWorkflow."""
    monkeypatch.chdir(temp_dir)

    with patch("maverick.main.FlyWorkflow") as mock_workflow_cls:
        mock_workflow = AsyncMock()
        mock_workflow_cls.return_value = mock_workflow
        mock_workflow.execute.return_value = MagicMock(success=True, summary="Done")

        result = cli_runner.invoke(cli, ["fly", "feature-branch"])

        assert result.exit_code == 0
        mock_workflow.execute.assert_called_once()
```

---

## Using Test Fixtures

### Available Fixtures

| Fixture | Source | Purpose |
|---------|--------|---------|
| `mock_sdk_client` | `tests/fixtures/agents.py` | Mock Claude SDK client |
| `mock_text_message` | `tests/fixtures/agents.py` | Factory for text messages |
| `mock_result_message` | `tests/fixtures/agents.py` | Factory for result messages |
| `mock_github_cli` | `tests/fixtures/github.py` | Mock GitHub CLI |
| `sample_config` | `tests/fixtures/config.py` | Sample MaverickConfig |
| `temp_dir` | `tests/conftest.py` | Temporary directory |
| `clean_env` | `tests/conftest.py` | Clean environment |
| `cli_runner` | `tests/conftest.py` | Click CliRunner |

### Importing Fixtures

Fixtures in `tests/conftest.py` are auto-available. For fixtures in `tests/fixtures/`:

```python
# In your test file
from tests.fixtures.agents import mock_sdk_client, mock_text_message

# Or use pytest_plugins in conftest.py
pytest_plugins = [
    "tests.fixtures.agents",
    "tests.fixtures.config",
    "tests.fixtures.github",
]
```

---

## Test Organization

### Directory Structure

```
tests/
├── conftest.py              # Root fixtures
├── fixtures/                # Shared fixture modules
│   ├── agents.py
│   ├── config.py
│   ├── github.py
│   └── responses.py
├── utils/                   # Test utilities
│   ├── async_helpers.py
│   ├── assertions.py
│   └── mcp.py
├── unit/                    # Unit tests
│   ├── agents/
│   ├── workflows/
│   ├── tools/
│   └── tui/
├── integration/             # Integration tests
│   ├── workflows/
│   └── cli/
└── tui/                     # TUI-specific tests
    └── screens/
```

### Naming Conventions

- Test files: `test_<module>.py`
- Test classes: `Test<ClassName>`
- Test functions: `test_<behavior>`
- Fixtures: `<entity>_fixture` or `mock_<entity>`

---

## CI Integration

Tests run automatically on:
- Push to `main` branch
- Pull request to `main` branch

CI checks:
1. Lint with ruff
2. Type check with mypy
3. Test with pytest (Python 3.10, 3.11, 3.12)
4. Coverage threshold: 80% minimum

### Running CI Locally

```bash
# Run the full CI check locally
ruff check src/ tests/
mypy src/
pytest --cov=maverick --cov-fail-under=80
```
