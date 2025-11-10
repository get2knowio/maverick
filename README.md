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

```bash
# Start Temporal server (separate terminal)
temporal server start-dev

# Start the worker (separate terminal)
uv run maverick-worker

# Run phase automation on your tasks.md
uv run python -m src.cli.readiness --workflow automate-phase-tasks \
  --tasks-md-path /path/to/specs/feature/tasks.md \
  --repo-path /path/to/repo \
  --branch feature-branch

# Resume after a failure (automatically skips completed phases)
uv run python -m src.cli.readiness --workflow automate-phase-tasks \
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

Orchestrates sequential processing of multiple task files through all phases (initialize, implement, review/fix, PR/CI/merge) with optional interactive approval gates and resume capability after worker restarts.

**What it does:**
- ✓ Processes multiple task files sequentially through all phases
- ✓ Calls AutomatePhaseTasksWorkflow as child workflow for each task
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
# Start Temporal server (separate terminal)
temporal server start-dev

# Start the worker (separate terminal)
uv run maverick-worker

# Run orchestration for multiple task files (batch mode)
uv run maverick-orchestrate run \
  task1.md task2.md task3.md \
  --repo-path /path/to/repo \
  --branch feature-001

# Run with interactive mode (pause after each task)
uv run maverick-orchestrate run \
  task1.md task2.md \
  --repo-path /path/to/repo \
  --branch feature-001 \
  --interactive

# Query progress of running workflow
uv run maverick-orchestrate query --workflow-id orchestrate-abc123

# Send continue signal to resume paused workflow
uv run maverick-orchestrate continue --workflow-id orchestrate-abc123

# Skip current task in paused workflow
uv run maverick-orchestrate skip --workflow-id orchestrate-abc123
```

**Usage patterns:**

Automated batch processing:
```bash
# Process 5 task files without interaction
uv run maverick-orchestrate run \
  tasks/feature-1.md tasks/feature-2.md tasks/feature-3.md \
  tasks/feature-4.md tasks/feature-5.md \
  --repo-path /workspace/myrepo \
  --branch feature-batch-001 \
  --retry-limit 3
```

Interactive workflow with manual approval:
```bash
# Start workflow in interactive mode
uv run maverick-orchestrate run \
  tasks/critical-feature.md \
  --repo-path /workspace/myrepo \
  --branch feature-critical-001 \
  --interactive \
  --workflow-id critical-task-001

# In separate terminal, monitor progress
uv run maverick-orchestrate query --workflow-id critical-task-001

# After reviewing task 1 results, continue to task 2
uv run maverick-orchestrate continue --workflow-id critical-task-001

# Or skip task 2 if needed
uv run maverick-orchestrate skip --workflow-id critical-task-001
```

Resume after worker restart:
```bash
# Start workflow
uv run maverick-orchestrate run \
  tasks/t1.md tasks/t2.md tasks/t3.md \
  --repo-path /workspace/myrepo \
  --branch feature-resume-test \
  --workflow-id resume-test-001

# Worker crashes or restarts during task 2
# Temporal automatically resumes workflow from correct state
# Task 1 results preserved, task 2 continues from where it left off
```

**Configuration:**
- `--retry-limit`: Maximum retry attempts for phase execution (1-10, default: 3)
- `--interactive`: Enable interactive mode with pause/resume between tasks
- `--default-model`: Override AI model for all phases
- `--default-agent-profile`: Override agent profile for all phases
- `--workflow-id`: Reuse same ID to resume from checkpoint

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
- Full specification: `specs/001-multi-task-orchestration/spec.md`
- Data model: `specs/001-multi-task-orchestration/data-model.md`
- Quick start guide: `specs/001-multi-task-orchestration/quickstart.md`
- Implementation: `src/workflows/multi_task_orchestration.py`

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
timeout 15 uv run pytest

# Unit tests only
timeout 15 uv run pytest tests/unit/

# Integration tests only
timeout 15 uv run pytest tests/integration/

# With coverage
timeout 15 uv run pytest --cov=src
```

Adjust the timeout window when suites need longer to finish, but every pytest invocation MUST include a `timeout` wrapper to catch hanging tests.

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
4. Run tests: `timeout 15 uv run pytest`
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
