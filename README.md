# Maverick

Temporal-based CLI tools for development workflow automation.

## Overview

Maverick provides Temporal workflows and activities to automate common development tasks, with built-in observability, reliability, and scalability.

## Features

### Maverick CLI

The `maverick` command is now the single interface for orchestrating specs-backed work. Install it once with `uv tool install maverick --from git+https://github.com/get2knowio/maverick.git`, then run `maverick <command>` from any repository that contains `specs/*/tasks.md`.

**Quick start**

```bash
# Install once (requires uv 0.4+ and the Temporal CLI in PATH)
uv tool install maverick --from git+https://github.com/get2knowio/maverick.git

# Run from any repo that contains specs/*/tasks.md files
maverick run
```

**How it works**

- Bootstraps a local Temporal dev server and the Maverick worker automatically (no extra terminals required). Set `MAVERICK_SKIP_TEMPORAL_BOOTSTRAP=1` if you want to connect to an existing cluster.
- Validates that you are inside a git repository (and a clean working tree unless `--allow-dirty` is supplied).
- Discovers `tasks.md` files under `specs/`, skipping `specs-completed/`, and sorts them by numeric directory prefix (001, 002, …).
- Generates stable task IDs and branch hints, then starts `MultiTaskOrchestrationWorkflow` on the `maverick-task-queue`.
- Prints the workflow ID (`maverick-run-*`) and run ID so you can monitor or reconnect while the CLI session is active.

**`maverick run`**

Starts the workflow, validates repo state, and streams Temporal progress until completion.

```bash
# Run everything that was discovered
maverick run

# Limit execution to one tasks.md file
maverick run --task specs/042-new-feature/tasks.md

# Pause between phases/tasks
maverick run --interactive

# Non-blocking preview for CI bots
maverick run --dry-run --json

# Minimal TTY output (one-line updates)
maverick run --compact
```

Options:
- `--task PATH` – restrict execution to a single tasks file inside the repo root.
- `--interactive` – instructs the workflow to pause between major phases; resume or skip with Temporal signals (`temporal workflow signal --workflow-id <id> --name continue_to_next_phase` or `skip_current_task`).
- `--dry-run` – skip Temporal execution and print the descriptors that would run (task ID, file path, derived branch, discovery timing).
- `--json` – emit JSON payloads for every poll plus the final summary; works with real runs and dry runs.
- `--allow-dirty` – bypass the clean working tree requirement (default is to block when there are uncommitted files).
- `--compact` – collapse human-readable streaming output to a single line per poll for cramped terminals.

Runtime notes:
- Rich-based tables are shown automatically when stdout is a TTY; JSON mode disables styling.
- Pressing `Ctrl+C` now cancels the workflow because the CLI owns the Temporal server/worker lifecycle. Re-run `maverick run` to restart.
- Discovery failures (missing specs directory, empty results) surface actionable remediation text. Dry runs exit with `task_count: 0` when nothing is queued.
- The CLI shells out to the Temporal CLI binary (`temporal`). Install it via https://docs.temporal.io/cli or set `TEMPORAL_CLI_PATH`.
- Set `MAVERICK_SKIP_TEMPORAL_BOOTSTRAP=1` and/or `MAVERICK_SKIP_WORKER_BOOTSTRAP=1` to connect to an already-running Temporal deployment (for remote clusters or CI).

**`maverick status <workflow-id>`**

Reattach to a running or completed workflow—no need to keep the original `run` session open.

```bash
maverick status maverick-run-1730941830
maverick status maverick-run-1730941830 --json
```

`status` prints workflow/run IDs, current state (`running`, `completed`, or `failed`), the task currently executing, and per-task progress summaries. JSON mode returns a stable schema that is easy to scrape for dashboards.

**Automation-friendly output**

- `run --json` emits a progress document each poll plus p95 poll latency when the workflow finishes.
- `run --dry-run --json` is ideal for CI pre-checks; it exits 0 with `task_count: 0` when nothing is available.
- `status --json` returns timestamps, task IDs, and last messages so you can build a lightweight status board or Slack notifier.

**Troubleshooting**

- Connection failures usually indicate the Temporal CLI is missing or blocked. Install `temporal`, or set `MAVERICK_SKIP_TEMPORAL_BOOTSTRAP=1` / `MAVERICK_SKIP_WORKER_BOOTSTRAP=1` to point at an existing cluster and verify `TEMPORAL_HOST=localhost:7233`.
- Git validation errors show the current directory and how to fix dirty working trees (or rerun with `--allow-dirty`).
- If discovery returns no work, the CLI raises `NoTasksDiscoveredError`; rerun with `--dry-run` to inspect discovery order without touching Temporal.

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

> **Note:** When you run `maverick`, the CLI automatically boots the Temporal dev server and worker. The commands below are only required when invoking the legacy helper directly for debugging.

```bash
# Start Temporal server (separate terminal)
temporal server start-dev

# Start the worker (separate terminal)
maverick-worker

# Run the readiness check with your repository URL
readiness-check https://github.com/owner/repo
```

### Automated Phase Execution

Automates the sequential execution of Speckit `tasks.md` phases, enabling AI-backed implementation with built-in checkpoint management and resume capabilities.

**What it does:**
- ✓ Parses `tasks.md` into structured phase definitions
- ✓ Executes phases sequentially via `speckit.implement`
- ✓ Maintains checkpoints for fault-tolerant resume
- ✓ Supports per-phase AI model and agent profile overrides
- ✓ Captures structured execution logs and results
- ✓ Handles document drift with automatic checkpoint recalculation

**Key capabilities:**
- Sequential phase orchestration with deterministic execution
- Resume from failure without repeating completed phases
- Per-phase execution context (timeout, retry policy, AI settings)
- Machine-readable phase results (JSON with timestamps, task IDs, logs)
- Automatic checkpoint validation and drift detection
- Structured logging for observability and debugging

**Quick start:**

> **Note:** Normal usage goes through `maverick run`, which handles Temporal/worker bootstrap automatically. Use the legacy commands below only when debugging the underlying workflows in isolation.

```bash
# Start Temporal server (separate terminal)
temporal server start-dev

# Start the worker (separate terminal)
maverick-worker

# Run phase automation on your tasks.md
python -m src.cli.readiness --workflow automate-phase-tasks \
  --tasks-md-path /path/to/specs/feature/tasks.md \
  --repo-path /path/to/repo \
  --branch feature-branch

# Resume after a failure (automatically skips completed phases)
python -m src.cli.readiness --workflow automate-phase-tasks \
  --tasks-md-path /path/to/specs/feature/tasks.md \
  --repo-path /path/to/repo \
  --branch feature-branch

# Review phase results
cat /tmp/phase-results/<workflow-id>/<phase-id>.json
```

### PR CI Automation

Automates the creation, monitoring, and merging of AI-authored pull requests by standardizing on the GitHub CLI (`gh`). Provides deterministic outcomes for workflow orchestration with built-in retry logic and structured failure reporting.

**What it does:**
- ✓ Creates or reuses pull requests from AI-authored branches
- ✓ Monitors GitHub Actions CI status with bounded polling
- ✓ Merges PRs automatically when all checks pass
- ✓ Returns structured failure evidence for remediation
- ✓ Handles timeouts, base branch mismatches, and resume scenarios
- ✓ Emits SLA metrics for polling and merge operations

**Key capabilities:**
- **Idempotent PR management**: Reuses existing PRs, prevents duplicates
- **Bounded CI polling**: Exponential backoff with configurable timeout (default: 45 min)
- **Deterministic results**: Four terminal states: `merged`, `ci_failed`, `timeout`, `error`
- **Failure aggregation**: Captures job names, statuses, and log URLs for failed checks
- **Base branch validation**: Prevents merge when PR targets unexpected branch
- **Resume-safe**: Handles workflow replays and retries without side effects
- **Observability**: Structured logging with SLA timing metrics

**Terminal States:**
- `merged`: CI passed, PR merged successfully with commit SHA
- `ci_failed`: One or more checks failed, returns failure details with log URLs
- `timeout`: CI didn't complete within timeout, PR left open for investigation
- `error`: Pre-merge failure (missing branch, base mismatch, CLI errors)

**Integration:**

Used as a Temporal activity within workflows. Example from phase automation:

```python
from src.models.phase_automation import (
    PullRequestAutomationRequest,
    PullRequestAutomationResult,
    PollingConfiguration,
)

# Configure PR automation request
pr_request = PullRequestAutomationRequest(
    source_branch="feature-123",
    target_branch="main",  # Optional, defaults to repo default branch
    summary="AI-generated PR description...",
    workflow_attempt_id="workflow-id-123",
    polling=PollingConfiguration(
        interval_seconds=30,
        timeout_minutes=45,
        max_retries=5,
    ),
)

# Execute as Temporal activity
result: PullRequestAutomationResult = await workflow.execute_activity(
    "pr_ci_automation",
    pr_request,
    start_to_close_timeout=timedelta(hours=1),
    result_type=PullRequestAutomationResult,
)

# Handle deterministic outcomes
if result.status == "merged":
    # Success: PR merged, commit SHA available
    logger.info("pr_merged", merge_sha=result.merge_commit_sha)
elif result.status == "ci_failed":
    # Failure: Start remediation with failure details
    for failure in result.ci_failures:
        logger.error("check_failed", job=failure.job_name, url=failure.log_url)
elif result.status == "timeout":
    # Timeout: Extend timeout or manual investigation
    logger.warning("ci_timeout", duration=result.polling_duration_seconds)
elif result.status == "error":
    # Error: Address root cause per retry_advice
    logger.error("pr_error", detail=result.error_detail)
```

**CLI Prerequisites:**
- GitHub CLI (`gh`) authenticated with repository access
- Source branch pushed to remote
- Repository with GitHub Actions configured (optional, PRs without CI auto-merge)

**Configuration:**
- Default polling interval: 30 seconds
- Default timeout: 45 minutes
- Default max retries: 5 (for transient errors)
- Exponential backoff coefficient: 2.0x

**Observability:**

Key log events:
- `pr_ci_automation_started` → Activity begins
- `existing_pr_found` / `pr_created` → PR ready
- `base_branch_validated` → Target alignment confirmed
- `ci_poll_started` → Polling begins
- `ci_poll_update` → Per-poll status (periodic)
- `ci_poll_completed_success` / `ci_poll_completed_failure` / `ci_poll_timeout` → Terminal state
- `pull_request_merged` → Merge completed
- `ci_poll_sla_metrics` / `pr_merge_sla_metrics` → Timing metrics

**See Also:**
- Full flow examples: `specs/001-pr-ci-automation/quickstart.md`
- Data model: `specs/001-pr-ci-automation/data-model.md`
- Implementation: `src/activities/pr_ci_automation.py`

### Multi-Task Orchestration

`maverick run` launches `MultiTaskOrchestrationWorkflow`, which processes each discovered `tasks.md` sequentially (initialize → implement → review/fix → PR/CI/merge) with deterministic replay guarantees.

**What it does:**
- ✓ Processes multiple task files sequentially through all phases
- ✓ Calls AutomatePhaseTasksWorkflow as a child workflow for each task
- ✓ Implements fail-fast behavior (stops on first task failure)
- ✓ Supports interactive mode with pause/resume between tasks
- ✓ Maintains progress state for resumability after worker restarts
- ✓ Returns aggregated results with success/failure statistics

**Key capabilities:**
- **Sequential processing**: Processes tasks one by one to avoid branch conflicts
- **Fail-fast error handling**: Stops immediately on task failure, returns partial results
- **Interactive approval gates**: Optional pause after each task for manual review
- **Resume from interruption**: Automatically resumes from correct task after worker restart
- **Progress tracking**: Query handlers provide real-time workflow state
- **Signal control**: Skip current task or continue to next task via signals

**Quick start:**

```bash
# Install once if needed, then run workflows
maverick run
```

**Common flows:**

```bash
# Target a single spec/tasks file
maverick run --task specs/feature-alpha/tasks.md

# Dry run to inspect discovery order (no workflow started)
maverick run --dry-run

# JSON streaming for dashboards
maverick run --json --compact

# Check on a workflow later
maverick status maverick-run-1730941830

# Interactive mode waiting for approval? Send Temporal signals:
temporal workflow signal \
  --workflow-id maverick-run-1730941830 \
  --name continue_to_next_phase

temporal workflow signal \
  --workflow-id maverick-run-1730941830 \
  --name skip_current_task
```

**Monitoring & control:**
- `maverick run` streams the workflow’s query handlers (`get_progress`, `get_task_results`); use `maverick status` for ad-hoc checks from new terminals.
- When `--interactive` is set, the workflow pauses until you send a `continue_to_next_phase` or `skip_current_task` signal (use the Temporal CLI commands above).
- The standalone CLI manages worker lifecycle; rerun `maverick run` if you need to restart a session.

**Configuration:**
- `retry_limit` defaults to 3 (configurable via `OrchestrationInput` when called programmatically).
- `interactive_mode` is toggled by the CLI flag.
- `default_model` / `default_agent_profile` can be overridden when invoking the workflow directly in Python.
- Workflow IDs are generated with the `maverick-run-*` prefix for predictable lookups.

**Output format:**

```text
============================================================
Multi-Task Orchestration
============================================================

Total Tasks:       5
Successful Tasks:  3
Failed Tasks:      1
Skipped Tasks:     0
Unprocessed Tasks: 1

⚠️  Workflow terminated early due to task failure

------------------------------------------------------------
Task Results:

✓ Task 1: SUCCESS
  File: /workspace/tasks/feature-001.md
  Duration: 1234s
  Phases: 4
    ✓ initialize: success (120s)
    ✓ implement: success (800s)
    ✓ review_fix: success (200s)
    ✓ pr_ci_merge: success (114s)

✗ Task 2: FAILED
  File: /workspace/tasks/feature-002.md
  Duration: 456s
  Phases: 2
    ✓ initialize: success (100s)
    ✗ implement: failed (356s)
  Failure: Phase 'implement' failed after 3 retries: Compilation error

------------------------------------------------------------
Unprocessed Tasks (not attempted):
  - /workspace/tasks/feature-003.md

------------------------------------------------------------
✗ Workflow stopped early due to task failure

Total Duration: 1690s
============================================================
```

**Integration:**

Used programmatically within applications:

```python
from temporalio.client import Client
from src.models.orchestration import OrchestrationInput, OrchestrationResult

# Connect to Temporal
client = await Client.connect("localhost:7233")

# Build input
orchestration_input = OrchestrationInput(
    task_file_paths=("tasks/feature-001.md", "tasks/feature-002.md"),
    interactive_mode=False,
    retry_limit=3,
    repo_path="/workspace/myrepo",
    branch="feature-batch-001",
)

# Execute workflow
result: OrchestrationResult = await client.execute_workflow(
    "MultiTaskOrchestrationWorkflow",
    orchestration_input,
    id="orchestrate-batch-001",
    task_queue="maverick-task-queue",
)

# Check results
if result.failed_tasks > 0:
    print(f"❌ {result.failed_tasks} tasks failed")
    for task_result in result.task_results:
        if task_result.overall_status == "failed":
            print(f"  - {task_result.task_file_path}: {task_result.failure_reason}")
else:
    print(f"✅ All {result.successful_tasks} tasks completed successfully!")
```

**Error handling:**

The workflow implements fail-fast behavior:
- Task failure → Workflow stops immediately, returns partial results
- Child workflow exception → Captured and converted to failed TaskResult
- Empty phase list → Treated as task failure with synthetic PhaseResult
- Validation errors → Caught during OrchestrationInput construction

Unprocessed tasks are listed in `OrchestrationResult.unprocessed_task_paths` for visibility.

**See Also:**
- `src/workflows/multi_task_orchestration.py` – workflow implementation
- `src/models/orchestration.py` – orchestration input/output contracts
- `src/models/phase_automation.py` – phase automation parameters

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
# All tests (10-minute timeout by default)
timeout 600 uv run pytest

# Unit tests only
timeout 600 uv run pytest tests/unit/

# Integration tests only
timeout 600 uv run pytest tests/integration/

# With coverage
timeout 600 uv run pytest --cov=src
```

Allocate 10 minutes by default because suites currently take ~8 minutes to run. Adjust higher only if needed, but every pytest invocation MUST include a `timeout` wrapper to catch hanging tests.

### Code Quality

```bash
# Run linting
uv run ruff check .

# Auto-fix issues
uv run ruff check --fix .
```

### Development Workflow

1. Install project dependencies: `uv sync`
2. Ensure the Temporal CLI (`temporal`) is installed and in your PATH (the `maverick` CLI shells out to it).
3. Make your changes
4. Run tests: `timeout 600 uv run pytest`
5. Run linting: `uv run ruff check .`
6. Execute CLI: `maverick run` (optionally run `maverick status <workflow-id>` or `readiness-check https://github.com/owner/repo` for legacy debugging)

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
- **AutomatePhaseTasksWorkflow**: Orchestrates sequential execution of Speckit `tasks.md` phases with checkpoint management
- **MultiTaskOrchestrationWorkflow**: Processes multiple task files sequentially through all phases with fail-fast behavior and interactive approval gates
- **PR CI Automation**: Creates/monitors/merges pull requests with deterministic CI status handling (used as activity within workflows)

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
