# Maverick

AI-powered development workflow orchestration with autonomous agent execution.

## What is Maverick?

Maverick is a Python CLI/TUI application that orchestrates complex AI-powered development workflows using the Claude Agent SDK. It automates the complete development lifecycle from task implementation through code review, validation, and PR management.

Unlike traditional automation tools, Maverick uses autonomous AI agents that can make decisions, recover from failures, and execute complex multi-step workflows without constant human intervention.

## Key Features

- 🤖 **Autonomous Agent Execution** - AI agents handle implementation, review, and fixes independently
- 🔄 **Smart Workflow Orchestration** - DSL-based workflows with parallel execution and conditional logic
- 🎨 **Interactive TUI** - Real-time visibility into agent operations with Textual-based interface
- 📊 **Resilient Operation** - Automatic retries, checkpointing, and graceful degradation
- 🔌 **Extensible Architecture** - Custom workflows, agents, and MCP tools
- 📝 **Spec-Driven Development** - Work from structured specifications with automatic task parsing

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/get2knowio/maverick.git
cd maverick

# Install with pip (development mode)
pip install -e .

# Or install with uv (recommended)
uv pip install -e .
```

### Prerequisites

- Python 3.10 or higher
- [GitHub CLI](https://cli.github.com/) (`gh`) for PR and issue management
- Claude API access (set `ANTHROPIC_API_KEY` environment variable)
- Git repository with remote origin
- [Speckit](https://speckit.org) for task generation (tasks.md files must be generated via `/speckit.tasks`)
- Optional: [CodeRabbit CLI](https://coderabbit.ai/) for enhanced code review
- Optional: [ntfy](https://ntfy.sh) for push notifications

### Basic Usage

```bash
# Initialize configuration
maverick config init

# Run the FlyWorkflow for a feature branch
maverick fly feature-branch-name

# Fix tech debt issues automatically
maverick refuel --label tech-debt

# Review a pull request
maverick review 123

# Check project status
maverick status

# List available workflows
maverick workflow list

# Run a custom workflow
maverick workflow run my-workflow
```

## Core Workflows

### FlyWorkflow

Complete spec-based development workflow for feature implementation:

1. **Setup** - Sync branch with origin/main, validate spec directory
2. **Implementation** - Parse tasks.md, execute tasks (parallel for "P:" marked)
3. **Code Review** - Parallel CodeRabbit + architecture review
4. **Validation** - Format/lint/build/test with iterative fixes
5. **Convention Update** - Update CLAUDE.md if significant learnings
6. **PR Management** - Generate PR body, create/update via GitHub CLI

> **Note:** The `tasks.md` file must be generated using [Speckit](https://speckit.org) via the `/speckit.tasks` command. Manual creation of tasks.md is not supported.

```bash
# First, generate tasks.md using speckit (in Claude Code)
/speckit.tasks

# Then run the workflow
maverick fly my-feature --task-file ./specs/my-feature/tasks.md
```

### RefuelWorkflow

Automated tech-debt resolution workflow:

1. **Discovery** - List open issues with target label
2. **Selection** - Analyze and select up to 3 non-conflicting issues
3. **Implementation** - Execute fixes in parallel
4. **Review & Validation** - Same as FlyWorkflow
5. **Finalize** - Mark PR ready, close issues

```bash
maverick refuel --label tech-debt --limit 5 --parallel
```

## Architecture

Maverick follows a clean separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│  CLI/TUI Layer (Click + Textual)                        │
│  - User interaction and display                         │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Workflow Layer (Orchestration)                         │
│  - FlyWorkflow, RefuelWorkflow                          │
│  - DSL-based workflow execution                         │
│  - State management and sequencing                      │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Agent Layer (Claude Agent SDK)                         │
│  - CodeReviewerAgent, ImplementerAgent, etc.            │
│  - System prompts and tool selection                    │
│  - Autonomous decision-making                           │
└─────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────┐
│  Tool Layer (MCP Tools)                                 │
│  - GitHub operations, git commands                      │
│  - Validation runners, notifications                    │
│  - External system integrations                         │
└─────────────────────────────────────────────────────────┘
```

### Project Structure

```
src/maverick/
├── __init__.py          # Version, public API exports
├── main.py              # CLI entry point (Click commands)
├── config.py            # Pydantic configuration models
├── exceptions.py        # Custom exception hierarchy
├── agents/              # Agent implementations
│   ├── base.py          # MaverickAgent abstract base class
│   └── *.py             # Concrete agents (CodeReviewerAgent, etc.)
├── workflows/           # Workflow orchestration
│   ├── fly.py           # FlyWorkflow - full spec-based workflow
│   └── refuel.py        # RefuelWorkflow - tech-debt resolution
├── dsl/                 # Workflow DSL implementation
├── tools/               # MCP tool definitions
├── hooks/               # Safety and logging hooks
├── tui/                 # Textual application
│   ├── app.py           # Main Textual App
│   ├── screens/         # Screen components
│   └── widgets/         # Reusable widgets
└── utils/               # Shared utilities
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
  model_id: claude-sonnet-4-20250514
  max_tokens: 8192
  temperature: 0.0

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

## Legacy Plugin

The `plugins/maverick/` directory contains the legacy Claude Code plugin implementation. This is being migrated to the Python SDK-based architecture. The plugin is still functional but deprecated.

## License

MIT

## Links

- [Documentation Site](https://get2knowio.github.io/maverick/)
- [Training Slides](https://get2knowio.github.io/maverick/slides/)
- [Contributing Guide](CONTRIBUTING.md)
- [Constitution (Core Principles)](.specify/memory/constitution.md)
- [Issue Tracker](https://github.com/get2knowio/maverick/issues)
- [Claude Agent SDK](https://github.com/anthropics/anthropic-agent-sdk)
