# Data Model: Refuel Workflow Interface

**Date**: 2025-12-15
**Feature Branch**: `010-refuel-workflow`

## Entity Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  RefuelInputs   │────>│  RefuelWorkflow │────>│  RefuelResult   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │                       │
                               │ yields                │ contains
                               ▼                       ▼
                        ┌─────────────────┐   ┌─────────────────────┐
                        │ProgressEvents   │   │ IssueProcessingResult│
                        │ - RefuelStarted │   └─────────────────────┘
                        │ - IssueProcStart│            │
                        │ - IssueProcEnd  │            │ references
                        │ - RefuelComplete│            ▼
                        └─────────────────┘   ┌─────────────────┐
                                              │   GitHubIssue   │
                                              └─────────────────┘
```

## Entities

### GitHubIssue

Minimal representation of a GitHub issue for refuel workflow.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| number | int | Yes | Issue number (e.g., 123) |
| title | str | Yes | Issue title |
| body | str \| None | No | Issue body/description |
| labels | list[str] | Yes | List of label names |
| assignee | str \| None | No | Assigned username |
| url | str | Yes | Full GitHub issue URL |

**Immutability**: `@dataclass(frozen=True, slots=True)`

**Validation**: None (simple value object)

---

### IssueStatus

Enum representing issue processing lifecycle.

| Value | Description |
|-------|-------------|
| PENDING | Issue identified, not yet processed |
| IN_PROGRESS | Currently being processed by agent |
| FIXED | Successfully fixed, PR created |
| FAILED | Processing failed (with error details) |
| SKIPPED | Skipped due to policy (dry_run, assigned, etc.) |

**State Transitions**:
```
PENDING → IN_PROGRESS → FIXED
                     → FAILED
       → SKIPPED (dry_run or skip_if_assigned)
```

---

### RefuelInputs

Configuration for a single workflow execution.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| label | str | "tech-debt" | Label filter for discovering issues |
| limit | int | 5 | Maximum issues to process |
| parallel | bool | False | Enable parallel processing |
| dry_run | bool | False | Preview mode (no changes) |
| auto_assign | bool | True | Auto-assign issues to self |

**Immutability**: `@dataclass(frozen=True, slots=True)`

**Validation**:
- `limit` must be positive integer (≥1)
- `label` must be non-empty string

---

### IssueProcessingResult

Outcome of processing a single issue.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| issue | GitHubIssue | Yes | The processed issue |
| status | IssueStatus | Yes | Processing outcome |
| branch | str \| None | No | Created branch name (if any) |
| pr_url | str \| None | No | Created PR URL (if any) |
| error | str \| None | No | Error message (if FAILED) |
| duration_ms | int | Yes | Processing duration |
| agent_usage | AgentUsage | Yes | Token/cost metrics |

**Immutability**: `@dataclass(frozen=True, slots=True)`

**Invariants**:
- If `status == FIXED`: `branch` and `pr_url` must be non-None
- If `status == FAILED`: `error` must be non-None
- If `status == SKIPPED`: `branch`, `pr_url`, `error` should be None

---

### RefuelResult

Aggregate outcome of workflow execution.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| success | bool | Yes | Overall workflow success |
| issues_found | int | Yes | Total issues matching label |
| issues_processed | int | Yes | Issues actually processed |
| issues_fixed | int | Yes | Issues successfully fixed |
| issues_failed | int | Yes | Issues that failed |
| issues_skipped | int | Yes | Issues skipped |
| results | list[IssueProcessingResult] | Yes | Per-issue outcomes |
| total_duration_ms | int | Yes | Total execution time |
| total_cost_usd | float | Yes | Total API cost |

**Immutability**: `@dataclass(frozen=True, slots=True)`

**Invariants**:
- `issues_processed == issues_fixed + issues_failed`
- `len(results) == issues_found` (after filtering by limit)
- `success == True` if `issues_failed == 0` and no exceptions

---

### RefuelConfig

Persistent configuration for refuel workflow (Pydantic BaseModel).

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| default_label | str | "tech-debt" | Default label filter |
| branch_prefix | str | "fix/issue-" | Branch naming prefix |
| link_pr_to_issue | bool | True | Add "Fixes #N" to PR |
| close_on_merge | bool | False | Close issue when PR merges |
| skip_if_assigned | bool | True | Skip already-assigned issues |
| max_parallel | int | 3 | Max concurrent issue processing |

**Model**: `pydantic.BaseModel` with `frozen=True`

**Validation**:
- `max_parallel` must be between 1 and 10
- `branch_prefix` must end with "/" or "-"

---

## Progress Events

All events use `@dataclass(frozen=True, slots=True)`.

### RefuelStarted

| Field | Type | Description |
|-------|------|-------------|
| inputs | RefuelInputs | Workflow input configuration |
| issues_found | int | Number of matching issues |

### IssueProcessingStarted

| Field | Type | Description |
|-------|------|-------------|
| issue | GitHubIssue | Issue being processed |
| index | int | Current index (1-based) |
| total | int | Total issues to process |

### IssueProcessingCompleted

| Field | Type | Description |
|-------|------|-------------|
| result | IssueProcessingResult | Processing outcome |

### RefuelCompleted

| Field | Type | Description |
|-------|------|-------------|
| result | RefuelResult | Aggregate workflow result |

---

## Type Alias

```python
RefuelProgressEvent = (
    RefuelStarted
    | IssueProcessingStarted
    | IssueProcessingCompleted
    | RefuelCompleted
)
```

---

## Relationships

1. **RefuelWorkflow** receives **RefuelInputs** and yields **RefuelProgressEvent**
2. **RefuelResult** contains list of **IssueProcessingResult**
3. **IssueProcessingResult** references **GitHubIssue** and **AgentUsage**
4. **RefuelStarted** embeds **RefuelInputs**
5. **RefuelConfig** integrates into **MaverickConfig** as nested section
