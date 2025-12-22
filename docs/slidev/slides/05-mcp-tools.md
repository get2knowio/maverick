# Part 5: MCP Tools Integration

Model Context Protocol tools for external system integration

---
layout: default
---

# MCP Tool Servers

<div class="grid grid-cols-2 gap-6">

<div>

### GitHub Tools
`create_github_tools_server()`

```python
# PR Management
github_create_pr
github_pr_status

# Issue Management
github_list_issues
github_get_issue
github_add_labels
github_close_issue

# Code Review
github_get_pr_diff
```

</div>

<div>

### Git Tools
`create_git_tools_server()`

```python
# Branch Operations
git_current_branch
git_create_branch

# Commit & Push
git_commit
git_push

# Inspection
git_diff_stats
```

</div>

</div>

<div class="grid grid-cols-2 gap-6 mt-4">

<div>

### Validation Tools
`create_validation_tools_server()`

```python
# Run Checks
run_validation

# Parse Results
parse_validation_output
```

</div>

<div>

### Notification Tools
`create_notification_tools_server()`

```python
# ntfy.sh Integration
send_workflow_update
send_notification
```

</div>

</div>

---
layout: two-cols
---

# Tool Response Patterns

MCP tools return structured JSON responses

### Success Response

```python
{
    "content": [{
        "type": "text",
        "text": json.dumps({
            "success": True,
            "pr_number": 123,
            "url": "https://github.com/...",
            "state": "open"
        })
    }]
}
```

<v-click>

### Error Response

```python
{
    "content": [{
        "type": "text",
        "text": json.dumps({
            "isError": True,
            "message": "Rate limit exceeded",
            "error_code": "RATE_LIMIT",
            "retry_after_seconds": 60
        })
    }]
}
```

</v-click>

::right::

### Key Patterns

<v-click>

**Validation at Creation**
- Fail-fast: Check prerequisites before server creation
- `skip_verification=True` for testing
- Raises `GitHubToolsError`, `GitToolsError`, etc.

</v-click>

<v-click>

**Rate Limiting**
- Parse retry time from error messages
- Return `retry_after_seconds` in error response
- Classify errors: `RATE_LIMIT`, `AUTH_ERROR`, `NOT_FOUND`

</v-click>

<v-click>

**Graceful Degradation**
- Optional tool servers won't crash workflows
- Tools check prerequisites on first use
- Clear error codes for agent decision-making

</v-click>

<v-click>

**Structured Responses**
- JSON-serialized data (not raw text)
- Consistent error format across all tools
- Type-safe parsing with error handling

</v-click>
