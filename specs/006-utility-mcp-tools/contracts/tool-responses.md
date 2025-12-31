# MCP Tool Response Contracts

**Feature Branch**: `006-utility-mcp-tools`
**Date**: 2025-12-15
**Status**: Complete

This document defines the formal API contracts for all Utility MCP Tools responses.

## Base Response Format

All MCP tool responses follow this structure:

```typescript
interface MCPToolResponse {
  content: Array<{
    type: "text";
    text: string;  // JSON-serialized payload
  }>;
}
```

The `text` field contains JSON with either a success or error payload.

## Notification Tools

### send_notification

**Tool Name**: `send_notification`
**MCP Path**: `mcp__notification-tools__send_notification`

#### Parameters

```typescript
interface SendNotificationParams {
  message: string;        // Required: notification body text
  title?: string;         // Optional: notification title
  priority?: Priority;    // Optional: defaults to "default"
  tags?: string[];        // Optional: ntfy emoji tags
}

type Priority = "min" | "low" | "default" | "high" | "urgent";
```

#### Success Response

```typescript
interface SendNotificationSuccess {
  success: true;
  message: string;  // "Notification sent" | "Notifications disabled" | "Notification sent (after retry)"
  notification_id?: string;  // ntfy response ID if available
  warning?: string;  // Present when notification delivery is uncertain
}
```

#### Example Responses

```json
// Success - notification sent
{"success": true, "message": "Notification sent", "notification_id": "abc123"}

// Success - notifications disabled (graceful degradation)
{"success": true, "message": "Notifications disabled (no topic configured)"}

// Success - with retry warning
{"success": true, "message": "Notification sent (after retry)", "warning": "Initial request timed out"}

// Success - server unreachable (graceful degradation)
{"success": true, "message": "Notification not delivered", "warning": "ntfy.sh server unreachable after 2 attempts"}
```

---

### send_workflow_update

**Tool Name**: `send_workflow_update`
**MCP Path**: `mcp__notification-tools__send_workflow_update`

#### Parameters

```typescript
interface SendWorkflowUpdateParams {
  stage: WorkflowStage;     // Required: workflow stage
  message: string;          // Required: update message
  workflow_name?: string;   // Optional: workflow identifier
}

type WorkflowStage = "start" | "implementation" | "review" | "validation" | "complete" | "error";
```

#### Success Response

Same as `send_notification`.

#### Stage to Priority/Tags Mapping

| Stage | Priority | Tags | Title Format |
|-------|----------|------|--------------|
| start | default | ["rocket"] | "🚀 {workflow_name} Started" |
| implementation | default | ["hammer"] | "🔨 Implementation Update" |
| review | default | ["mag"] | "🔍 Code Review" |
| validation | default | ["white_check_mark"] | "✅ Validation" |
| complete | high | ["tada"] | "🎉 {workflow_name} Complete" |
| error | urgent | ["x", "warning"] | "❌ {workflow_name} Error" |

---

## Git Tools

### git_current_branch

**Tool Name**: `git_current_branch`
**MCP Path**: `mcp__git-tools__git_current_branch`

#### Parameters

```typescript
interface GitCurrentBranchParams {
  // No parameters
}
```

#### Success Response

```typescript
interface GitCurrentBranchSuccess {
  branch: string;  // Branch name or "(detached)"
}
```

#### Error Responses

```typescript
// Not in a git repository
{
  "isError": true,
  "message": "Not inside a git repository",
  "error_code": "NOT_A_REPOSITORY"
}
```

---

### git_create_branch

**Tool Name**: `git_create_branch`
**MCP Path**: `mcp__git-tools__git_create_branch`

#### Parameters

```typescript
interface GitCreateBranchParams {
  name: string;    // Required: new branch name
  base?: string;   // Optional: base branch (default: current branch)
}
```

#### Success Response

```typescript
interface GitCreateBranchSuccess {
  success: true;
  branch: string;  // Created branch name
  base: string;    // Base branch used
}
```

#### Error Responses

```typescript
// Branch already exists
{
  "isError": true,
  "message": "Branch 'feature-x' already exists",
  "error_code": "BRANCH_EXISTS"
}

// Base branch not found
{
  "isError": true,
  "message": "Branch 'develop' not found",
  "error_code": "BRANCH_NOT_FOUND"
}

// Invalid branch name
{
  "isError": true,
  "message": "Invalid branch name: contains spaces",
  "error_code": "INVALID_INPUT"
}
```

---

### git_commit

**Tool Name**: `git_commit`
**MCP Path**: `mcp__git-tools__git_commit`

#### Parameters

```typescript
interface GitCommitParams {
  message: string;      // Required: commit description
  type?: CommitType;    // Optional: conventional commit type
  scope?: string;       // Optional: commit scope
  breaking?: boolean;   // Optional: breaking change flag
}

type CommitType = "feat" | "fix" | "docs" | "style" | "refactor" | "test" | "chore";
```

#### Success Response

```typescript
interface GitCommitSuccess {
  success: true;
  commit_sha: string;  // Full SHA of created commit
  message: string;     // Formatted commit message
}
```

#### Error Responses

```typescript
// Nothing to commit
{
  "isError": true,
  "message": "Nothing to commit (no staged changes)",
  "error_code": "NOTHING_TO_COMMIT"
}

// Invalid commit type
{
  "isError": true,
  "message": "Invalid commit type 'feature'. Use: feat, fix, docs, style, refactor, test, chore",
  "error_code": "INVALID_INPUT"
}
```

---

### git_push

**Tool Name**: `git_push`
**MCP Path**: `mcp__git-tools__git_push`

#### Parameters

```typescript
interface GitPushParams {
  set_upstream?: boolean;  // Optional: set upstream tracking (default: false)
}
```

#### Success Response

```typescript
interface GitPushSuccess {
  success: true;
  commits_pushed: number;
  remote: string;
  branch: string;
}
```

#### Error Responses

```typescript
// Detached HEAD
{
  "isError": true,
  "message": "Cannot push from detached HEAD state. Create a branch first with git_create_branch",
  "error_code": "DETACHED_HEAD"
}

// Authentication required
{
  "isError": true,
  "message": "Authentication failed. Run 'gh auth login' or configure git credentials",
  "error_code": "AUTHENTICATION_REQUIRED"
}

// Network error
{
  "isError": true,
  "message": "Network error: could not connect to remote",
  "error_code": "NETWORK_ERROR"
}
```

---

### git_diff_stats

**Tool Name**: `git_diff_stats`
**MCP Path**: `mcp__git-tools__git_diff_stats`

#### Parameters

```typescript
interface GitDiffStatsParams {
  // No parameters
}
```

#### Success Response

```typescript
interface GitDiffStatsSuccess {
  files_changed: number;
  insertions: number;
  deletions: number;
}
```

#### Example Response

```json
{"files_changed": 3, "insertions": 50, "deletions": 20}

// No changes
{"files_changed": 0, "insertions": 0, "deletions": 0}
```

---

## Validation Tools

### run_validation

**Tool Name**: `run_validation`
**MCP Path**: `mcp__validation-tools__run_validation`

#### Parameters

```typescript
interface RunValidationParams {
  types: ValidationType[];  // Required: validation types to run
}

type ValidationType = "format" | "lint" | "typecheck" | "test";
```

#### Success Response

```typescript
interface RunValidationSuccess {
  success: boolean;  // True if ALL validations passed
  results: ValidationResult[];
}

interface ValidationResult {
  type: ValidationType;
  success: boolean;
  output: string;       // Raw command output (may be truncated)
  duration_ms: number;
  status: "success" | "failed" | "timeout";  // Always present
}
```

#### Error Responses

```typescript
// Configuration missing
{
  "isError": true,
  "message": "Validation commands not configured. Add 'validation' section to maverick.yaml",
  "error_code": "CONFIG_MISSING"
}

// Invalid validation type
{
  "isError": true,
  "message": "Invalid validation type 'build'. Use: format, lint, typecheck, test",
  "error_code": "INVALID_INPUT"
}
```

#### Example Response

```json
{
  "success": false,
  "results": [
    {
      "type": "format",
      "success": true,
      "output": "All files formatted.",
      "duration_ms": 1200
    },
    {
      "type": "lint",
      "success": false,
      "output": "src/main.py:10:5: E501 Line too long...",
      "duration_ms": 2500
    }
  ]
}
```

---

### parse_validation_output

**Tool Name**: `parse_validation_output`
**MCP Path**: `mcp__validation-tools__parse_validation_output`

#### Parameters

```typescript
interface ParseValidationOutputParams {
  output: string;    // Required: raw validation output
  type: ParseType;   // Required: output format type
}

type ParseType = "lint" | "typecheck";
```

#### Success Response

```typescript
interface ParseValidationOutputSuccess {
  errors: ParsedError[];
  total_count: number;
  truncated: boolean;
}

interface ParsedError {
  file: string;
  line: number;
  column?: number;     // May be null for some linters
  message: string;
  code?: string;       // Error code (e.g., "E501", "arg-type")
  severity?: Severity;
}

type Severity = "error" | "warning" | "note";
```

#### Example Response

```json
{
  "errors": [
    {
      "file": "src/main.py",
      "line": 10,
      "column": 5,
      "message": "Line too long (89 > 88)",
      "code": "E501",
      "severity": "error"
    },
    {
      "file": "src/utils.py",
      "line": 25,
      "column": null,
      "message": "Incompatible types in assignment",
      "code": "arg-type",
      "severity": "error"
    }
  ],
  "total_count": 2,
  "truncated": false
}

// Truncated output (>50 errors)
{
  "errors": [...],  // First 50 errors
  "total_count": 1247,
  "truncated": true
}
```

---

## Common Error Codes

All tools may return these common error codes:

| Code | HTTP Equivalent | Description |
|------|-----------------|-------------|
| `NOT_A_REPOSITORY` | 400 | Git operation attempted outside git repo |
| `BRANCH_EXISTS` | 409 | Branch name already exists |
| `BRANCH_NOT_FOUND` | 404 | Referenced branch doesn't exist |
| `NOTHING_TO_COMMIT` | 400 | No staged changes to commit |
| `DETACHED_HEAD` | 400 | Operation requires a branch |
| `AUTHENTICATION_REQUIRED` | 401 | Git credentials missing/expired |
| `NETWORK_ERROR` | 503 | Network connectivity issue |
| `TIMEOUT` | 408 | Operation timed out |
| `CONFIG_MISSING` | 400 | Required configuration not set |
| `INVALID_INPUT` | 400 | Invalid parameter value |
| `INTERNAL_ERROR` | 500 | Unexpected internal error |

---

## Factory Functions

### create_notification_tools_server

```python
def create_notification_tools_server(
    config: NotificationConfig | None = None,
) -> MCPServer:
    """Create MCP server with notification tools.

    Args:
        config: Notification configuration. If None, loads from MaverickConfig.

    Returns:
        Configured MCP server with send_notification and send_workflow_update tools.
    """
```

### create_git_tools_server

```python
def create_git_tools_server(
    cwd: Path | None = None,
    skip_verification: bool = False,
) -> MCPServer:
    """Create MCP server with git utility tools.

    Args:
        cwd: Working directory for git operations.
        skip_verification: Skip git repo verification (for testing).

    Returns:
        Configured MCP server with git_current_branch, git_create_branch,
        git_commit, git_push, git_diff_stats tools.

    Raises:
        GitToolsError: If not in a git repository (unless skip_verification=True).
    """
```

### create_validation_tools_server

```python
def create_validation_tools_server(
    config: ValidationConfig | None = None,
    cwd: Path | None = None,
) -> MCPServer:
    """Create MCP server with validation tools.

    Args:
        config: Validation configuration. If None, uses defaults.
        cwd: Working directory for validation commands.

    Returns:
        Configured MCP server with run_validation and parse_validation_output tools.
    """
```
