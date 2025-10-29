# Maverick

Temporal-based CLI tools for development workflow automation.

## Overview

Maverick provides Temporal workflows and activities to automate common development tasks, with built-in observability, reliability, and scalability.

## Features

### CLI Readiness Check

Verifies that essential development tools are installed and properly configured, and validates GitHub repository access before starting work.

**What it checks:**
- ✓ GitHub CLI (`gh`) - Installed and authenticated
- ✓ Copilot CLI (`copilot`) - Available and functional
- ✓ GitHub Repository - Accessible and valid

**Key capabilities:**
- Non-interactive, automated checks
- Clear pass/fail status for each check
- Actionable remediation guidance with official documentation links
- Fast execution (< 30 seconds)
- Structured logging for observability

**Quick start:**

```bash
# Start Temporal server (separate terminal)
temporal server start-dev

# Start the worker (separate terminal)
uv run maverick-worker

# Run the readiness check with your repository URL
uv run readiness-check https://github.com/owner/repo
```

## Requirements

- **Python**: 3.11 or later
- **Package Manager**: [uv](https://github.com/astral-sh/uv)
- **Temporal**: Local dev server or remote cluster

## Installation

1. **Clone the repository**:

```bash
git clone https://github.com/get2knowio/maverick.git
cd maverick
```

2. **Install dependencies**:

```bash
uv sync
```

This installs:
- Temporal Python SDK
- Testing framework (pytest)
- Code quality tools (ruff)

## Development

### Project Structure

```text
src/
├── activities/        # Temporal activity implementations
├── workflows/         # Temporal workflow definitions
├── workers/          # Temporal worker processes
├── cli/              # CLI entrypoints
├── models/           # Data models and types
└── common/           # Shared utilities (logging, etc.)

tests/
├── unit/             # Unit tests for activities
└── integration/      # Integration tests for workflows

specs/                # Feature specifications and documentation
```

### Running Tests

```bash
# All tests
uv run pytest

# Unit tests only
uv run pytest tests/unit/

# Integration tests only
uv run pytest tests/integration/

# With coverage
uv run pytest --cov=src
```

### Code Quality

```bash
# Run linting
uv run ruff check .

# Auto-fix issues
uv run ruff check --fix .
```

### Development Workflow

1. Start Temporal server: `temporal server start-dev`
2. Start the worker: `uv run maverick-worker`
3. Make your changes
4. Run tests: `uv run pytest`
5. Run linting: `uv run ruff check .`
6. Execute CLI: `uv run readiness-check https://github.com/owner/repo`

## Architecture

Maverick follows Temporal best practices:

- **Activities**: Pure functions that interact with external systems (CLI tools, APIs)
- **Workflows**: Orchestration logic that coordinates activities
- **Workers**: Single consolidated worker that hosts all workflows and activities
- **CLI**: User-facing commands that trigger workflows

### Worker Architecture

Maverick uses a **unified worker architecture**:
- Single worker process (`maverick-worker`) hosts all workflows and activities
- Single task queue (`maverick-task-queue`) for all workflow types
- Benefits: Simplified operations, better resource utilization, easier deployment

Available workflows:
- **ReadinessWorkflow**: Checks CLI tool prerequisites and verifies GitHub repository access

Key principles:
- **Deterministic workflows**: All non-deterministic operations (time, randomness) use Temporal-safe APIs
- **Type safety**: Proper `result_type` specifications for activity results
- **Literal types**: Used instead of Enums for seamless JSON serialization
- **Structured logging**: JSON-based logging in activities/workers, traditional logging in CLI
- **Error resilience**: Safe subprocess decoding, JSON serialization with fallbacks
- **Single worker**: Consolidated architecture for simplified operations

### Logging Architecture

Maverick uses two logging approaches:
- **Activities & Workers**: Structured JSON logging (`src/utils/logging.py`) with SafeJSONEncoder
- **CLI & User-facing**: Traditional formatted logging (`src/common/logging.py`)
- **Workflows**: Use `workflow.logger` exclusively (never import loggers)

This separation ensures proper observability while maintaining deterministic workflow behavior.

## Contributing

1. Read the [constitution](.github/copilot-instructions.md) for coding standards
2. Check feature specs in `specs/` directory
3. Follow TDD: Write tests before implementation
4. Ensure all tests pass and linting is clean
5. Submit a pull request

## License

MIT

````
