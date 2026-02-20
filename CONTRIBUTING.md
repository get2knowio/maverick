# Contributing to Maverick

Thank you for contributing to Maverick! This guide explains the project architecture, how to set up your development environment, and how to extend the system.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Architecture Overview](#architecture-overview)
- [Key Concepts](#key-concepts)
- [Creating Custom Agents](#creating-custom-agents)
- [Creating Custom Workflows](#creating-custom-workflows)
  - [Workflow Architecture Overview](#workflow-architecture-overview)
  - [Workflow Discovery Locations](#workflow-discovery-locations)
  - [Creating a YAML Workflow](#creating-a-yaml-workflow)
  - [Built-in Step Types](#built-in-step-types)
  - [Registering Components](#registering-components)
  - [Creating Reusable Fragments](#creating-reusable-fragments)
- [Adding New Step Types](#adding-new-step-types)
- [Testing Guidelines](#testing-guidelines)
- [Code Style](#code-style)
- [Pull Request Process](#pull-request-process)

## Getting Started

### Prerequisites

- Python 3.10 or higher
- Git
- GitHub CLI (`gh`)
- [Jujutsu](https://martinvonz.github.io/jj/) (`jj`) for VCS write operations
- [bd](https://beads.dev/) for bead/work-item management
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
│  CLI Layer (User Interface)                             │
│  - Click commands (cli/commands/)                       │
│  - User input validation                                │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Workflow Layer (Orchestration)                         │
│  - YAML workflows (library/workflows/)                  │
│  - DSL-based workflow execution (dsl/)                  │
│  - State management and sequencing                      │
│  - Progress reporting as async generators               │
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
├── agents/              # AI agent implementations
├── beads/               # Bead models, client, speckit integration
├── cli/                 # Click CLI commands
├── dsl/                 # Workflow DSL engine
├── exceptions/          # Custom exception hierarchy
├── git/                 # GitPython wrapper (read-only)
├── hooks/               # Safety and logging hooks
├── init/                # Project initialization
├── jj/                  # JjClient (Jujutsu wrapper)
├── library/             # Built-in workflows, actions, fragments
├── models/              # Pydantic/dataclass models
├── runners/             # Subprocess runners (CommandRunner, validation)
├── skills/              # Claude Code skills
├── tools/               # MCP tool definitions
├── utils/               # Shared utilities (github_client, secrets)
├── vcs/                 # VCS abstraction protocol
├── workflows/           # Workflow orchestration (legacy)
└── workspace/           # Hidden workspace lifecycle management
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

Maverick uses a YAML-based DSL for defining workflows. Workflows are executed by the `WorkflowFileExecutor` which resolves component references from registries.

```yaml
version: "1.0"
name: my-workflow
description: Custom workflow example

inputs:
  branch:
    type: string
    required: true
    description: Target branch name

  dry_run:
    type: boolean
    required: false
    default: false
    description: Preview mode without changes

steps:
  - name: validate-branch
    type: python
    action: validate_branch_name # Registered action
    kwargs:
      branch: ${{ inputs.branch }}

  - name: run-tests
    type: validate
    stages: [format, lint, test]
    retry: 2
    when: ${{ inputs.dry_run == false }}
```

**Key Components**:

- **WorkflowFile**: Pydantic schema for YAML parsing and validation
- **ComponentRegistry**: Resolves actions, agents, generators by name
- **Step Handlers**: Execute each step type (python, agent, validate, etc.)
- **Expression Engine**: Evaluates `${{ ... }}` expressions for dynamic values

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

Maverick supports YAML-based workflows that are declarative, shareable, and can be discovered from multiple locations. This is the **recommended approach** for defining reusable workflows.

### Workflow Architecture Overview

The workflow system consists of:

1. **WorkflowFile** (`maverick.dsl.serialization.schema`): Pydantic schema for YAML workflows
2. **WorkflowFileExecutor** (`maverick.dsl.serialization.executor`): Executes workflows
3. **ComponentRegistry** (`maverick.dsl.serialization.registry`): Resolves actions, agents, generators
4. **Step Handlers** (`maverick.dsl.serialization.executor.handlers`): Execute each step type
5. **Workflow Discovery** (`maverick.dsl.discovery`): Finds workflows from multiple locations

### Workflow Discovery Locations

Workflows are discovered from three locations (in override order):

| Priority    | Location                        | Purpose                    |
| ----------- | ------------------------------- | -------------------------- |
| 1 (highest) | `.maverick/workflows/`          | Project-specific workflows |
| 2           | `~/.config/maverick/workflows/` | User-defined workflows     |
| 3 (lowest)  | Built-in library                | Packaged with Maverick     |

**Override Behavior**: If the same workflow name exists in multiple locations, project overrides user, which overrides built-in.

### Creating a YAML Workflow

#### Step 1: Create the Workflow File

Create a YAML file in `.maverick/workflows/` (project) or `~/.config/maverick/workflows/` (user):

```yaml
# .maverick/workflows/my-workflow.yaml
version: "1.0"
name: my-workflow
description: Example custom workflow for feature development

# Input declarations with type, required/optional, defaults, and descriptions
inputs:
  branch_name:
    type: string
    required: true
    description: Feature branch name

  max_retries:
    type: integer
    required: false
    default: 3
    description: Maximum retry attempts for validation

  skip_tests:
    type: boolean
    required: false
    default: false
    description: Skip test execution

# Workflow steps execute in order
steps:
  # Python step: Execute a registered action
  - name: preflight-checks
    type: python
    action: run_preflight_checks
    kwargs:
      check_git: true
      check_github: true

  # Agent step: Invoke a registered AI agent
  - name: implement-feature
    type: agent
    agent: implementer
    context:
      branch: ${{ inputs.branch_name }}
      spec_dir: specs/${{ inputs.branch_name }}

  # Validate step: Run validation with retry loop
  - name: validate-code
    type: validate
    stages:
      - format
      - lint
      - typecheck
      - test
    retry: ${{ inputs.max_retries }}
    on_failure:
      name: auto-fix
      type: agent
      agent: validation_fixer

  # Conditional execution with 'when' clause
  - name: run-tests
    type: python
    action: run_test_suite
    when: ${{ inputs.skip_tests == false }}

  # Checkpoint for resumability
  - name: save-progress
    type: checkpoint
    checkpoint_id: after-validation
```

#### Step 2: Supported Input Types

```yaml
inputs:
  string_input:
    type: string # Text values
    required: true

  integer_input:
    type: integer # Whole numbers
    default: 10

  float_input:
    type: float # Decimal numbers
    default: 0.5

  boolean_input:
    type: boolean # true/false
    default: false

  object_input:
    type: object # dict[str, Any]
    default: {}

  array_input:
    type: array # list[Any]
    default: []
```

#### Step 3: Expression Syntax

Use `${{ ... }}` for dynamic values:

```yaml
steps:
  - name: example
    type: python
    action: my_action
    kwargs:
      # Reference workflow inputs
      branch: ${{ inputs.branch_name }}

      # Reference previous step outputs
      findings: ${{ steps.review.output.findings }}

      # Nested access
      count: ${{ steps.fetch.output.issues.length }}

      # Boolean expressions (for 'when' conditions)
      # when: ${{ inputs.skip_review == false }}
```

### Built-in Step Types

Maverick provides 8 built-in step types, each with a dedicated handler:

| Step Type     | Purpose                            | Handler Module        |
| ------------- | ---------------------------------- | --------------------- |
| `python`      | Execute registered Python actions  | `python_step.py`      |
| `agent`       | Invoke registered AI agents        | `agent_step.py`       |
| `generate`    | Generate text via generator agents | `generate_step.py`    |
| `validate`    | Run validation with retry logic    | `validate_step.py`    |
| `branch`      | Conditional branching              | `branch_step.py`      |
| `loop`        | Iteration with concurrency control | `loop_step.py`        |
| `subworkflow` | Invoke another workflow            | `subworkflow_step.py` |
| `checkpoint`  | Save state for resumability        | `checkpoint_step.py`  |

#### Python Step

Execute a registered Python action:

```yaml
- name: fetch-issue
  type: python
  action: fetch_github_issue # Must be registered in ActionRegistry
  args: [] # Positional arguments (optional)
  kwargs: # Keyword arguments
    issue_number: ${{ inputs.issue_number }}
  rollback: cleanup_action # Optional rollback on workflow failure
```

#### Agent Step

Invoke a registered AI agent:

```yaml
- name: review-code
  type: agent
  agent: code_reviewer # Must be registered in AgentRegistry
  context: # Static dict or context builder name
    files: ${{ steps.find-files.output }}
    branch: ${{ inputs.branch }}
  rollback: revert_changes # Optional rollback action
```

#### Validate Step

Run validation stages with automatic retry:

```yaml
- name: validate
  type: validate
  stages: # Explicit list or config key
    - format
    - lint
    - typecheck
    - test
  retry: 3 # Retry attempts (0 = no retry)
  on_failure: # Optional step to run before each retry
    name: auto-fix
    type: agent
    agent: validation_fixer
```

#### Branch Step

Conditional execution based on predicates:

```yaml
- name: choose-strategy
  type: branch
  options:
    - when: ${{ inputs.mode == 'fast' }}
      step:
        name: quick-validate
        type: validate
        stages: [format, lint]

    - when: ${{ inputs.mode == 'thorough' }}
      step:
        name: full-validate
        type: validate
        stages: [format, lint, typecheck, test]

    - when: ${{ true }} # Default/fallback branch
      step:
        name: standard-validate
        type: validate
        stages: [format, lint, test]
```

#### Loop Step

Iterate over items with concurrency control:

```yaml
- name: process-issues
  type: loop
  for_each: ${{ steps.fetch-issues.output.issues }}
  max_concurrency: 3 # 1=sequential, 0=unlimited, N=parallel limit
  steps:
    - name: fix-issue
      type: agent
      agent: issue_fixer
      context:
        issue: ${{ item }} # 'item' contains current iteration value
```

#### Subworkflow Step

Invoke another workflow as a step:

```yaml
- name: validate-with-fixes
  type: subworkflow
  workflow: validate-and-fix # Workflow name or file path
  inputs:
    stages: [format, lint, test]
    max_attempts: 5
```

#### Checkpoint Step

Mark state for workflow resumability:

```yaml
- name: after-implementation
  type: checkpoint
  checkpoint_id: implementation-complete # Optional, defaults to step name
```

### Registering Components

Workflows reference components by name. Register them in the appropriate registry:

#### Registering Actions

```python
# src/maverick/library/actions/my_actions.py
from maverick.dsl.serialization.registry import action_registry

@action_registry.register("fetch_github_issue")
async def fetch_github_issue(issue_number: int) -> dict:
    """Fetch issue details from GitHub.

    Args:
        issue_number: GitHub issue number

    Returns:
        Issue details dict with title, body, labels, etc.
    """
    # Implementation
    return {"title": "...", "body": "...", "labels": [...]}

# Or register directly
action_registry.register("my_action", my_function)
```

#### Registering Agents

```python
# src/maverick/library/agents/my_agents.py
from maverick.dsl.serialization.registry import agent_registry
from maverick.agents.base import MaverickAgent

@agent_registry.register("code_reviewer")
class CodeReviewerAgent(MaverickAgent):
    """Code review agent."""

    async def execute(self, context: dict) -> dict:
        # Implementation
        return {"findings": [...], "summary": "..."}
```

#### Registering Generators

```python
# src/maverick/library/generators/my_generators.py
from maverick.dsl.serialization.registry import generator_registry

@generator_registry.register("pr_body_generator")
class PRBodyGenerator:
    """Generate PR descriptions."""

    async def generate(self, context: dict) -> str:
        # Implementation
        return "## Summary\n..."
```

### Creating Reusable Fragments

Fragments are workflow snippets designed for reuse via `subworkflow` steps:

```yaml
# .maverick/workflows/my-fragment.yaml
version: "1.0"
name: my-fragment
description: Reusable validation-with-retry logic

inputs:
  stages:
    type: array
    required: false
    default: ["format", "lint", "test"]

  max_attempts:
    type: integer
    required: false
    default: 3

steps:
  - name: run-validation
    type: validate
    stages: ${{ inputs.stages }}
    retry: ${{ inputs.max_attempts }}
    on_failure:
      name: auto-fix
      type: agent
      agent: validation_fixer
```

Use in other workflows:

```yaml
steps:
  - name: validate-code
    type: subworkflow
    workflow: my-fragment
    inputs:
      stages: [format, lint, typecheck, test]
      max_attempts: 5
```

### Running Workflows

```bash
# Run a workflow with inputs
maverick workflow run my-workflow -i branch_name=feature/test

# Run built-in workflow
maverick workflow run feature -i branch_name=025-new-feature

# List available workflows
maverick workflow list

# Show workflow details
maverick workflow show my-workflow
```

## Adding New Step Types

To extend the DSL with a custom step type, follow these steps:

### Step 1: Define the Step Type

Add a new value to the `StepType` enum:

```python
# src/maverick/dsl/types.py
class StepType(str, Enum):
    PYTHON = "python"
    AGENT = "agent"
    # ... existing types ...
    CUSTOM = "custom"  # Add your new type
```

### Step 2: Create the Schema Record

Define the Pydantic model for YAML/JSON serialization:

```python
# src/maverick/dsl/serialization/schema.py
class CustomStepRecord(StepRecord):
    """Custom step for specialized operations.

    Fields:
        operation: Type of operation to perform
        config: Operation-specific configuration
    """

    type: Literal[StepType.CUSTOM] = StepType.CUSTOM
    operation: str = Field(..., min_length=1, description="Operation name")
    config: dict[str, Any] = Field(default_factory=dict)

# Add to the discriminated union
StepRecordUnion = Annotated[
    PythonStepRecord
    | AgentStepRecord
    # ... existing types ...
    | CustomStepRecord,  # Add your new record
    Field(discriminator="type"),
]
```

### Step 3: Create the Step Handler

Create the execution handler:

```python
# src/maverick/dsl/serialization/executor/handlers/custom_step.py
"""Custom step handler for specialized operations."""

from __future__ import annotations

from typing import Any

from maverick.dsl.context import WorkflowContext
from maverick.dsl.serialization.executor.handlers.base import EventCallback
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import CustomStepRecord
from maverick.logging import get_logger

logger = get_logger(__name__)


async def execute_custom_step(
    step: CustomStepRecord,
    resolved_inputs: dict[str, Any],
    context: WorkflowContext,
    registry: ComponentRegistry,
    config: Any = None,
    event_callback: EventCallback | None = None,
) -> Any:
    """Execute a custom step.

    Args:
        step: CustomStepRecord containing operation and config.
        resolved_inputs: Resolved inputs from expressions.
        context: WorkflowContext with inputs and step results.
        registry: Component registry.
        config: Optional workflow configuration.
        event_callback: Optional callback for streaming events.

    Returns:
        Operation result.

    Raises:
        ValueError: If operation is not supported.
    """
    operation = step.operation
    step_config = {**step.config, **resolved_inputs}

    logger.info(f"Executing custom operation: {operation}")

    # Implement your operation logic
    if operation == "special_operation":
        result = await _do_special_operation(step_config, context)
    else:
        raise ValueError(f"Unknown custom operation: {operation}")

    return result


async def _do_special_operation(
    config: dict[str, Any],
    context: WorkflowContext,
) -> dict[str, Any]:
    """Perform the special operation."""
    # Implementation
    return {"success": True, "result": "..."}
```

### Step 4: Register the Handler

Add the handler to the registry:

```python
# src/maverick/dsl/serialization/executor/handlers/__init__.py
from maverick.dsl.serialization.executor.handlers import custom_step

STEP_HANDLERS: dict[StepType, StepHandler] = {
    # ... existing handlers ...
    StepType.CUSTOM: custom_step.execute_custom_step,
}
```

### Step 5: Add Tests

Create comprehensive tests:

```python
# tests/unit/dsl/serialization/executor/handlers/test_custom_step.py
import pytest
from maverick.dsl.context import WorkflowContext
from maverick.dsl.serialization.executor.handlers.custom_step import (
    execute_custom_step,
)
from maverick.dsl.serialization.registry import ComponentRegistry
from maverick.dsl.serialization.schema import CustomStepRecord


@pytest.fixture
def custom_step() -> CustomStepRecord:
    return CustomStepRecord(
        name="test-custom",
        operation="special_operation",
        config={"key": "value"},
    )


@pytest.fixture
def context() -> WorkflowContext:
    return WorkflowContext(inputs={}, results={})


@pytest.fixture
def registry() -> ComponentRegistry:
    return ComponentRegistry()


@pytest.mark.asyncio
async def test_execute_custom_step_success(
    custom_step: CustomStepRecord,
    context: WorkflowContext,
    registry: ComponentRegistry,
) -> None:
    """Test successful custom step execution."""
    result = await execute_custom_step(
        step=custom_step,
        resolved_inputs={},
        context=context,
        registry=registry,
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_execute_custom_step_unknown_operation(
    context: WorkflowContext,
    registry: ComponentRegistry,
) -> None:
    """Test custom step with unknown operation."""
    step = CustomStepRecord(
        name="test-unknown",
        operation="unknown_operation",
        config={},
    )

    with pytest.raises(ValueError, match="Unknown custom operation"):
        await execute_custom_step(
            step=step,
            resolved_inputs={},
            context=context,
            registry=registry,
        )
```

### Step 6: Update Documentation

Add documentation for your new step type in the relevant locations:

- Update the step types table in this file
- Add usage examples
- Document schema fields

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

| Aspect      | Convention                                                   | Example                   |
| ----------- | ------------------------------------------------------------ | ------------------------- |
| Line Length | 88 characters (Black compatible)                             | -                         |
| Imports     | Sorted with isort (groups: stdlib, third-party, first-party) | -                         |
| Quotes      | Double quotes for strings                                    | `"hello world"`           |
| Type Hints  | Required for all public functions                            | `def foo(x: int) -> str:` |
| Docstrings  | Google style, required for public APIs                       | See below                 |
| Naming      | See naming conventions table                                 | -                         |

### Naming Conventions

| Element      | Convention           | Example                            |
| ------------ | -------------------- | ---------------------------------- |
| Classes      | PascalCase           | `CodeReviewerAgent`, `FlyWorkflow` |
| Functions    | snake_case           | `execute_review`, `create_pr`      |
| Constants    | SCREAMING_SNAKE_CASE | `MAX_RETRIES`, `DEFAULT_TIMEOUT`   |
| Private      | Leading underscore   | `_build_prompt`, `_validate`       |
| Type Aliases | PascalCase           | `AgentResult`, `WorkflowEvent`     |

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
