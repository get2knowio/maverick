# Research: GitHub MCP Tools Integration

**Feature**: 005-github-mcp-tools
**Date**: 2025-12-14

## Research Questions

### 1. Claude Agent SDK MCP Tool Patterns

**Question**: How to implement custom MCP tools using the Claude Agent SDK?

**Decision**: Use `@tool` decorator with `create_sdk_mcp_server()` factory pattern.

**Rationale**:
- SDK provides first-class support for in-process MCP servers
- Tools are async functions decorated with `@tool(name, description, parameters)`
- Server factory returns injectable MCP server for agent configuration
- Follows established patterns in `specs/002-base-agent/research.md`

**Implementation Pattern**:
```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool(
    name="tool_name",
    description="What the tool does",
    parameters={"param1": str, "param2": {"type": int, "default": 10}}
)
async def tool_name(args: dict[str, Any]) -> dict[str, Any]:
    # Implementation
    return {"content": [{"type": "text", "text": json.dumps({...})}]}

server = create_sdk_mcp_server(
    name="server-name",
    version="1.0.0",
    tools=[tool_name]
)
```

**Alternatives Considered**:
- External MCP server process: Rejected (adds complexity, process management)
- Direct Claude API calls: Rejected (loses tool abstraction benefits)

---

### 2. MCP Response Format

**Question**: How should tool responses be structured for MCP compliance?

**Decision**: Return dict with `content` array containing JSON-serialized structured data.

**Rationale**:
- MCP protocol requires `content` array with typed blocks
- Structured JSON (typed fields) preferred over free-form text (FR-004)
- Error responses use `isError: true` flag (FR-005)
- Enables reliable parsing by agents

**Success Response Format**:
```python
{
    "content": [
        {
            "type": "text",
            "text": json.dumps({
                "pr_number": 123,
                "url": "https://github.com/owner/repo/pull/123",
                "state": "open"
            })
        }
    ]
}
```

**Error Response Format**:
```python
{
    "content": [
        {
            "type": "text",
            "text": json.dumps({
                "isError": True,
                "message": "Branch 'feature-xyz' not found",
                "error_code": "BRANCH_NOT_FOUND"
            })
        }
    ]
}
```

**Rate Limit Error Format** (FR-016):
```python
{
    "content": [
        {
            "type": "text",
            "text": json.dumps({
                "isError": True,
                "message": "GitHub API rate limit exceeded",
                "retry_after_seconds": 3600,
                "error_code": "RATE_LIMIT"
            })
        }
    ]
}
```

---

### 3. GitHub CLI Commands

**Question**: What `gh` CLI commands are needed for each tool?

**Decision**: Map each tool to specific `gh` CLI commands with JSON output.

| Tool | gh CLI Command | Notes |
|------|---------------|-------|
| `github_create_pr` | `gh pr create --title X --body Y --base B --head H [--draft]` | Returns PR URL |
| `github_list_issues` | `gh issue list --state S --label L --limit N --json fields` | JSON array |
| `github_get_issue` | `gh issue view N --json fields` | Single issue JSON |
| `github_get_pr_diff` | `gh pr diff N` | Raw diff text |
| `github_pr_status` | `gh pr view N --json state,mergeable,reviews,statusCheckRollup` | Status JSON |
| `github_add_labels` | `gh issue edit N --add-label L1 --add-label L2` | Applies to PRs too |
| `github_close_issue` | `gh issue close N [--comment C]` | Idempotent |

**JSON Fields per Command**:
- Issues: `number,title,body,labels,state,url,author,assignees,createdAt,comments`
- PRs: `number,title,body,state,url,headRefName,baseRefName,isDraft,mergeable,reviews,statusCheckRollup`

---

### 4. Error Handling Strategy

**Question**: How to handle errors gracefully without raising exceptions?

**Decision**: Catch all exceptions within tool, return error response dict.

**Rationale**:
- Tools should never raise (agents can't handle exceptions)
- Error responses include actionable messages (SC-003)
- Rate limits include retry-after info (FR-016)
- Logging captures details for debugging (FR-006)

**Error Categories**:
| Category | Error Code | Message Pattern |
|----------|------------|-----------------|
| Not found | `NOT_FOUND` | "Issue #N not found" |
| Auth failure | `AUTH_ERROR` | "GitHub CLI not authenticated. Run: gh auth login" |
| Rate limit | `RATE_LIMIT` | "Rate limit exceeded, retry after N seconds" |
| Network | `NETWORK_ERROR` | "Network error: {original message}" |
| Invalid input | `INVALID_INPUT` | "Invalid parameter: {details}" |
| Timeout | `TIMEOUT` | "Operation timed out after N seconds" |
| Internal | `INTERNAL_ERROR` | "Unexpected error: {message}" |

---

### 5. Prerequisite Verification

**Question**: When and how to verify `gh` CLI and git repo context?

**Decision**: Verify at server creation time (fail fast per FR-015).

**Rationale**:
- Early failure gives clear error before any tool execution
- Avoids repeated checks in each tool call
- Matches spec requirement FR-015

**Verification Steps**:
1. Check `gh --version` succeeds (CLI installed)
2. Check `gh auth status` succeeds (authenticated)
3. Check `git rev-parse --git-dir` succeeds (in git repo)
4. Check `git remote get-url origin` succeeds (has remote)

**Exception**: Raise `GitHubToolsError` on any failure.

---

### 6. Large Diff Handling

**Question**: How to handle large PR diffs that exceed size limits?

**Decision**: Truncate at configurable limit with warning (FR-010).

**Rationale**:
- Default 100KB prevents memory issues
- Warning in response alerts agent to truncation
- Configurable allows override when needed

**Implementation**:
```python
@tool(
    name="github_get_pr_diff",
    parameters={"pr_number": int, "max_size": {"type": int, "default": 102400}}
)
async def github_get_pr_diff(args: dict[str, Any]) -> dict[str, Any]:
    diff = await _run_gh_command(["pr", "diff", str(pr_number)])

    if len(diff) > max_size:
        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "diff": diff[:max_size],
                    "truncated": True,
                    "warning": f"Diff truncated at {max_size // 1024}KB",
                    "original_size_bytes": len(diff)
                })
            }]
        }

    return {"content": [{"type": "text", "text": json.dumps({"diff": diff, "truncated": False})}]}
```

---

### 7. Reusing Existing Utils

**Question**: Can we reuse `src/maverick/utils/github.py`?

**Decision**: Yes, reuse `_run_gh_command()` and `_parse_rate_limit_wait()`.

**Rationale**:
- Already implements async subprocess execution with timeout
- Has rate limit parsing logic
- Avoids code duplication
- Battle-tested in existing agents

**Functions to Reuse**:
- `_run_gh_command(*args, cwd, timeout)` - async subprocess execution
- `_parse_rate_limit_wait(stderr)` - extract retry-after seconds
- `check_gh_auth(cwd)` - verify authentication

**Note**: May need to make some functions public (remove underscore prefix) or add new public wrappers.

---

## Summary

All research questions resolved. Key decisions:

1. **SDK Pattern**: `@tool` decorator + `create_sdk_mcp_server()`
2. **Response Format**: `{"content": [{"type": "text", "text": json.dumps(...)}]}`
3. **Error Pattern**: Return dict with `isError: true`, never raise
4. **CLI Commands**: Direct `gh` CLI with `--json` output
5. **Prerequisites**: Verify at server creation (fail fast)
6. **Large Diffs**: Truncate with warning at configurable limit
7. **Code Reuse**: Leverage existing `utils/github.py` helpers
