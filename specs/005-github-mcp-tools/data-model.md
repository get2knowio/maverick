# Data Model: GitHub MCP Tools

**Feature**: 005-github-mcp-tools
**Date**: 2025-12-14

## Entities

### MCPServer

The configured MCP server instance returned by `create_github_tools_server()`.

| Property | Type | Description |
|----------|------|-------------|
| name | `str` | Server identifier: `"github-tools"` |
| version | `str` | Server version: `"1.0.0"` |
| tools | `list[Tool]` | Registered tool functions |

**Factory Function**:
```python
def create_github_tools_server() -> MCPServer:
    """Create MCP server with all GitHub tools registered.

    Raises:
        GitHubToolsError: If gh CLI not installed/authenticated or not in git repo.
    """
```

---

### ToolResponse

MCP-formatted response returned by all tools.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| content | `list[ContentBlock]` | Yes | Response content blocks |

**ContentBlock**:
| Property | Type | Required | Description |
|----------|------|----------|-------------|
| type | `Literal["text"]` | Yes | Always `"text"` for these tools |
| text | `str` | Yes | JSON-serialized response data |

---

### SuccessResponse (JSON in text field)

Common fields for successful tool responses.

| Field | Type | Description |
|-------|------|-------------|
| (varies) | varies | Tool-specific response fields |

---

### ErrorResponse (JSON in text field)

Common fields for error responses.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| isError | `Literal[True]` | Yes | Always `true` for errors |
| message | `str` | Yes | Human-readable error message |
| error_code | `str` | Yes | Machine-readable error code |
| retry_after_seconds | `int` | No | Seconds to wait (rate limits only) |

**Error Codes**:
- `NOT_FOUND` - Resource not found
- `AUTH_ERROR` - Authentication failure
- `RATE_LIMIT` - GitHub API rate limit exceeded
- `NETWORK_ERROR` - Network/connection failure
- `INVALID_INPUT` - Invalid parameter value
- `TIMEOUT` - Operation timed out
- `INTERNAL_ERROR` - Unexpected error

---

### PullRequest

Represents a GitHub pull request.

| Field | Type | Description |
|-------|------|-------------|
| number | `int` | PR number |
| title | `str` | PR title |
| body | `str` | PR description (markdown) |
| url | `str` | Full PR URL |
| state | `str` | `"open"`, `"closed"`, `"merged"` |
| head_ref | `str` | Head branch name |
| base_ref | `str` | Base branch name |
| is_draft | `bool` | Whether PR is draft |
| mergeable | `bool \| None` | Merge status (`None` if unknown) |
| created_at | `str` | ISO 8601 timestamp |

---

### Issue

Represents a GitHub issue.

| Field | Type | Description |
|-------|------|-------------|
| number | `int` | Issue number |
| title | `str` | Issue title |
| body | `str` | Issue body (markdown) |
| url | `str` | Full issue URL |
| state | `str` | `"open"`, `"closed"` |
| labels | `list[str]` | Label names |
| assignees | `list[str]` | Assignee usernames |
| author | `str` | Creator username |
| comments_count | `int` | Number of comments |
| created_at | `str` | ISO 8601 timestamp |
| updated_at | `str` | ISO 8601 timestamp |

---

### PRStatus

Represents PR status for merge readiness check.

| Field | Type | Description |
|-------|------|-------------|
| pr_number | `int` | PR number |
| state | `str` | PR state |
| mergeable | `bool \| None` | Can be merged (`None` if unknown) |
| merge_state_status | `str` | `"clean"`, `"blocked"`, `"behind"`, etc. |
| reviews | `list[Review]` | Review summaries |
| checks | `list[Check]` | CI check statuses |
| has_conflicts | `bool` | Has merge conflicts |

**Review**:
| Field | Type | Description |
|-------|------|-------------|
| author | `str` | Reviewer username |
| state | `str` | `"APPROVED"`, `"CHANGES_REQUESTED"`, `"COMMENTED"`, `"PENDING"` |

**Check**:
| Field | Type | Description |
|-------|------|-------------|
| name | `str` | Check name |
| status | `str` | `"completed"`, `"in_progress"`, `"queued"` |
| conclusion | `str \| None` | `"success"`, `"failure"`, `"neutral"`, etc. |

---

### PRDiff

Represents PR diff content.

| Field | Type | Description |
|-------|------|-------------|
| diff | `str` | Unified diff text |
| truncated | `bool` | Whether diff was truncated |
| warning | `str \| None` | Truncation warning message |
| original_size_bytes | `int \| None` | Original size if truncated |

---

## Tool Input Schemas

### github_create_pr

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| title | `str` | Yes | - | PR title |
| body | `str` | Yes | - | PR description |
| base | `str` | Yes | - | Base branch name |
| head | `str` | Yes | - | Head branch name |
| draft | `bool` | No | `false` | Create as draft PR |

**Response**: `PullRequest` subset (`pr_number`, `url`, `state`, `title`)

---

### github_list_issues

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| label | `str` | No | `None` | Filter by label |
| state | `str` | No | `"open"` | `"open"`, `"closed"`, `"all"` |
| limit | `int` | No | `30` | Max issues to return |

**Response**: `list[Issue]` (subset: `number`, `title`, `labels`, `state`, `url`)

---

### github_get_issue

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| issue_number | `int` | Yes | - | Issue number |

**Response**: Full `Issue` object

---

### github_get_pr_diff

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| pr_number | `int` | Yes | - | PR number |
| max_size | `int` | No | `102400` | Max diff size (bytes) |

**Response**: `PRDiff` object

---

### github_pr_status

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| pr_number | `int` | Yes | - | PR number |

**Response**: `PRStatus` object

---

### github_add_labels

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| issue_number | `int` | Yes | - | Issue/PR number |
| labels | `list[str]` | Yes | - | Label names to add |

**Response**: `{"success": true, "labels_added": ["label1", "label2"]}`

---

### github_close_issue

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| issue_number | `int` | Yes | - | Issue number |
| comment | `str` | No | `None` | Closing comment |

**Response**: `{"success": true, "issue_number": N, "state": "closed"}`

---

## State Transitions

### Issue States

```
open ──close──> closed
closed ──reopen──> open (not exposed in tools)
```

### PR States

```
open ──merge──> merged
open ──close──> closed
draft ──ready_for_review──> open (via github_create_pr draft=false)
```

---

## Validation Rules

| Rule | Applies To | Validation |
|------|------------|------------|
| PR number positive | `github_get_pr_diff`, `github_pr_status` | `pr_number > 0` |
| Issue number positive | `github_get_issue`, `github_add_labels`, `github_close_issue` | `issue_number > 0` |
| Labels non-empty | `github_add_labels` | `len(labels) > 0` |
| Max size positive | `github_get_pr_diff` | `max_size > 0` |
| State enum valid | `github_list_issues` | `state in ["open", "closed", "all"]` |
| Limit positive | `github_list_issues` | `limit > 0` |
