# Contributing to Maverick

Thank you for contributing to Maverick! This guide explains the project architecture, how to set up your development environment, and how to extend the system.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Architecture Overview](#architecture-overview)
- [Key Concepts](#key-concepts)
- [Creating Custom Agents](#creating-custom-agents)
- [Creating Custom Workflows](#creating-custom-workflows)
- [Testing Guidelines](#testing-guidelines)
- [Code Style](#code-style)
- [Pull Request Process](#pull-request-process)

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Git
- GitHub CLI (`gh`)
- Claude API key (set `ANTHROPIC_API_KEY` environment variable)
- [uv](https://docs.astral.sh/uv/) - Fast Python package and project manager (recommended)

### Quick Setup

We use [uv](https://docs.astral.sh/uv/) for dependency management, providing faster installs and reproducible environments via `uv.lock`.

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/get2knowio/maverick.git
cd maverick

# Install all dependencies (uses uv.lock for reproducibility)
uv sync --group dev

# Verify installation
uv run maverick --version

# Run tests
uv run pytest

# Run linting
uv run ruff check .
uv run ruff format --check .

# Run type checking
uv run mypy src/maverick
```

#### Using pip (Alternative)

```bash
# Clone the repository
git clone https://github.com/get2knowio/maverick.git
cd maverick

# Install with pip
pip install -e ".[dev]"

# Verify installation
maverick --version
```

## Development Setup

### Environment Configuration

1. **API Keys**: Set your Claude API key:
   ```bash
   export ANTHROPIC_API_KEY=your-api-key-here
   ```

2. **GitHub Authentication**: Ensure GitHub CLI is authenticated:
   ```bash
   gh auth status
   gh auth login  # if not authenticated
   ```

3. **Project Configuration**: Initialize a local config file:
   ```bash
   maverick config init
   # Edit maverick.yaml as needed
   ```

### Running Locally

```bash
# Run in development mode (using uv)
uv run maverick --help

# Run specific commands
uv run maverick fly my-branch --dry-run
uv run maverick status

# Run with verbose logging
uv run maverick -vv fly my-branch

# Run TUI in development
uv run python -m maverick.tui.app  # if TUI entry point exists
```

### Development Workflow

1. Create a feature branch from `main`
2. Make your changes following the code style guidelines
3. Add tests for new functionality
4. Run tests and linting locally
5. Commit with clear, descriptive messages
6. Open a pull request

## Architecture Overview

Maverick follows a layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│  CLI/TUI Layer (User Interface)                         │
│  - Click commands (main.py)                             │
│  - Textual TUI (tui/)                                   │
│  - User input validation                                │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Workflow Layer (Orchestration)                         │
│  - FlyWorkflow, RefuelWorkflow (workflows/)             │
│  - DSL-based workflow execution (dsl/)                  │
│  - State management and sequencing                      │
│  - Progress reporting as async generators              │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Agent Layer (AI Decision Making)                       │
│  - MaverickAgent base class (agents/base.py)            │
│  - Concrete agents (CodeReviewerAgent, etc.)            │
│  - Claude Agent SDK integration                         │
│  - System prompts and tool selection                    │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Tool Layer (External Integration)                      │
│  - MCP tools (tools/)                                   │
│  - GitHub operations, git commands                      │
│  - Validation runners, notifications                    │
└─────────────────────────────────────────────────────────┘
```

### Directory Structure

```
src/maverick/
├── __init__.py          # Version info, public API
├── main.py              # CLI entry point (Click)
├── config.py            # Pydantic configuration models
├── exceptions.py        # Exception hierarchy
│
├── agents/              # AI agent implementations
│   ├── base.py          # MaverickAgent ABC
│   ├── code_reviewer.py # Code review agent
│   ├── implementer.py   # Task implementation agent
│   └── issue_fixer.py   # Issue fixing agent
│
├── workflows/           # Workflow orchestration
│   ├── fly.py           # FlyWorkflow (spec-based dev)
│   └── refuel.py        # RefuelWorkflow (tech debt)
│
├── dsl/                 # Workflow DSL
│   ├── events.py        # Event types
│   ├── executor.py      # DSL execution engine
│   ├── serialization/   # YAML workflow parsing
│   └── visualization/   # Workflow diagrams
│
├── tools/               # MCP tool definitions
│   ├── github.py        # GitHub API tools
│   ├── git.py           # Git operations
│   └── validation.py    # Code validation tools
│
├── hooks/               # Agent safety/logging hooks
│   └── safety.py        # Rate limiting, cost tracking
│
├── tui/                 # Textual UI components
│   ├── app.py           # Main TUI application
│   ├── screens/         # Screen definitions
│   └── widgets/         # Reusable UI widgets
│
├── models/              # Pydantic data models
│   ├── review.py        # Review result models
│   ├── implementation.py # Implementation models
│   └── validation.py    # Validation models
│
├── runners/             # Command execution
│   ├── command.py       # Generic command runner
│   ├── git.py           # Git command wrapper
│   └── github.py        # GitHub CLI wrapper
│
└── utils/               # Shared utilities
    ├── git_operations.py # Git helpers
    ├── task_parser.py    # Task markdown parsing
    └── context.py        # Context building
```

## Key Concepts

### Agents

Agents are autonomous AI-powered components that know **HOW** to perform specific tasks. They encapsulate:

- **System Prompts**: Instructions that define the agent's expertise and behavior
- **Tool Selection**: Which MCP tools the agent can use (least privilege principle)
- **Claude SDK Integration**: Stateful multi-turn interactions or one-shot queries
- **Output Structuring**: Converting raw AI responses into typed results

**Base Class**: All agents inherit from `MaverickAgent` (abstract base class)

```python
from maverick.agents.base import MaverickAgent
from maverick.agents.context import AgentContext

class MyAgent(MaverickAgent):
    """Custom agent for specific task."""
    
    async def execute(self, context: AgentContext) -> MyResult:
        """Execute the agent's task.
        
        Args:
            context: Agent execution context with config, branch, etc.
            
        Returns:
            MyResult: Structured result object
        """
        # Implementation here
        pass
```

### Workflows

Workflows orchestrate **WHAT** tasks to do and **WHEN** to do them. They:

- **Sequence Operations**: Define the order of agent executions
- **Manage State**: Track progress and handle partial failures
- **Yield Progress**: Emit events as async generators for real-time UI updates
- **Handle Errors**: Implement retry logic and graceful degradation

**Key Workflows**:
- `FlyWorkflow`: Complete spec-based feature development
- `RefuelWorkflow`: Automated tech-debt resolution

```python
from maverick.workflows.base import Workflow, WorkflowInputs, WorkflowResult

async def my_workflow(inputs: MyInputs) -> AsyncGenerator[Event, None]:
    """Custom workflow implementation."""
    yield WorkflowStarted(...)
    
    # Execute agents
    agent_result = await my_agent.execute(context)
    yield AgentCompleted(...)
    
    # Final result
    yield WorkflowCompleted(success=True, ...)
```

### MCP Tools

Tools wrap external systems and provide a safe, structured interface for agents:

- **GitHub Operations**: PR creation, issue management, repository queries
- **Git Commands**: Branch management, commits, diffs
- **Validation**: Code formatting, linting, testing
- **Notifications**: Push notifications via ntfy

Tools follow the Model Context Protocol (MCP) specification and are defined with the `@tool` decorator:

```python
from claude_agent_sdk import tool

@tool
async def my_custom_tool(param: str) -> str:
    """Tool description for the AI.
    
    Args:
        param: Parameter description
        
    Returns:
        Result description
    """
    # Implementation
    return result
```

### Workflow DSL

The DSL (Domain-Specific Language) allows defining workflows in YAML:

```yaml
name: my-workflow
version: 1.0.0
description: Custom workflow example

inputs:
  branch:
    type: string
    required: true
    description: Target branch name

steps:
  - name: validate-branch
    type: python
    code: |
      if not inputs["branch"].startswith("feature/"):
          raise ValueError("Branch must start with 'feature/'")
  
  - name: run-tests
    type: agent
    agent: test-runner
    inputs:
      branch: ${{ inputs.branch }}
```

### Configuration

Configuration follows a layered approach with Pydantic models:

1. **Defaults**: Built-in sensible defaults
2. **User Config**: `~/.config/maverick/config.yaml`
3. **Project Config**: `./maverick.yaml`
4. **CLI Arguments**: Highest precedence

```python
from maverick.config import MaverickConfig, load_config

# Load merged configuration
config = load_config()

# Access config values (type-safe)
max_tokens = config.model.max_tokens
timeout = config.validation.timeout_seconds
```

### Async-First Design

Everything in Maverick is async to support:

- **Concurrent Agent Execution**: Run multiple agents in parallel
- **Responsive TUI**: Update UI during long-running operations
- **Efficient I/O**: Non-blocking external API calls

```python
import asyncio

# Async functions use await
result = await agent.execute(context)

# Async generators yield values
async for event in workflow.execute(inputs):
    print(f"Event: {event}")

# Parallel execution with asyncio.gather
results = await asyncio.gather(
    agent1.execute(ctx1),
    agent2.execute(ctx2),
    agent3.execute(ctx3),
)
```

## Creating Custom Agents

### Step 1: Define Your Agent Class

Create a new file in `src/maverick/agents/`:

```python
from __future__ import annotations

from maverick.agents.base import MaverickAgent
from maverick.agents.context import AgentContext
from maverick.models.custom import CustomResult  # Define your result model
from claude_agent_sdk import ClaudeSDKClient

class MyCustomAgent(MaverickAgent):
    """Agent that performs a specific task.
    
    This agent uses Claude to analyze code and suggest improvements
    based on project-specific conventions.
    """
    
    def __init__(self) -> None:
        """Initialize the agent."""
        super().__init__()
        self._client: ClaudeSDKClient | None = None
    
    async def execute(self, context: AgentContext) -> CustomResult:
        """Execute the agent's task.
        
        Args:
            context: Execution context with branch, config, etc.
            
        Returns:
            CustomResult with findings and suggestions.
            
        Raises:
            AgentError: If execution fails.
        """
        # Build system prompt
        system_prompt = self._build_system_prompt(context)
        
        # Create Claude SDK client with allowed tools
        self._client = ClaudeSDKClient(
            model=context.config.model.model_id,
            max_tokens=context.config.model.max_tokens,
            system=system_prompt,
            allowed_tools=["read_file", "search_code"],  # Least privilege
        )
        
        # Execute with Claude
        response = await self._client.run(
            "Analyze the codebase for improvements"
        )
        
        # Parse and structure the response
        return self._parse_response(response)
    
    def _build_system_prompt(self, context: AgentContext) -> str:
        """Build the system prompt for Claude."""
        return f"""You are an expert code analyzer.
        
        Repository: {context.config.github.repo}
        Branch: {context.branch}
        
        Analyze code and suggest improvements following the project's
        conventions in CLAUDE.md.
        """
    
    def _parse_response(self, response: str) -> CustomResult:
        """Parse Claude's response into structured result."""
        # Implementation to extract findings
        return CustomResult(
            findings=[],
            summary="Analysis complete",
            success=True,
        )
```

### Step 2: Define Result Model

Create result models in `src/maverick/models/`:

```python
from __future__ import annotations

from pydantic import BaseModel, Field

class CustomFinding(BaseModel):
    """A single finding from the agent."""
    
    file: str = Field(..., description="File path")
    line: int | None = Field(None, description="Line number")
    message: str = Field(..., description="Finding message")
    suggestion: str | None = Field(None, description="Suggested fix")

class CustomResult(BaseModel):
    """Result from MyCustomAgent."""
    
    findings: list[CustomFinding] = Field(default_factory=list)
    summary: str = Field(..., description="Summary of analysis")
    success: bool = Field(..., description="Whether execution succeeded")
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### Step 3: Add Tests

Create tests in `tests/agents/`:

```python
import pytest
from maverick.agents.custom import MyCustomAgent
from maverick.agents.context import AgentContext
from maverick.config import MaverickConfig

@pytest.mark.asyncio
async def test_custom_agent_success():
    """Test successful agent execution."""
    agent = MyCustomAgent()
    context = AgentContext(
        branch="feature/test",
        cwd=Path.cwd(),
        config=MaverickConfig(),  # Use defaults
    )
    
    result = await agent.execute(context)
    
    assert result.success
    assert isinstance(result.findings, list)
    assert result.summary
```

## Creating Custom Workflows

### Option 1: Python Workflow

Create a new workflow in `src/maverick/workflows/`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncGenerator

from pydantic import BaseModel, Field

from maverick.workflows.base import WorkflowEvent

@dataclass(frozen=True)
class MyWorkflowStarted(WorkflowEvent):
    """Workflow started event."""
    total_steps: int

@dataclass(frozen=True)
class MyWorkflowCompleted(WorkflowEvent):
    """Workflow completed event."""
    success: bool
    summary: str

class MyWorkflowInputs(BaseModel):
    """Inputs for MyWorkflow."""
    
    param1: str = Field(..., description="First parameter")
    param2: int = Field(default=10, description="Second parameter")

class MyWorkflow:
    """Custom workflow implementation."""
    
    async def execute(
        self, inputs: MyWorkflowInputs
    ) -> AsyncGenerator[WorkflowEvent, None]:
        """Execute the workflow.
        
        Args:
            inputs: Workflow inputs
            
        Yields:
            WorkflowEvent instances for progress tracking
        """
        yield MyWorkflowStarted(total_steps=3)
        
        # Step 1: Do something
        yield StepStarted(step_name="step-1")
        # ... implementation ...
        yield StepCompleted(step_name="step-1", success=True)
        
        # Step 2: Do something else
        yield StepStarted(step_name="step-2")
        # ... implementation ...
        yield StepCompleted(step_name="step-2", success=True)
        
        # Final result
        yield MyWorkflowCompleted(
            success=True,
            summary="Workflow completed successfully"
        )
```

### Option 2: DSL-Based Workflow

Create a YAML workflow file in `.maverick/workflows/`:

```yaml
name: my-workflow
version: 1.0.0
description: Example custom workflow

inputs:
  branch:
    type: string
    required: true
    description: Branch to process
  
  dry_run:
    type: boolean
    required: false
    default: false
    description: Run without making changes

steps:
  - name: validate-inputs
    type: python
    code: |
      if not inputs["branch"]:
          raise ValueError("Branch is required")
      print(f"Processing branch: {inputs['branch']}")
  
  - name: analyze-code
    type: agent
    agent: code-analyzer
    inputs:
      branch: ${{ inputs.branch }}
    when: ${{ inputs.dry_run == false }}
  
  - name: create-report
    type: generate
    template: report-template
    inputs:
      findings: ${{ steps.analyze-code.output.findings }}
```

Run with:

```bash
maverick workflow run my-workflow -i branch=feature/test
```

## Testing Guidelines

Maverick follows a test-first approach with comprehensive test coverage.

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/agents/test_code_reviewer.py

# Run with coverage
uv run pytest --cov=maverick --cov-report=html

# Run only async tests
uv run pytest -m asyncio

# Run with verbose output
uv run pytest -vv

# Run fast tests only (skip slow integration tests)
uv run pytest -m "not slow"
```

### Writing Tests

#### Unit Tests for Agents

```python
import pytest
from pathlib import Path
from maverick.agents.code_reviewer import CodeReviewerAgent
from maverick.agents.context import AgentContext
from maverick.config import MaverickConfig

@pytest.fixture
def agent_context():
    """Create a test agent context."""
    return AgentContext(
        branch="test-branch",
        cwd=Path.cwd(),
        config=MaverickConfig(),
    )

@pytest.mark.asyncio
async def test_code_reviewer_success(agent_context, mocker):
    """Test successful code review execution."""
    # Mock Claude SDK
    mock_client = mocker.patch("maverick.agents.code_reviewer.ClaudeSDKClient")
    mock_client.return_value.run = mocker.AsyncMock(
        return_value="Review complete. No issues found."
    )
    
    agent = CodeReviewerAgent()
    result = await agent.execute(agent_context)
    
    assert result.success
    assert result.files_reviewed >= 0
    assert result.summary
```

#### Integration Tests for Workflows

```python
@pytest.mark.asyncio
@pytest.mark.slow
async def test_fly_workflow_execution(tmp_path):
    """Test FlyWorkflow execution end-to-end."""
    # Setup test repository
    repo_path = tmp_path / "test-repo"
    repo_path.mkdir()
    # ... initialize git repo, create tasks.md ...
    
    workflow = FlyWorkflow()
    inputs = FlyInputs(
        branch_name="test-branch",
        task_file=repo_path / "tasks.md",
    )
    
    # Collect events
    events = []
    async for event in workflow.execute(inputs):
        events.append(event)
    
    # Verify workflow completed
    assert any(isinstance(e, FlyCompleted) for e in events)
```

#### TUI Tests

```python
from textual.pilot import Pilot
from maverick.tui.app import MaverickApp

@pytest.mark.asyncio
async def test_tui_home_screen():
    """Test TUI home screen rendering."""
    app = MaverickApp()
    
    async with app.run_test() as pilot:
        # Verify initial screen
        assert app.screen.title == "Maverick"
        
        # Simulate user input
        await pilot.press("q")  # Quit
        
        # Verify app closed
        assert not app.is_running
```

### Test Organization

```
tests/
├── agents/              # Agent tests
│   ├── test_code_reviewer.py
│   ├── test_implementer.py
│   └── test_issue_fixer.py
├── workflows/           # Workflow tests
│   ├── test_fly.py
│   └── test_refuel.py
├── tools/               # Tool tests
│   ├── test_github.py
│   └── test_git.py
├── tui/                 # TUI tests
│   ├── test_app.py
│   └── test_widgets.py
├── conftest.py          # Shared fixtures
└── fixtures/            # Test data files
```

### Mocking External Dependencies

Always mock external dependencies to keep tests fast and deterministic:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_github_cli(mocker):
    """Mock GitHub CLI commands."""
    return mocker.patch("subprocess.run")

@pytest.fixture
def mock_claude_sdk(mocker):
    """Mock Claude Agent SDK client."""
    mock = mocker.patch("claude_agent_sdk.ClaudeSDKClient")
    mock.return_value.run = AsyncMock(return_value="Success")
    return mock

@pytest.mark.asyncio
async def test_with_mocks(mock_github_cli, mock_claude_sdk):
    """Test using mocked dependencies."""
    # Your test here
    pass
```

## Code Style

Maverick follows strict code style guidelines enforced by automated tools.

### Style Rules

| Aspect | Convention | Example |
|--------|-----------|---------|
| Line Length | 88 characters (Black compatible) | - |
| Imports | Sorted with isort (groups: stdlib, third-party, first-party) | - |
| Quotes | Double quotes for strings | `"hello world"` |
| Type Hints | Required for all public functions | `def foo(x: int) -> str:` |
| Docstrings | Google style, required for public APIs | See below |
| Naming | See naming conventions table | - |

### Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Classes | PascalCase | `CodeReviewerAgent`, `FlyWorkflow` |
| Functions | snake_case | `execute_review`, `create_pr` |
| Constants | SCREAMING_SNAKE_CASE | `MAX_RETRIES`, `DEFAULT_TIMEOUT` |
| Private | Leading underscore | `_build_prompt`, `_validate` |
| Type Aliases | PascalCase | `AgentResult`, `WorkflowEvent` |

### Docstring Format

Use Google-style docstrings for all public classes and functions:

```python
def execute_task(
    task_id: str,
    config: TaskConfig,
    timeout: int = 300,
) -> TaskResult:
    """Execute a single task with the given configuration.
    
    This function orchestrates the execution of a task by:
    1. Validating the task ID exists
    2. Loading task configuration
    3. Running the task with the specified agent
    4. Collecting and structuring results
    
    Args:
        task_id: Unique identifier for the task to execute. Must be
            a valid task ID from the project's task registry.
        config: Configuration object containing execution parameters
            such as timeout, retry policy, and agent selection.
        timeout: Maximum execution time in seconds. Defaults to 300.
            If exceeded, the task is terminated and marked as failed.
    
    Returns:
        TaskResult containing:
            - success: Whether the task completed successfully
            - output: Task output data
            - duration: Execution time in milliseconds
            - error: Error message if failed (None otherwise)
    
    Raises:
        TaskNotFoundError: If the task_id does not exist in the registry.
        ExecutionError: If the task fails during execution.
        TimeoutError: If execution exceeds the timeout limit.
    
    Example:
        >>> config = TaskConfig(agent="implementer", retry=3)
        >>> result = execute_task("TASK-123", config, timeout=600)
        >>> if result.success:
        ...     print(f"Task completed in {result.duration}ms")
    """
    # Implementation here
    pass
```

### Import Organization

Organize imports in this order:

```python
# Future imports (first)
from __future__ import annotations

# Standard library imports
import asyncio
import logging
from pathlib import Path
from typing import Any, AsyncGenerator

# Third-party imports
import click
from pydantic import BaseModel, Field
from claude_agent_sdk import ClaudeSDKClient

# First-party imports (maverick modules)
from maverick.agents.base import MaverickAgent
from maverick.config import MaverickConfig
from maverick.exceptions import AgentError
```

### Type Hints

Complete type hints are mandatory:

```python
from __future__ import annotations

from typing import Any, AsyncGenerator, Protocol

# Good: Complete type hints
async def process_items(
    items: list[str],
    config: dict[str, Any],
) -> AsyncGenerator[str, None]:
    """Process items asynchronously."""
    for item in items:
        yield item

# Good: Use Protocol for interfaces
class AgentProtocol(Protocol):
    """Protocol for agent implementations."""
    
    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute the agent."""
        ...

# Good: Use TypeAlias for complex types
EventStream: TypeAlias = AsyncGenerator[WorkflowEvent, None]
```

### Code Quality Tools

Run these before committing:

```bash
# Format code
uv run ruff format .

# Check linting
uv run ruff check .

# Auto-fix linting issues
uv run ruff check --fix .

# Type checking
uv run mypy src/maverick

# Run all checks
uv run ruff format . && uv run ruff check --fix . && uv run mypy src/maverick && uv run pytest
```

### Pre-commit Hook (Optional)

Add a `.git/hooks/pre-commit` script:

```bash
#!/bin/bash
set -e

echo "Running pre-commit checks..."

# Format
echo "→ Formatting code..."
uv run ruff format .

# Lint
echo "→ Linting..."
uv run ruff check --fix .

# Type check
echo "→ Type checking..."
uv run mypy src/maverick

# Test
echo "→ Running tests..."
uv run pytest -x --tb=short

echo "✓ All checks passed!"
```

Make it executable:
```bash
chmod +x .git/hooks/pre-commit
```

## Pull Request Process

### Before Opening a PR

1. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make focused changes**: Keep PRs small and focused on a single feature/fix

3. **Add tests**: All new code must have tests

4. **Run all checks**:
   ```bash
   uv run ruff format . && uv run ruff check --fix . && uv run mypy src/maverick && uv run pytest
   ```

5. **Update documentation**: If adding features, update README.md and CONTRIBUTING.md

6. **Commit with clear messages**:
   ```bash
   git commit -m "Add code review agent with retry logic"
   ```

### PR Guidelines

- **Title**: Clear, descriptive summary (e.g., "Add parallel task execution to FlyWorkflow")
- **Description**: Explain what and why (not how - that's in the code)
- **Link issues**: Reference related issues with "Fixes #123" or "Relates to #456"
- **Request review**: Tag relevant reviewers

### PR Description Template

```markdown
## Summary
Brief description of changes.

## Motivation
Why is this change needed? What problem does it solve?

## Changes
- Added X feature
- Fixed Y bug
- Refactored Z component

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing completed

## Checklist
- [ ] Code follows style guidelines
- [ ] All tests pass
- [ ] Documentation updated
- [ ] No new warnings from linter/type checker
```

### Review Process

1. **Automated checks**: CI runs tests, linting, type checking
2. **Code review**: At least one approval required
3. **Address feedback**: Make requested changes
4. **Squash and merge**: Keep main branch history clean

### Constitution Compliance

All PRs are reviewed for compliance with [.specify/memory/constitution.md](.specify/memory/constitution.md).

Key points:
- ✅ Async-first design
- ✅ Proper separation of concerns (Agents/Workflows/TUI/Tools)
- ✅ Dependency injection
- ✅ Graceful error handling with retries
- ✅ Complete type hints
- ✅ Tests for all new code

## Getting Help

- **Questions**: Open a discussion on GitHub
- **Bugs**: Open an issue with reproduction steps
- **Features**: Open an issue describing the use case
- **Architecture**: Read [.specify/memory/constitution.md](.specify/memory/constitution.md)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
