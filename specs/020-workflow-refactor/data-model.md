# Data Model: Workflow Refactor to Python-Orchestrated Pattern

**Feature**: 020-workflow-refactor
**Date**: 2025-12-18
**Status**: Complete

## Overview

This document defines the data model for the workflow refactor. Most entities already exist in the codebase; this document identifies which are reused, which need extensions, and the one new entity (GitRunner).

---

## Existing Entities (No Changes Required)

### FlyWorkflow Models (src/maverick/workflows/fly.py)

| Entity | Type | Purpose |
|--------|------|---------|
| `WorkflowStage` | Enum | 8 workflow stages: INIT, IMPLEMENTATION, VALIDATION, CODE_REVIEW, CONVENTION_UPDATE, PR_CREATION, COMPLETE, FAILED |
| `FlyConfig` | Pydantic (frozen) | Configuration: parallel_reviews, max_validation_attempts, coderabbit_enabled, auto_merge, notification_on_complete |
| `FlyInputs` | Pydantic (frozen) | Inputs: branch_name, task_file, skip_review, skip_pr, draft_pr, base_branch |
| `WorkflowState` | Pydantic (mutable) | State tracking: stage, branch, results, pr_url, errors, timestamps |
| `FlyResult` | Pydantic (frozen) | Result: success, state, summary, token_usage, total_cost_usd |
| `FlyProgressEvent` | Union type | Events: FlyWorkflowStarted, FlyStageStarted, FlyStageCompleted, FlyWorkflowCompleted, FlyWorkflowFailed |

### RefuelWorkflow Models (src/maverick/workflows/refuel.py)

| Entity | Type | Purpose |
|--------|------|---------|
| `GitHubIssue` | dataclass (frozen) | Issue data: number, title, body, labels, assignee, url |
| `IssueStatus` | Enum | Lifecycle: PENDING, IN_PROGRESS, FIXED, FAILED, SKIPPED |
| `RefuelInputs` | dataclass (frozen) | Inputs: label, limit, parallel, dry_run, auto_assign |
| `IssueProcessingResult` | dataclass (frozen) | Per-issue result: issue, status, branch, pr_url, error, duration_ms, agent_usage |
| `RefuelResult` | dataclass (frozen) | Aggregate result: success, issues_found/processed/fixed/failed/skipped, results, total_duration_ms, total_cost_usd |
| `RefuelConfig` | Pydantic (frozen) | Config: default_label, branch_prefix, link_pr_to_issue, close_on_merge, skip_if_assigned, max_parallel |
| `RefuelProgressEvent` | Union type | Events: RefuelStarted, IssueProcessingStarted, IssueProcessingCompleted, RefuelCompleted |

### Runner Models (src/maverick/runners/models.py)

| Entity | Type | Purpose |
|--------|------|---------|
| `CommandResult` | dataclass (frozen) | Command output: returncode, stdout, stderr, duration_ms, timed_out |
| `StreamLine` | dataclass (frozen) | Streaming output: content, stream (stdout/stderr), timestamp_ms |
| `ValidationStage` | dataclass (frozen) | Stage config: name, command, fixable, fix_command, timeout_seconds |
| `StageResult` | dataclass (frozen) | Stage result: stage_name, passed, output, duration_ms, fix_attempts, errors |
| `ValidationOutput` | dataclass (frozen) | Aggregate: success, stages, total_duration_ms |
| `GitHubIssue` | dataclass (frozen) | GitHub issue: number, title, body, labels, state, assignees, url |
| `PullRequest` | dataclass (frozen) | PR data: number, title, body, state, url, head_branch, base_branch, mergeable, draft |
| `CheckStatus` | dataclass (frozen) | CI status: name, status, conclusion, url |
| `CodeRabbitFinding` | dataclass (frozen) | Finding: file, line, severity, message, suggestion, category |
| `CodeRabbitResult` | dataclass (frozen) | Review result: findings, summary, raw_output, warnings |
| `ParsedError` | dataclass (frozen) | Error info: file, line, message, column, severity, code |

### Agent Models (src/maverick/agents/result.py, base.py)

| Entity | Type | Purpose |
|--------|------|---------|
| `AgentUsage` | dataclass (frozen) | Token tracking: input_tokens, output_tokens, total_cost_usd, duration_ms |
| `AgentResult` | dataclass (frozen) | Execution result: success, output, usage, metadata, errors |

---

## New Entity: GitRunner

**Location**: `src/maverick/runners/git.py` (NEW)

### GitResult

```python
@dataclass(frozen=True, slots=True)
class GitResult:
    """Result of a git operation.

    Attributes:
        success: True if operation succeeded (exit code 0).
        output: Combined stdout output from git.
        error: Error message if operation failed.
        duration_ms: Operation duration in milliseconds.
    """
    success: bool
    output: str
    error: str | None
    duration_ms: int
```

### GitRunner Interface

```python
class GitRunner:
    """Execute git operations via subprocess.

    Provides async git operations without AI involvement:
    - Branch creation and checkout
    - Committing changes
    - Pushing to remote
    - Getting diff output for commit message generation

    All operations use CommandRunner internally for timeout handling
    and proper error management.
    """

    def __init__(
        self,
        cwd: Path | None = None,
        command_runner: CommandRunner | None = None,
    ) -> None:
        """Initialize GitRunner.

        Args:
            cwd: Working directory for git operations.
            command_runner: Optional CommandRunner instance (for testing).
        """

    async def create_branch(
        self,
        branch_name: str,
        from_ref: str = "HEAD",
    ) -> GitResult:
        """Create and checkout a new branch.

        Args:
            branch_name: Name for the new branch.
            from_ref: Starting point for the branch (default: HEAD).

        Returns:
            GitResult with success status and any output.
        """

    async def checkout(self, ref: str) -> GitResult:
        """Checkout an existing branch or commit.

        Args:
            ref: Branch name, tag, or commit SHA to checkout.

        Returns:
            GitResult with success status.
        """

    async def commit(
        self,
        message: str,
        allow_empty: bool = False,
    ) -> GitResult:
        """Create a commit with staged changes.

        Args:
            message: Commit message.
            allow_empty: Allow commit with no changes.

        Returns:
            GitResult with success status.
        """

    async def push(
        self,
        remote: str = "origin",
        branch: str | None = None,
        force: bool = False,
        set_upstream: bool = False,
    ) -> GitResult:
        """Push commits to remote.

        Args:
            remote: Remote name (default: origin).
            branch: Branch to push (default: current branch).
            force: Force push (use with caution).
            set_upstream: Set upstream tracking.

        Returns:
            GitResult with success status.
        """

    async def diff(
        self,
        base: str = "HEAD",
        staged: bool = True,
    ) -> str:
        """Get diff output for commit message generation.

        Args:
            base: Base ref for diff comparison.
            staged: If True, show staged changes only.

        Returns:
            Diff output as string.
        """

    async def add(
        self,
        paths: list[str] | None = None,
        all: bool = False,
    ) -> GitResult:
        """Stage files for commit.

        Args:
            paths: Specific paths to stage.
            all: Stage all changes (-A flag).

        Returns:
            GitResult with success status.
        """

    async def status(self) -> GitResult:
        """Get repository status.

        Returns:
            GitResult with status output.
        """
```

---

## Entity Relationships

```
FlyWorkflow
├── FlyConfig (configuration)
├── FlyInputs (inputs)
├── WorkflowState (mutable state during execution)
├── FlyResult (final output)
├── FlyProgressEvent (progress events during execution)
└── Dependencies:
    ├── GitRunner (branch creation, commit, push)
    ├── ValidationRunner (format, lint, build, test)
    ├── GitHubCLIRunner (PR creation, issue management)
    ├── CodeRabbitRunner (optional code review)
    ├── ImplementerAgent (code implementation)
    ├── CodeReviewerAgent (review interpretation)
    ├── CommitMessageGenerator (commit messages)
    └── PRDescriptionGenerator (PR body)

RefuelWorkflow
├── RefuelConfig (configuration)
├── RefuelInputs (inputs)
├── IssueProcessingResult (per-issue result)
├── RefuelResult (aggregate output)
├── RefuelProgressEvent (progress events)
└── Dependencies:
    ├── GitRunner (branch creation, commit, push)
    ├── GitHubCLIRunner (issue fetching, PR creation)
    ├── ValidationRunner (validation after fixes)
    ├── IssueFixerAgent (issue fixing)
    └── CommitMessageGenerator (commit messages)
```

---

## State Transitions

### FlyWorkflow Stage Transitions

```
INIT ──────────────────────→ IMPLEMENTATION
  │                              │
  │ (branch creation failure)    │
  └─────────────────→ FAILED     │
                                 │
IMPLEMENTATION ────────────→ VALIDATION
  │                              │
  │ (agent error)                │
  └─────────────────→ FAILED     │
                                 │
VALIDATION ────────────────→ CODE_REVIEW
  │                              │
  │ (exhausted retries)          │ (skip_review=True)
  │ [continue with draft PR]     └──────────────────→ PR_CREATION
  │                              │
  └────────────────────────→ CODE_REVIEW
                                 │
CODE_REVIEW ───────────────→ CONVENTION_UPDATE
  │                              │
  │ (coderabbit unavailable)     │
  │ [skip with warning]          │
  └──────────────────────────────┘
                                 │
CONVENTION_UPDATE ─────────→ PR_CREATION
                                 │
PR_CREATION ───────────────→ COMPLETE
  │                              │
  │ (PR creation failure)        │
  └─────────────────→ FAILED     │
                                 │
COMPLETE ──────────────────→ [terminal]
FAILED ────────────────────→ [terminal]
```

### RefuelWorkflow Issue Processing States

```
PENDING ───────────────────→ IN_PROGRESS
  │                              │
  │ (skip_if_assigned)           │
  └─────────────→ SKIPPED        │
                                 │
IN_PROGRESS ───────────────→ FIXED
  │                              │
  │ (agent error, validation     │
  │  failure after retries)      │
  └─────────────→ FAILED         │
                                 │
FIXED ─────────────────────→ [terminal, PR created]
FAILED ────────────────────→ [terminal, error recorded]
SKIPPED ───────────────────→ [terminal, no processing]
```

---

## Validation Rules

### FlyInputs Validation

| Field | Constraint | Error |
|-------|------------|-------|
| branch_name | min_length=1 | "Branch name cannot be empty" |
| base_branch | default="main" | N/A |
| task_file | Path or None | Existence checked at runtime |

### FlyConfig Validation

| Field | Constraint | Error |
|-------|------------|-------|
| max_validation_attempts | ge=1, le=10 | "Must be between 1 and 10" |

### RefuelConfig Validation

| Field | Constraint | Error |
|-------|------------|-------|
| branch_prefix | must end with "/" or "-" | "branch_prefix must end with '/' or '-'" |
| max_parallel | ge=1, le=10 | "Must be between 1 and 10" |

### GitResult Validation

| Field | Constraint | Error |
|-------|------------|-------|
| duration_ms | ge=0 | "Duration cannot be negative" |
| error | None if success=True | Invariant enforced at construction |

---

## Invariants

### FlyWorkflowState

- `stage` must transition forward through WorkflowStage enum (no backward transitions)
- `completed_at` is None until stage is COMPLETE or FAILED
- `pr_url` is None until PR_CREATION stage succeeds
- `errors` accumulates; items are never removed

### RefuelResult

- `issues_processed == issues_fixed + issues_failed`
- `len(results) == issues_found` (after limit applied)
- `success == True` only if `issues_failed == 0`

### IssueProcessingResult

- If `status == FIXED`: `branch` and `pr_url` must be non-None
- If `status == FAILED`: `error` must be non-None
- If `status == SKIPPED`: `branch`, `pr_url`, `error` should be None

---

## Token Usage Aggregation

Token usage is aggregated at the workflow level from all agent and generator executions:

```python
def aggregate_usage(usages: list[AgentUsage]) -> AgentUsage:
    """Aggregate multiple usage records into single summary."""
    return AgentUsage(
        input_tokens=sum(u.input_tokens for u in usages),
        output_tokens=sum(u.output_tokens for u in usages),
        total_cost_usd=sum(u.total_cost_usd or 0.0 for u in usages),
        duration_ms=sum(u.duration_ms for u in usages),
    )
```

FlyWorkflow aggregates from:
- ImplementerAgent.execute() - code implementation
- ValidationWorkflow (if fix agent invoked)
- CodeReviewerAgent.execute() - review interpretation
- CommitMessageGenerator.generate() - commit messages (multiple calls)
- PRDescriptionGenerator.generate() - PR body

RefuelWorkflow aggregates from (per issue):
- IssueFixerAgent.execute() - issue fixing
- ValidationWorkflow (if fix agent invoked)
- CommitMessageGenerator.generate() - commit message
