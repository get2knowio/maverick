# Maverick

Temporal-based CLI tools for development workflow automation.

## Overview

Maverick provides Temporal workflows and activities to automate common development tasks, with built-in observability, reliability, and scalability.

## Features

### CLI Prerequisite Check

Verifies that essential development tools are installed and properly configured before starting work.

**What it checks:**
- ✓ GitHub CLI (`gh`) - Installed and authenticated
- ✓ Copilot CLI (`copilot`) - Available and functional

**Key capabilities:**
- Non-interactive, automated checks
- Clear pass/fail status for each tool
- Actionable remediation guidance with official documentation links
- Fast execution (< 30 seconds)
- Structured logging for observability

**Quick start:**

```bash
# Start Temporal server (separate terminal)
temporal server start-dev

# Start the worker (separate terminal)
uv run readiness-worker

# Run the readiness check
uv run readiness-check
```

See [quickstart guide](specs/001-cli-prereq-check/quickstart.md) for detailed instructions.

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
2. Start the worker: `uv run readiness-worker`
3. Make your changes
4. Run tests: `uv run pytest`
5. Run linting: `uv run ruff check .`
6. Execute CLI: `uv run readiness-check`

## Architecture

Maverick follows Temporal best practices:

- **Activities**: Pure functions that interact with external systems (CLI tools, APIs)
- **Workflows**: Orchestration logic that coordinates activities
- **Workers**: Long-running processes that execute activities and workflows
- **CLI**: User-facing commands that trigger workflows

Key principles:
- **Deterministic workflows**: All non-deterministic operations (time, randomness) use Temporal-safe APIs
- **Type safety**: Proper `result_type` specifications for activity results
- **Literal types**: Used instead of Enums for seamless JSON serialization
- **Structured logging**: Consistent logging format across all components

## Contributing

1. Read the [constitution](.github/copilot-instructions.md) for coding standards
2. Check feature specs in `specs/` directory
3. Follow TDD: Write tests before implementation
4. Ensure all tests pass and linting is clean
5. Submit a pull request

## License

MIT

````
