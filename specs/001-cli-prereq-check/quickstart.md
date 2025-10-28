# Quickstart: CLI Prerequisite Check

This guide walks through running the Temporal workflow that verifies two prerequisites:

- GitHub CLI is installed and authenticated.
- The standalone Copilot CLI binary is available.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Temporal development server (Temporal CLI `start-dev` or Docker Compose)

## Install Dependencies

Ensure the repository `pyproject.toml` is present, then install dependencies:

```bash
uv sync
```

This installs the Temporal Python SDK, test tooling (`pytest`, `pytest-asyncio`), linting (`ruff`), and supporting libraries required by the readiness workflow.

## Run Temporal Locally

Start a local Temporal server before launching the workflow:

```bash
temporal server start-dev
```

This command starts Temporal at `localhost:7233` with the web UI at `localhost:8233`.

## Running the Readiness Check

### Step 1: Start the Readiness Worker

In a new terminal, run the worker that hosts the workflow activities:

```bash
uv run readiness:worker
```

The worker connects to the Temporal server, registers `ReadinessWorkflow`, and continues running until you stop it (Ctrl+C).

### Step 2: Execute the Readiness Check

From your original terminal, trigger the workflow:

```bash
uv run readiness:check
```

The CLI client connects to Temporal, schedules the readiness workflow, prints a human-readable summary, and exits with code `0` when ready, `1` when not ready, or `2` on error.

### Example Output (Success)

```text
============================================================
CLI Readiness Check
============================================================

✓ GH: PASS
  GitHub CLI is installed and authenticated

✓ COPILOT: PASS
  Copilot CLI is available

------------------------------------------------------------
✓ Overall Status: READY

All prerequisites are satisfied. You're ready to proceed!

Check completed in 234ms
============================================================
```

### Example Output (Failure)

```text
============================================================
CLI Readiness Check
============================================================

✗ GH: FAIL
  GitHub CLI is not authenticated

  Remediation:
    You need to authenticate with GitHub:
      gh auth login

    After installation, authenticate with:
      gh auth login

    Official documentation: https://cli.github.com/

------------------------------------------------------------
✗ Overall Status: NOT READY

Some prerequisites are not satisfied. Please review the
remediation guidance above and try again.

Check completed in 189ms
============================================================
```

## Development & Testing

### Run All Tests

```bash
uv run pytest
```

### Run Specific Test Categories

```bash
# Unit tests only
uv run pytest tests/unit/

# Integration tests only
uv run pytest tests/integration/

# Verbose output
uv run pytest -v

# Quick mode (less output)
uv run pytest -q
```

### Run Linting

```bash
uv run ruff check .
```

### Test Coverage

The test suite includes:
- **Unit tests**: Test individual activity functions (`gh_status`, `copilot_help`)
- **Integration tests**: Test complete workflow orchestration with Temporal test environment
- **Remediation tests**: Verify actionable guidance is provided on failures

## Troubleshooting

### Worker Not Running

If you get an error like "workflow execution failed", ensure the worker is running:

```bash
uv run readiness:worker
```

### Temporal Server Not Running

If you get connection errors, ensure the Temporal dev server is running:

```bash
temporal server start-dev
```

### Check Logs

Both the worker and CLI use structured logging. Check terminal output for detailed error messages.

## Architecture

```text
┌─────────────┐
│     CLI     │  (readiness-check)
│  Triggers   │
└──────┬──────┘
       │
       v
┌─────────────────────────────┐
│   Temporal Workflow         │
│  (ReadinessWorkflow.run)    │
│                             │
│  ┌────────────────────┐    │
│  │ Activity: gh_status│    │
│  └────────────────────┘    │
│           +                 │
│  ┌─────────────────────┐   │
│  │ Activity:           │   │
│  │ copilot_help        │   │
│  └─────────────────────┘   │
│                             │
│  Returns: ReadinessSummary  │
└─────────────────────────────┘
       │
       v
┌─────────────┐
│  Worker     │  (readiness-worker)
│  Executes   │
└─────────────┘
```

## Next Steps

After running the readiness check:

1. **If READY**: All prerequisites are satisfied. Proceed with development.
2. **If NOT READY**: Follow the remediation guidance in the output to install/configure missing tools.
3. **Review Logs**: Check worker and CLI output for detailed execution information.

For more details on the implementation, see:
- Data models: `src/models/prereq.py`
- Activities: `src/activities/gh_status.py`, `src/activities/copilot_help.py`
- Workflow: `src/workflows/readiness.py`
- Worker: `src/workers/readiness_worker.py`
- CLI: `src/cli/readiness.py`
