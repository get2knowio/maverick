# Maverick

AI-powered development workflow orchestration with autonomous agent execution.

## What is Maverick?

Maverick is a Python CLI/TUI application that orchestrates AI-powered development workflows using the Claude Agent SDK. It automates the complete development lifecycle from task implementation through code review, validation, and PR management.

Unlike traditional automation tools, Maverick uses:
- **Autonomous AI agents** that make decisions and recover from failures
- **YAML-based workflow DSL** for declarative, shareable workflow definitions
- **Unified architecture** where all workflows are discoverable YAML files

## Key Features

- **Declarative Workflows** - Define workflows in YAML with conditional logic, parallel execution, and checkpoints
- **Autonomous Agents** - AI agents handle implementation, review, and fixes independently
- **Interactive TUI** - Real-time visibility into agent operations with Textual-based interface
- **Resilient Operation** - Automatic retries, checkpointing, and graceful degradation
- **Extensible Architecture** - Custom workflows, agents, and MCP tools
- **Workflow Discovery** - Automatic discovery from project, user, and built-in locations

## Quick Start

### Prerequisites

- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/) - Fast Python package manager (recommended)
- [GitHub CLI](https://cli.github.com/) (`gh`) for PR and issue management
- Claude API access (set `ANTHROPIC_API_KEY` environment variable)
- Git repository with remote origin
- Optional: [CodeRabbit CLI](https://coderabbit.ai/) for enhanced code review
- Optional: [ntfy](https://ntfy.sh) for push notifications

### Installation

#### Using uv (Recommended)

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/get2knowio/maverick.git
cd maverick

# Install with uv (uses uv.lock for reproducible builds)
uv sync

# Run maverick
uv run maverick --help

# Or install globally as a tool
uv tool install .
maverick --help
```

#### Using pip

```bash
# Clone the repository
git clone https://github.com/get2knowio/maverick.git
cd maverick

# Install with pip (development mode)
pip install -e .
```

### Basic Usage

```bash
# Execute a workflow (primary interface)
maverick fly feature -i branch_name=my-feature

# Run tech-debt cleanup
maverick fly cleanup -i label=tech-debt -i limit=5

# Quick fix a single issue
maverick fly quick-fix -i issue_number=123

# Run code review
maverick fly review -i pr_number=456

# Run validation with auto-fix
maverick fly validate

# List available workflows
maverick workflow list

# Show workflow details
maverick workflow show feature

# Generate workflow diagram
maverick workflow viz feature --format mermaid

# Create a new custom workflow
maverick workflow new my-workflow --template full
```

## Built-in Workflows

All workflows are defined as YAML files and can be customized by placing overrides in `.maverick/workflows/`.

### feature

Full spec-based development workflow for feature implementation:

1. **Init** - Sync branch with origin/main, validate workspace
2. **Implement** - Parse tasks.md, execute tasks phase-by-phase
3. **Validate** - Format/lint/typecheck/test with automatic fix retry
4. **Commit** - Generate commit message and push changes
5. **Review** - Optional automated code review
6. **Create PR** - Generate PR body and create pull request

```bash
maverick fly feature -i branch_name=025-new-feature
maverick fly feature -i branch_name=025-new-feature -i skip_review=true
maverick fly feature -i branch_name=025-new-feature --dry-run
```

### cleanup

Tech-debt resolution workflow (replaces the former RefuelWorkflow):

1. **Fetch Issues** - List open issues with target label
2. **Analyze** - Select up to N non-conflicting issues
3. **Process** - Fix issues in parallel or sequentially
4. **Create PRs** - Generate PRs for each fix
5. **Report** - Summary of all processed issues

```bash
maverick fly cleanup -i label=tech-debt -i limit=5
maverick fly cleanup -i label=refactor -i parallel=false
```

### quick-fix

Rapid single-issue resolution:

```bash
maverick fly quick-fix -i issue_number=123
```

### review

Code review orchestration combining CodeRabbit and AI agent review:

```bash
maverick fly review -i pr_number=123
maverick fly review -i pr_number=123 -i base_branch=develop
```

### validate

Validation with optional automatic fixes:

```bash
maverick fly validate
maverick fly validate -i fix=false
maverick fly validate -i max_attempts=5
```

## Workflow Discovery

Workflows are discovered from three locations (higher precedence overrides lower):

1. **Project** - `.maverick/workflows/` - Project-specific customizations
2. **User** - `~/.config/maverick/workflows/` - User-wide customizations
3. **Built-in** - Packaged with Maverick - Default implementations

To customize a built-in workflow, copy it to your project directory and modify:

```bash
mkdir -p .maverick/workflows
# Find the built-in workflow location
maverick workflow info feature
# Copy and customize
cp /path/to/builtin/feature.yaml .maverick/workflows/feature.yaml
# Edit .maverick/workflows/feature.yaml
```

## Architecture

Maverick follows a clean separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│  CLI Layer (Click)                                          │
│  - maverick fly, workflow, config, status                   │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Workflow DSL Layer                                         │
│  - YAML parsing and validation                              │
│  - Step execution (python, agent, validate, parallel, etc.) │
│  - Checkpointing and resumption                             │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Agent Layer (Claude Agent SDK)                             │
│  - CodeReviewerAgent, ImplementerAgent, FixerAgent          │
│  - System prompts and tool selection                        │
│  - Autonomous decision-making                               │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  Tool Layer (MCP Tools)                                     │
│  - GitHub operations, git commands                          │
│  - Validation runners, notifications                        │
│  - External system integrations                             │
└─────────────────────────────────────────────────────────────┘
```

### Project Structure

```
src/maverick/
├── cli/                 # Click CLI commands
│   └── commands/        # fly, workflow, config, review, status
├── dsl/                 # Workflow DSL implementation
│   ├── serialization/   # YAML parsing, schema, executor
│   ├── discovery/       # Workflow discovery from locations
│   ├── steps/           # Step type implementations
│   └── visualization/   # ASCII and Mermaid diagram generation
├── agents/              # Agent implementations
│   ├── code_reviewer.py
│   ├── implementer.py
│   ├── fixer.py
│   └── generators/      # Text generators (commit, PR, etc.)
├── library/             # Built-in workflows and actions
│   ├── workflows/       # YAML workflow definitions
│   ├── actions/         # Python actions for workflows
│   └── fragments/       # Reusable workflow fragments
├── tools/               # MCP tool definitions
│   ├── github/          # GitHub API tools
│   └── git/             # Git operation tools
├── tui/                 # Textual TUI application
│   ├── screens/
│   └── widgets/
└── runners/             # Subprocess runners (validation, commands)
```

## Workflow DSL

Workflows are defined in YAML with a rich set of step types:

```yaml
version: "1.0"
name: my-workflow
description: Example workflow

inputs:
  branch_name:
    type: string
    required: true
  skip_tests:
    type: boolean
    default: false

steps:
  # Python action
  - name: setup
    type: python
    action: init_workspace
    kwargs:
      branch: ${{ inputs.branch_name }}

  # Agent invocation
  - name: implement
    type: agent
    agent: implementer
    context:
      task_file: ${{ steps.setup.output.task_file }}

  # Validation with retry
  - name: validate
    type: validate
    stages: ["format", "lint", "typecheck", "test"]
    retry: 3

  # Conditional execution
  - name: run_tests
    type: python
    action: run_tests
    when: ${{ not inputs.skip_tests }}

  # Parallel execution
  - name: parallel_reviews
    type: parallel
    steps:
      - name: coderabbit
        type: python
        action: run_coderabbit
      - name: agent_review
        type: agent
        agent: code_reviewer

  # Checkpoint for resumption
  - name: checkpoint_done
    type: checkpoint
    checkpoint_id: implementation_complete

  # Sub-workflow
  - name: create_pr
    type: subworkflow
    workflow: create-pr-with-summary
    inputs:
      base_branch: main
```

## Configuration

Maverick uses YAML configuration files with layered precedence:

1. Project config: `./maverick.yaml`
2. User config: `~/.config/maverick/config.yaml`
3. CLI arguments (highest precedence)

Example configuration:

```yaml
github:
  owner: your-org
  repo: your-repo
  default_branch: main

model:
  model_id: claude-sonnet-4-5-20250929

validation:
  format_cmd: ["ruff", "format", "."]
  lint_cmd: ["ruff", "check", "--fix", "."]
  test_cmd: ["pytest", "-x", "--tb=short"]
  timeout_seconds: 300

notifications:
  enabled: false
  server: https://ntfy.sh
  topic: maverick-notifications

parallel:
  max_agents: 3
  max_tasks: 5

verbosity: warning
```

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Setting up a development environment
- Running tests and linting
- Understanding the architecture
- Creating custom agents and workflows
- Contributing guidelines

### Development Commands

```bash
make test        # Run tests
make lint        # Run ruff linter
make typecheck   # Run mypy
make format-fix  # Apply formatting
make check       # Run all checks
```

## License

MIT

## Links

- [Documentation Site](https://get2knowio.github.io/maverick/)
- [Training Slides](https://get2knowio.github.io/maverick/slides/)
- [Contributing Guide](CONTRIBUTING.md)
- [Issue Tracker](https://github.com/get2knowio/maverick/issues)
- [Claude Agent SDK](https://github.com/anthropics/anthropic-agent-sdk)
