# Data Model: DSL-Based Built-in Workflow Implementation

**Spec**: 026-dsl-builtin-workflows
**Date**: 2025-12-20

This document defines the data models, entities, and their relationships for the DSL-based built-in workflow implementation.

## Entity Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Workflow Execution                               │
├─────────────────────────────────────────────────────────────────────────┤
│  WorkflowFile ──────────> StepRecordUnion ──────> StepResult            │
│       │                        │                       │                 │
│       │                        │                       │                 │
│       v                        v                       v                 │
│  InputDefinition         AgentStepRecord         WorkflowResult          │
│                          GenerateStepRecord                              │
│                          SubWorkflowStepRecord                           │
│                          BranchStepRecord                                │
│                          ParallelStepRecord                              │
│                          ValidateStepRecord                              │
│                          PythonStepRecord                                │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         Python Actions                                   │
├─────────────────────────────────────────────────────────────────────────┤
│  ActionResult ─────────> WorkspaceState                                  │
│       │                  GitResult                                       │
│       │                  GitHubIssueResult                               │
│       │                  PRCreationResult                                │
│       v                  ValidationReportResult                          │
│  ActionContext           ReviewContextResult                             │
│                          RefuelSummaryResult                             │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                         Progress Events                                  │
├─────────────────────────────────────────────────────────────────────────┤
│  ProgressEvent ─────────> WorkflowStarted                                │
│       │                   WorkflowCompleted                              │
│       │                   StepStarted                                    │
│       v                   StepCompleted                                  │
│  FlyProgressEvent         CheckpointSaved                                │
│  RefuelProgressEvent                                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

## Core Entities

### 1. WorkflowFile (Existing - Spec 24)

Already defined in `maverick.dsl.serialization.schema`. No changes needed.

```python
class WorkflowFile(BaseModel):
    version: str                              # "1.0"
    name: str                                 # "fly", "refuel", etc.
    description: str                          # Human-readable description
    inputs: dict[str, InputDefinition]        # Input parameter declarations
    steps: list[StepRecordUnion]              # Ordered step definitions
```

### 2. StepRecordUnion (Existing - Spec 24)

Already defined. Discriminated union of all step types.

```python
StepRecordUnion = Union[
    PythonStepRecord,
    AgentStepRecord,
    GenerateStepRecord,
    ValidateStepRecord,
    SubWorkflowStepRecord,
    BranchStepRecord,
    ParallelStepRecord,
]
```

### 3. ComponentRegistry Extensions

**New: Agent Registry Extension**

```python
@dataclass(frozen=True, slots=True)
class AgentRegistration:
    """Agent registration entry."""
    name: str                                 # "implementer", "code_reviewer"
    agent_class: type[MaverickAgent]          # Agent class (not instance)
    config_factory: Callable[[], Any] | None  # Optional config factory
```

**Updated ComponentRegistry**

```python
class ComponentRegistry:
    actions: TypedRegistry[Callable[..., Any]]
    generators: TypedRegistry[Callable[..., Any]]
    workflows: TypedRegistry[WorkflowFile | Callable]
    context_builders: TypedRegistry[ContextBuilder]       # NEW
    agents: TypedRegistry[type[MaverickAgent]]            # NEW
```

## Python Action Result Models

### 4. WorkspaceState

Result from `init_workspace` action.

```python
@dataclass(frozen=True, slots=True)
class WorkspaceState:
    """State of the workspace after initialization."""
    branch_name: str                          # Current branch name
    base_branch: str                          # Base branch (e.g., "main")
    is_clean: bool                            # Whether workspace is clean
    synced_with_base: bool                    # Whether synced with origin/base
    task_file_path: Path | None               # Detected or provided task file

    # Validation
    # - branch_name: non-empty string
    # - base_branch: non-empty string, defaults to "main"
```

### 5. GitResult

Result from git operations (`git_commit`, `git_push`, `create_git_branch`).

```python
@dataclass(frozen=True, slots=True)
class GitCommitResult:
    """Result of git commit operation."""
    success: bool
    commit_sha: str | None                    # SHA of created commit
    message: str                              # Commit message used
    files_committed: tuple[str, ...]          # List of committed files
    error: str | None                         # Error message if failed

@dataclass(frozen=True, slots=True)
class GitPushResult:
    """Result of git push operation."""
    success: bool
    remote: str                               # Remote name (e.g., "origin")
    branch: str                               # Branch pushed
    upstream_set: bool                        # Whether upstream was set
    error: str | None

@dataclass(frozen=True, slots=True)
class GitBranchResult:
    """Result of branch creation."""
    success: bool
    branch_name: str
    base_branch: str
    created: bool                             # True if created, False if checked out
    error: str | None
```

### 6. GitHubIssueResult

Result from GitHub issue operations.

```python
@dataclass(frozen=True, slots=True)
class FetchedIssue:
    """Single GitHub issue fetched from API."""
    number: int
    title: str
    body: str | None
    labels: tuple[str, ...]
    assignee: str | None
    url: str
    state: str                                # "open", "closed"

@dataclass(frozen=True, slots=True)
class FetchIssuesResult:
    """Result of fetching multiple issues."""
    success: bool
    issues: tuple[FetchedIssue, ...]
    total_count: int                          # Total matching issues
    error: str | None

@dataclass(frozen=True, slots=True)
class FetchSingleIssueResult:
    """Result of fetching a single issue."""
    success: bool
    issue: FetchedIssue | None
    error: str | None
```

### 7. PRCreationResult

Result from PR creation action.

```python
@dataclass(frozen=True, slots=True)
class PRCreationResult:
    """Result of PR creation via GitHub CLI."""
    success: bool
    pr_number: int | None                     # PR number if created
    pr_url: str | None                        # URL to the PR
    title: str                                # Title used
    draft: bool                               # Whether created as draft
    base_branch: str                          # Target branch
    error: str | None
```

### 8. ValidationReportResult

Result from validation and fix operations.

```python
@dataclass(frozen=True, slots=True)
class StageResultEntry:
    """Result of a single validation stage."""
    name: str                                 # "format", "lint", etc.
    passed: bool
    errors: tuple[str, ...]                   # Error messages
    duration_ms: int

@dataclass(frozen=True, slots=True)
class ValidationReportResult:
    """Final validation report from validate_and_fix fragment."""
    passed: bool                              # Overall success
    stages: tuple[StageResultEntry, ...]
    attempts: int                             # Number of fix attempts made
    fixes_applied: tuple[str, ...]            # Descriptions of fixes applied
    remaining_errors: tuple[str, ...]         # Errors that couldn't be fixed
    suggestions: tuple[str, ...]              # Manual fix suggestions
```

### 9. ReviewContextResult

Result from review context gathering.

```python
@dataclass(frozen=True, slots=True)
class PRMetadata:
    """Pull request metadata."""
    number: int | None                        # PR number if exists
    title: str | None
    description: str | None
    author: str | None
    labels: tuple[str, ...]
    base_branch: str

@dataclass(frozen=True, slots=True)
class ReviewContextResult:
    """Gathered context for code review."""
    pr_metadata: PRMetadata
    changed_files: tuple[str, ...]            # List of changed file paths
    diff: str                                 # Full diff content
    commits: tuple[str, ...]                  # Commit messages
    coderabbit_available: bool                # Whether CodeRabbit is configured

@dataclass(frozen=True, slots=True)
class CodeRabbitResult:
    """Result from CodeRabbit review."""
    available: bool
    findings: tuple[dict[str, Any], ...]      # CodeRabbit findings
    error: str | None

@dataclass(frozen=True, slots=True)
class CombinedReviewResult:
    """Combined review results from all sources."""
    review_report: str                        # Markdown report
    issues: tuple[dict[str, Any], ...]        # Consolidated issues
    recommendation: str                       # "approve", "request_changes", "comment"
```

### 10. RefuelSummaryResult

Result from refuel workflow aggregation.

```python
@dataclass(frozen=True, slots=True)
class ProcessedIssueEntry:
    """Result of processing a single issue."""
    issue_number: int
    issue_title: str
    status: str                               # "fixed", "failed", "skipped"
    branch_name: str | None
    pr_url: str | None
    error: str | None

@dataclass(frozen=True, slots=True)
class RefuelSummaryResult:
    """Summary of refuel workflow execution."""
    total_issues: int                         # Total issues found
    processed_count: int                      # Number processed
    success_count: int                        # Number successfully fixed
    failure_count: int                        # Number that failed
    skipped_count: int                        # Number skipped
    issues: tuple[ProcessedIssueEntry, ...]
    pr_urls: tuple[str, ...]                  # All created PR URLs
```

## Context Builder Types

### 11. ContextBuilder Protocol

```python
ContextBuilder: TypeAlias = Callable[[WorkflowContext], Awaitable[dict[str, Any]]]
```

### 12. Context Data Structures

```python
@dataclass(frozen=True, slots=True)
class ImplementationContext:
    """Context for implementer agent."""
    task_description: str                     # Task to implement
    task_file_content: str | None             # Full tasks.md content
    project_structure: str                    # Directory tree
    spec_artifacts: dict[str, str]            # Spec files content
    conventions: str                          # CLAUDE.md content

@dataclass(frozen=True, slots=True)
class ReviewContext:
    """Context for code reviewer agent."""
    diff: str                                 # Git diff
    changed_files: tuple[str, ...]
    conventions: str                          # CLAUDE.md content
    base_branch: str
    pr_metadata: PRMetadata | None
    coderabbit_findings: tuple[dict[str, Any], ...] | None

@dataclass(frozen=True, slots=True)
class IssueFixContext:
    """Context for issue fixer agent."""
    issue_number: int
    issue_title: str
    issue_body: str
    branch_name: str
    related_files: tuple[str, ...]            # Files potentially related to issue
    conventions: str                          # CLAUDE.md content

@dataclass(frozen=True, slots=True)
class CommitMessageContext:
    """Context for commit message generator."""
    diff: str                                 # Git diff
    file_stats: dict[str, Any]                # Insertions/deletions per file
    recent_commits: tuple[str, ...]           # Recent commit messages for style

@dataclass(frozen=True, slots=True)
class PRBodyContext:
    """Context for PR body generator."""
    commits: tuple[str, ...]                  # All commits on branch
    diff_stats: dict[str, Any]                # File change statistics
    task_summary: str | None                  # Summary from task file
    validation_results: ValidationReportResult | None
```

## State Transitions

### Workflow Execution States

```
PENDING ──> STARTED ──> STEP_RUNNING ──> STEP_COMPLETED ──> ... ──> COMPLETED
                              │                                          │
                              │                                          │
                              v                                          v
                         STEP_FAILED ─────────────────────────────> FAILED
```

### Issue Processing States (Refuel)

```
PENDING ──> IN_PROGRESS ──> FIXED ──> (done)
                │
                v
            FAILED / SKIPPED ──> (done)
```

### Validation States

```
PENDING ──> RUNNING ──> PASSED ──> (done)
                │
                v
            FAILED ──> FIXING ──> RETRY ──> RUNNING ──> ...
                                      │
                                      v
                                (max attempts) ──> FAILED_FINAL
```

## Relationships

```
WorkflowFile 1──*> StepRecordUnion
    │
    └── inputs: dict[str, InputDefinition]
    └── steps: list[StepRecordUnion]

ComponentRegistry 1──1> TypedRegistry (actions)
                  1──1> TypedRegistry (generators)
                  1──1> TypedRegistry (workflows)
                  1──1> TypedRegistry (context_builders)
                  1──1> TypedRegistry (agents)

FlyWorkflow uses──> WorkflowFileExecutor
              uses──> ComponentRegistry
              yields> FlyProgressEvent

RefuelWorkflow uses──> WorkflowFileExecutor
               uses──> ComponentRegistry
               yields> RefuelProgressEvent

WorkflowFileExecutor executes> WorkflowFile
                     produces> StepResult
                     produces> WorkflowResult
                     yields> ProgressEvent
```

## Validation Rules

| Entity | Field | Rule |
|--------|-------|------|
| WorkflowFile | version | Must match `^\d+\.\d+$` |
| WorkflowFile | name | Must match `^[a-z][a-z0-9-]{0,63}$` |
| WorkflowFile | steps | At least 1 step; unique step names |
| InputDefinition | default | None if required=True |
| StepRecord | name | Non-empty, unique within workflow |
| GitCommitResult | commit_sha | 40-char hex string if success |
| PRCreationResult | pr_number | Positive integer if success |
| ValidationReportResult | attempts | >= 0 |
| ProcessedIssueEntry | status | One of: "fixed", "failed", "skipped" |

## Index Requirements

N/A - No persistent storage. All data is in-memory during workflow execution.

## Migration Notes

This spec introduces new models but does not require migration of existing data. The new models are:

1. **Action result types**: New frozen dataclasses for Python action return values
2. **Context data structures**: New frozen dataclasses for agent/generator contexts
3. **ComponentRegistry extensions**: Add `context_builders` and `agents` registries

All new types are additive and backward-compatible with existing DSL infrastructure.
