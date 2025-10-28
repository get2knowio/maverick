# Quickstart: CLI Prerequisite Check



This feature defines a Temporal workflow that verifies two prerequisites:This feature defines a Temporal workflow that verifies two prerequisites:

- GitHub CLI is installed and authenticated

- Standalone Copilot CLI binary is available



## Prerequisites## Prerequisites



- Python 3.11+- Python 3.11

- [uv](https://docs.astral.sh/uv/) package manager- uv (https://docs.astral.sh/uv/)

- Temporal server (local dev server)- Temporal server (local dev server or Docker Compose)



## Installation## Install dependencies (planned)



1. **Install dependencies**:A `pyproject.toml` will define dependencies and scripts. Once added, install with:



```bash
uv sync



This will install:

## Run Temporal locally (dev server)
- `temporalio` (Temporal Python SDK)

- `pytest` and `pytest-asyncio` (testing)- Option A: Temporal CLI dev server

- `ruff` (linting, dev dependency)- Option B: Docker Compose (if provided in repo)



## Running the Readiness Check## Execute readiness workflow (planned uv script)



### Step 1: Start Temporal ServerOnce `pyproject.toml` is in place, a script will be available:



Start the Temporal dev server (in a separate terminal):```bash

uv run workflows:readiness

```bash```

temporal server start-dev

```This will:

1) Start a worker (if not already running)

This will start a local Temporal server at `localhost:7233` with a web UI at `localhost:8233`.2) Execute the readiness workflow

3) Print human‑readable summary and exit non‑zero on failure

### Step 2: Start the Readiness Worker

## Testing

In another terminal, start the worker that will process workflow tasks:

Run tests (unit + integration) with:

```bash

uv run readiness-worker```bash

```uv run pytest -q

```

The worker will:

- Connect to Temporal server at `localhost:7233`Temporal tests will:

- Register the `ReadinessWorkflow` and activity functions- Unit-test activity functions (gh auth status parsing; copilot help presence)

- Listen on the `readiness-task-queue` for tasks- Integration-test workflow orchestration and summary mapping

- Keep running until you stop it (Ctrl+C)

### Step 3: Execute the Readiness Check

In your original terminal, run the readiness check:

```bash
uv run readiness-check
```

This will:
1. Connect to the Temporal server
2. Execute the readiness workflow
3. Display a human-readable summary of prerequisite checks
4. Exit with code 0 if ready, 1 if not ready, or 2 on error

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
uv run readiness-worker
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
