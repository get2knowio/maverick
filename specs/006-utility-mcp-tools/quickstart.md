# Quickstart: Utility MCP Tools

**Feature Branch**: `006-utility-mcp-tools`
**Date**: 2025-12-15

## Overview

The Utility MCP Tools provide three MCP servers for Maverick agents:

1. **Notification Tools**: Send push notifications via ntfy.sh
2. **Git Tools**: Git operations (branch, commit, push, diff)
3. **Validation Tools**: Run and parse validation commands

## Prerequisites

- Python 3.10+
- Git installed and configured
- Claude Agent SDK (`claude-agent-sdk`)
- (Optional) ntfy.sh account for notifications

## Installation

The tools are part of the Maverick package:

```python
from maverick.tools import (
    create_notification_tools_server,
    create_git_tools_server,
    create_validation_tools_server,
)
```

## Basic Usage

### Creating an Agent with Tools

```python
from maverick.agents.base import MaverickAgent
from maverick.tools import (
    create_notification_tools_server,
    create_git_tools_server,
    create_validation_tools_server,
)

# Create tool servers
notification_server = create_notification_tools_server()
git_server = create_git_tools_server()
validation_server = create_validation_tools_server()

# Create agent with tool access
agent = MaverickAgent(
    name="implementer",
    system_prompt="You are an implementation agent...",
    mcp_servers={
        "notification-tools": notification_server,
        "git-tools": git_server,
        "validation-tools": validation_server,
    },
    allowed_tools=[
        "mcp__git-tools__git_commit",
        "mcp__git-tools__git_push",
        "mcp__validation-tools__run_validation",
        "mcp__notification-tools__send_workflow_update",
    ],
)
```

### Notification Tools

```python
# Send a custom notification
await agent.run_tool("mcp__notification-tools__send_notification", {
    "message": "Build completed successfully!",
    "title": "CI Update",
    "priority": "high",
    "tags": ["white_check_mark", "rocket"],
})

# Send a workflow update (auto-formats based on stage)
await agent.run_tool("mcp__notification-tools__send_workflow_update", {
    "stage": "complete",
    "message": "All tasks finished successfully",
    "workflow_name": "FlyWorkflow",
})
```

### Git Tools

```python
# Get current branch
result = await agent.run_tool("mcp__git-tools__git_current_branch", {})
# Returns: {"branch": "feature-123"}

# Create a new branch
result = await agent.run_tool("mcp__git-tools__git_create_branch", {
    "name": "feature-456",
    "base": "main",
})
# Returns: {"success": true, "branch": "feature-456", "base": "main"}

# Commit with conventional format
result = await agent.run_tool("mcp__git-tools__git_commit", {
    "type": "feat",
    "scope": "api",
    "message": "add user authentication endpoint",
})
# Returns: {"success": true, "commit_sha": "abc123...", "message": "feat(api): add user authentication endpoint"}

# Push to remote
result = await agent.run_tool("mcp__git-tools__git_push", {
    "set_upstream": True,
})
# Returns: {"success": true, "commits_pushed": 3, "remote": "origin", "branch": "feature-456"}

# Get diff statistics
result = await agent.run_tool("mcp__git-tools__git_diff_stats", {})
# Returns: {"files_changed": 5, "insertions": 120, "deletions": 30}
```

### Validation Tools

```python
# Run validation suite
result = await agent.run_tool("mcp__validation-tools__run_validation", {
    "types": ["format", "lint", "typecheck", "test"],
})
# Returns: {"success": false, "results": [...]}

# Parse lint output for structured errors
result = await agent.run_tool("mcp__validation-tools__parse_validation_output", {
    "output": "src/main.py:10:5: E501 Line too long (89 > 88)",
    "type": "lint",
})
# Returns: {"errors": [{"file": "src/main.py", "line": 10, ...}], "total_count": 1, "truncated": false}
```

## Configuration

### Notification Configuration

Add to `maverick.yaml`:

```yaml
notifications:
  enabled: true
  server: "https://ntfy.sh"
  topic: "my-maverick-notifications"
```

Or via environment variables:

```bash
export MAVERICK_NOTIFICATIONS__ENABLED=true
export MAVERICK_NOTIFICATIONS__TOPIC=my-maverick-notifications
```

### Validation Configuration

Add to `maverick.yaml`:

```yaml
validation:
  format_cmd: ["ruff", "format", "."]
  lint_cmd: ["ruff", "check", "--fix", "."]
  typecheck_cmd: ["mypy", "."]
  test_cmd: ["pytest", "-x", "--tb=short"]
  timeout_seconds: 300
  max_errors: 50
```

## Error Handling

All tools return structured errors that agents can handle:

```python
result = await agent.run_tool("mcp__git-tools__git_commit", {
    "message": "update",
})

data = json.loads(result["content"][0]["text"])
if data.get("isError"):
    error_code = data["error_code"]
    if error_code == "NOTHING_TO_COMMIT":
        # Handle: no changes to commit
        pass
    elif error_code == "NOT_A_REPOSITORY":
        # Handle: not in a git repo
        pass
```

## Graceful Degradation

### Notifications

If ntfy.sh is not configured or unreachable, notification tools return success with a warning:

```python
# When notifications disabled
{"success": true, "message": "Notifications disabled (no topic configured)"}

# When server unreachable
{"success": true, "message": "Notification not delivered", "warning": "ntfy.sh server unreachable after 2 attempts"}
```

### Validation

If a validation tool is not installed, that step is skipped:

```python
{
    "type": "typecheck",
    "success": true,
    "output": "Validation tool not found: mypy. Skipping typecheck.",
    "duration_ms": 5
}
```

## Integration with Workflows

### FlyWorkflow Example

```python
async def fly_workflow(task_file: Path):
    # Create servers
    git_server = create_git_tools_server()
    validation_server = create_validation_tools_server()
    notification_server = create_notification_tools_server()

    # Notify start
    await send_workflow_update("start", "Starting FlyWorkflow", "FlyWorkflow")

    # Implementation phase
    for task in tasks:
        await implement_task(task)
        await git_commit(f"feat: {task.description}")

    # Validation phase
    await send_workflow_update("validation", "Running validation suite")
    result = await run_validation(["format", "lint", "typecheck", "test"])

    if not result["success"]:
        # Parse errors for agent to fix
        errors = await parse_validation_output(result["results"][0]["output"], "lint")
        # ... agent fixes errors ...

    # Push changes
    await git_push(set_upstream=True)

    # Notify completion
    await send_workflow_update("complete", "All tasks completed successfully!")
```

## Tool Reference

| Tool | Server | Purpose |
|------|--------|---------|
| `send_notification` | notification-tools | Send custom ntfy.sh notification |
| `send_workflow_update` | notification-tools | Send stage-formatted workflow notification |
| `git_current_branch` | git-tools | Get current branch name |
| `git_create_branch` | git-tools | Create and checkout new branch |
| `git_commit` | git-tools | Create conventional commit |
| `git_push` | git-tools | Push to remote |
| `git_diff_stats` | git-tools | Get change statistics |
| `run_validation` | validation-tools | Run validation commands |
| `parse_validation_output` | validation-tools | Parse linter/typecheck output |

## Next Steps

1. See [data-model.md](data-model.md) for detailed schemas
2. See [contracts/tool-responses.md](contracts/tool-responses.md) for API contracts
3. See [spec.md](spec.md) for full requirements and acceptance criteria
