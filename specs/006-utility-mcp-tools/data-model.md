# Data Model: Utility MCP Tools

**Feature Branch**: `006-utility-mcp-tools`
**Date**: 2025-12-15
**Status**: Complete

## Overview

This document defines the data models for the Utility MCP Tools feature, including configuration models, tool input/output schemas, and response types.

## Configuration Models

### NotificationConfig (Existing - Extended)

**Location**: `src/maverick/config.py` (existing)

The existing `NotificationConfig` model is sufficient for notification tools:

```python
class NotificationConfig(BaseModel):
    """Settings for ntfy-based push notifications."""
    enabled: bool = False
    server: str = "https://ntfy.sh"
    topic: str | None = None
```

No changes needed - this config is already available via `MaverickConfig.notifications`.

### ValidationConfig (New)

**Location**: `src/maverick/config.py`

```python
class ValidationConfig(BaseModel):
    """Settings for validation commands.

    Attributes:
        format_cmd: Command to run for formatting (default: ruff format .)
        lint_cmd: Command to run for linting (default: ruff check --fix .)
        typecheck_cmd: Command to run for type checking (default: mypy .)
        test_cmd: Command to run for tests (default: pytest -x --tb=short)
        timeout_seconds: Maximum time per validation command (default: 300s)
        max_errors: Maximum errors to return from parse (default: 50)
    """
    format_cmd: list[str] = Field(default_factory=lambda: ["ruff", "format", "."])
    lint_cmd: list[str] = Field(default_factory=lambda: ["ruff", "check", "--fix", "."])
    typecheck_cmd: list[str] = Field(default_factory=lambda: ["mypy", "."])
    test_cmd: list[str] = Field(default_factory=lambda: ["pytest", "-x", "--tb=short"])
    timeout_seconds: int = Field(default=300, ge=30, le=600)
    max_errors: int = Field(default=50, ge=1, le=500)
```

**Note**: MaverickConfig will need a new field:
```python
validation: ValidationConfig = Field(default_factory=ValidationConfig)
```

## Tool Input Schemas

### Notification Tools

#### send_notification

```python
@tool(
    "send_notification",
    "Send a custom push notification via ntfy.sh",
    {
        "message": str,      # Required: notification body
        "title": str,        # Optional: notification title
        "priority": str,     # Optional: min|low|default|high|urgent
        "tags": list[str],   # Optional: emoji tags
    },
)
```

**Input Validation**:
- `message`: Required, non-empty string
- `priority`: Must be one of: "min", "low", "default", "high", "urgent"
- `tags`: List of strings, used as ntfy emoji tags

#### send_workflow_update

```python
@tool(
    "send_workflow_update",
    "Send a workflow progress notification with stage-appropriate formatting",
    {
        "stage": str,         # Required: workflow stage name
        "message": str,       # Required: update message
        "workflow_name": str, # Optional: workflow identifier
    },
)
```

**Stage Mapping**:
| Stage | Priority | Tags |
|-------|----------|------|
| "start" | "default" | ["rocket"] |
| "implementation" | "default" | ["hammer"] |
| "review" | "default" | ["mag"] |
| "validation" | "default" | ["white_check_mark"] |
| "complete" | "high" | ["tada"] |
| "error" | "urgent" | ["x", "warning"] |

### Git Tools

#### git_current_branch

```python
@tool(
    "git_current_branch",
    "Get the current git branch name",
    {},  # No parameters
)
```

#### git_create_branch

```python
@tool(
    "git_create_branch",
    "Create and checkout a new git branch",
    {
        "name": str,   # Required: branch name
        "base": str,   # Optional: base branch (default: current branch)
    },
)
```

**Input Validation**:
- `name`: Required, valid git branch name (no spaces, special chars)
- `base`: Optional, existing branch name

#### git_commit

```python
@tool(
    "git_commit",
    "Create a git commit with conventional commit format",
    {
        "message": str,    # Required: commit description
        "type": str,       # Optional: feat|fix|docs|style|refactor|test|chore
        "scope": str,      # Optional: scope in parentheses
        "breaking": bool,  # Optional: adds ! for breaking changes
    },
)
```

**Conventional Commit Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting
- `refactor`: Code restructure
- `test`: Test addition/modification
- `chore`: Maintenance

#### git_push

```python
@tool(
    "git_push",
    "Push commits to remote repository",
    {
        "set_upstream": bool,  # Optional: set upstream tracking (default: false)
    },
)
```

#### git_diff_stats

```python
@tool(
    "git_diff_stats",
    "Get statistics about uncommitted changes",
    {},  # No parameters
)
```

### Validation Tools

#### run_validation

```python
@tool(
    "run_validation",
    "Run project validation commands (format, lint, build, test)",
    {
        "types": list[str],  # Required: list of validation types
    },
)
```

**Valid Types**: `["format", "lint", "typecheck", "test"]`

**Note**: "build" in spec maps to "typecheck" (mypy) for Python projects.

#### parse_validation_output

```python
@tool(
    "parse_validation_output",
    "Parse validation command output into structured errors",
    {
        "output": str,  # Required: raw validation output
        "type": str,    # Required: validation type (lint, typecheck)
    },
)
```

## Tool Response Schemas

### Success Responses

All successful responses follow MCP format:

```python
{
    "content": [
        {"type": "text", "text": "<json-string>"}
    ]
}
```

#### NotificationResponse

```python
{
    "success": true,
    "message": "Notification sent" | "Notifications disabled" | "Notification sent (after retry)",
    "notification_id": str | null,  # ntfy response ID if available
}
```

#### GitBranchResponse

```python
{
    "branch": str,  # Branch name or "(detached)"
}
```

#### GitCreateBranchResponse

```python
{
    "success": true,
    "branch": str,
    "base": str,
}
```

#### GitCommitResponse

```python
{
    "success": true,
    "commit_sha": str,
    "message": str,
}
```

#### GitPushResponse

```python
{
    "success": true,
    "commits_pushed": int,
    "remote": str,
    "branch": str,
}
```

#### GitDiffStatsResponse

```python
{
    "files_changed": int,
    "insertions": int,
    "deletions": int,
}
```

#### ValidationRunResponse

```python
{
    "success": bool,
    "results": [
        {
            "type": str,       # "format", "lint", "typecheck", "test"
            "success": bool,
            "output": str,     # Raw command output (truncated if large)
            "duration_ms": int,
        }
    ],
}
```

#### ValidationParseResponse

```python
{
    "errors": [
        {
            "file": str,
            "line": int,
            "column": int | null,
            "message": str,
            "code": str | null,      # Error code (e.g., "E501", "arg-type")
            "severity": str | null,  # "error", "warning", "note"
        }
    ],
    "total_count": int,
    "truncated": bool,
}
```

### Error Responses

All error responses include `isError: true`:

```python
{
    "content": [
        {
            "type": "text",
            "text": "{\"isError\": true, \"message\": \"...\", \"error_code\": \"...\"}"
        }
    ]
}
```

#### Error Codes

| Code | Description | Used By |
|------|-------------|---------|
| `NOT_A_REPOSITORY` | Not inside a git repository | git_* tools |
| `BRANCH_EXISTS` | Branch name already exists | git_create_branch |
| `BRANCH_NOT_FOUND` | Base branch doesn't exist | git_create_branch |
| `NOTHING_TO_COMMIT` | No staged changes | git_commit |
| `DETACHED_HEAD` | Cannot push from detached HEAD | git_push |
| `AUTHENTICATION_REQUIRED` | Git credentials missing/expired | git_push |
| `NETWORK_ERROR` | Network connectivity issue | git_push, notification tools |
| `TIMEOUT` | Operation timed out | run_validation |
| `CONFIG_MISSING` | Required configuration not set | run_validation |
| `INVALID_INPUT` | Invalid parameter value | All tools |
| `INTERNAL_ERROR` | Unexpected error | All tools |

## Entity Relationships

```
MaverickConfig
├── notifications: NotificationConfig
│   └── used by: send_notification, send_workflow_update
└── validation: ValidationConfig (NEW)
    └── used by: run_validation, parse_validation_output

Tool Responses (all JSON serialized)
├── Success: {"content": [{"type": "text", "text": "..."}]}
└── Error: {"content": [{"type": "text", "text": "{\"isError\": true, ...}"}]}
```

## State Transitions

### Notification State

```
┌─────────────────┐
│ Check Config    │
└────────┬────────┘
         │
    ┌────▼────┐     ┌──────────────────┐
    │Disabled?│─Yes─▶ Return Success   │
    └────┬────┘     │ (disabled msg)   │
         │No        └──────────────────┘
         ▼
┌─────────────────┐
│ Send Request    │
└────────┬────────┘
         │
    ┌────▼────┐     ┌──────────────────┐
    │Success? │─Yes─▶ Return Success   │
    └────┬────┘     └──────────────────┘
         │No
         ▼
┌─────────────────┐
│ Retry (1-2x)    │
└────────┬────────┘
         │
    ┌────▼────┐     ┌──────────────────┐
    │Success? │─Yes─▶ Return Success   │
    └────┬────┘     │ (with retry msg) │
         │No        └──────────────────┘
         ▼
┌──────────────────┐
│ Return Success   │
│ (with warning)   │
│ Log failure      │
└──────────────────┘
```

### Validation State

```
┌─────────────────┐
│ Validate Config │
└────────┬────────┘
         │
    ┌────▼────┐     ┌──────────────────┐
    │Missing? │─Yes─▶ Return Error     │
    └────┬────┘     │ CONFIG_MISSING   │
         │No        └──────────────────┘
         ▼
┌─────────────────┐
│ For each type   │◀──────┐
└────────┬────────┘       │
         │                │
         ▼                │
┌─────────────────┐       │
│ Run command     │       │
└────────┬────────┘       │
         │                │
    ┌────▼────┐           │
    │Timeout? │─Yes─▶ Kill process, record timeout
    └────┬────┘           │
         │No              │
         ▼                │
┌─────────────────┐       │
│ Record result   │───────┘
└────────┬────────┘
         │ All done
         ▼
┌─────────────────┐
│ Return results  │
└─────────────────┘
```

## Validation Rules

### Input Validation

| Field | Rule | Error |
|-------|------|-------|
| `message` (notification) | Non-empty string | INVALID_INPUT |
| `priority` | One of: min, low, default, high, urgent | INVALID_INPUT |
| `name` (branch) | Valid git ref name | INVALID_INPUT |
| `message` (commit) | Non-empty string | INVALID_INPUT |
| `type` (commit) | One of: feat, fix, docs, etc. | INVALID_INPUT |
| `types` (validation) | Non-empty list of valid types | INVALID_INPUT |
| `output` (parse) | Non-empty string | INVALID_INPUT |

### Business Rules

1. **Notification graceful degradation**: Never raise exceptions; always return success with appropriate message
2. **Git prerequisite check**: Verify git repo before any git operation
3. **Commit requires staged changes**: Return error if nothing to commit
4. **Push requires branch**: Return error if in detached HEAD
5. **Validation timeout**: Kill process after configured timeout
6. **Error truncation**: Limit parsed errors to max_errors config
