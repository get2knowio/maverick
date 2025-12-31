# Quickstart: GitHub MCP Tools

**Feature**: 005-github-mcp-tools
**Date**: 2025-12-14

## Prerequisites

1. **GitHub CLI installed**: `gh --version`
2. **GitHub CLI authenticated**: `gh auth status`
3. **Inside a git repository**: `git rev-parse --git-dir`
4. **Remote configured**: `git remote get-url origin`

## Installation

The GitHub MCP tools are part of the Maverick package:

```bash
pip install maverick
```

## Basic Usage

### Creating the Server

```python
from maverick.tools.github import create_github_tools_server

# Create MCP server with all GitHub tools
# Raises GitHubToolsError if prerequisites not met
server = create_github_tools_server()
```

### Using with an Agent

```python
from maverick.agents.base import MaverickAgent
from maverick.tools.github import create_github_tools_server

class PRCreatorAgent(MaverickAgent):
    def __init__(self):
        github_server = create_github_tools_server()

        super().__init__(
            name="pr-creator",
            system_prompt="You create pull requests for completed features.",
            allowed_tools=[
                "Read", "Bash",
                "mcp__github-tools__github_create_pr",
            ],
            mcp_servers={"github-tools": github_server},
        )
```

## Tool Examples

### github_create_pr

Create a pull request:

```python
# Agent prompt: "Create a PR from feature-auth to main"

# Tool call:
{
    "title": "Add user authentication",
    "body": "## Summary\n- Added login/logout\n- Added session management",
    "base": "main",
    "head": "feature-auth",
    "draft": False
}

# Success response:
{
    "pr_number": 42,
    "url": "https://github.com/owner/repo/pull/42",
    "state": "open",
    "title": "Add user authentication"
}

# Error response (branch not found):
{
    "isError": True,
    "message": "Branch 'feature-auth' not found",
    "error_code": "BRANCH_NOT_FOUND"
}
```

### github_list_issues

List open issues with a label:

```python
# Agent prompt: "Find all tech-debt issues"

# Tool call:
{
    "label": "tech-debt",
    "state": "open",
    "limit": 10
}

# Success response:
{
    "issues": [
        {
            "number": 15,
            "title": "Refactor database queries",
            "labels": ["tech-debt", "backend"],
            "state": "open",
            "url": "https://github.com/owner/repo/issues/15"
        },
        {
            "number": 23,
            "title": "Remove deprecated API endpoints",
            "labels": ["tech-debt"],
            "state": "open",
            "url": "https://github.com/owner/repo/issues/23"
        }
    ]
}
```

### github_get_issue

Get full issue details:

```python
# Agent prompt: "Get details for issue #15"

# Tool call:
{
    "issue_number": 15
}

# Success response:
{
    "number": 15,
    "title": "Refactor database queries",
    "body": "The current queries are slow and need optimization...",
    "url": "https://github.com/owner/repo/issues/15",
    "state": "open",
    "labels": ["tech-debt", "backend"],
    "assignees": ["alice"],
    "author": "bob",
    "comments_count": 3,
    "created_at": "2025-12-01T10:00:00Z",
    "updated_at": "2025-12-10T14:30:00Z"
}

# Error response (not found):
{
    "isError": True,
    "message": "Issue #999 not found",
    "error_code": "NOT_FOUND"
}
```

### github_get_pr_diff

Get PR diff for code review:

```python
# Agent prompt: "Get the diff for PR #42"

# Tool call:
{
    "pr_number": 42,
    "max_size": 102400  # 100KB default
}

# Success response:
{
    "diff": "diff --git a/src/auth.py b/src/auth.py\n...",
    "truncated": False
}

# Truncated response:
{
    "diff": "diff --git a/src/auth.py b/src/auth.py\n...[truncated]",
    "truncated": True,
    "warning": "Diff truncated at 100KB",
    "original_size_bytes": 250000
}
```

### github_pr_status

Check PR merge readiness:

```python
# Agent prompt: "Is PR #42 ready to merge?"

# Tool call:
{
    "pr_number": 42
}

# Success response (ready):
{
    "pr_number": 42,
    "state": "open",
    "mergeable": True,
    "merge_state_status": "clean",
    "has_conflicts": False,
    "reviews": [
        {"author": "alice", "state": "APPROVED"}
    ],
    "checks": [
        {"name": "tests", "status": "completed", "conclusion": "success"},
        {"name": "lint", "status": "completed", "conclusion": "success"}
    ]
}

# Success response (blocked):
{
    "pr_number": 42,
    "state": "open",
    "mergeable": False,
    "merge_state_status": "blocked",
    "has_conflicts": True,
    "reviews": [
        {"author": "bob", "state": "CHANGES_REQUESTED"}
    ],
    "checks": [
        {"name": "tests", "status": "completed", "conclusion": "failure"}
    ]
}
```

### github_add_labels

Add labels to an issue or PR:

```python
# Agent prompt: "Mark issue #15 as in-progress"

# Tool call:
{
    "issue_number": 15,
    "labels": ["in-progress", "assigned"]
}

# Success response:
{
    "success": True,
    "issue_number": 15,
    "labels_added": ["in-progress", "assigned"]
}
```

### github_close_issue

Close an issue with a comment:

```python
# Agent prompt: "Close issue #15, it's fixed in PR #42"

# Tool call:
{
    "issue_number": 15,
    "comment": "Fixed in #42"
}

# Success response:
{
    "success": True,
    "issue_number": 15,
    "state": "closed"
}

# Without comment:
{
    "issue_number": 15
}
# Also succeeds (comment is optional)
```

## Error Handling

All tools return structured error responses instead of raising exceptions:

```python
# Rate limit error:
{
    "isError": True,
    "message": "GitHub API rate limit exceeded",
    "retry_after_seconds": 3600,
    "error_code": "RATE_LIMIT"
}

# Authentication error:
{
    "isError": True,
    "message": "GitHub CLI not authenticated. Run: gh auth login",
    "error_code": "AUTH_ERROR"
}

# Network error:
{
    "isError": True,
    "message": "Network error: Connection refused",
    "error_code": "NETWORK_ERROR"
}
```

## Integration with Workflows

### FlyWorkflow Example

```python
from maverick.workflows.fly import FlyWorkflow
from maverick.tools.github import create_github_tools_server

async def create_feature_pr():
    workflow = FlyWorkflow(
        spec_path="specs/feature/spec.md",
        github_server=create_github_tools_server(),
    )

    async for event in workflow.execute():
        if event.type == "pr_created":
            print(f"PR created: {event.data['url']}")
```

### RefuelWorkflow Example

```python
from maverick.workflows.refuel import RefuelWorkflow
from maverick.tools.github import create_github_tools_server

async def fix_tech_debt():
    workflow = RefuelWorkflow(
        label="tech-debt",
        max_issues=3,
        github_server=create_github_tools_server(),
    )

    async for event in workflow.execute():
        if event.type == "issue_closed":
            print(f"Fixed: #{event.data['issue_number']}")
```

## Testing

Unit tests mock the `gh` CLI subprocess:

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_github_create_pr_success():
    with patch("maverick.tools.github._run_gh_command") as mock_run:
        mock_run.return_value = (
            "https://github.com/owner/repo/pull/42",
            "",
            0
        )

        result = await github_create_pr({
            "title": "Test PR",
            "body": "Test body",
            "base": "main",
            "head": "feature"
        })

        assert result["content"][0]["text"]
        data = json.loads(result["content"][0]["text"])
        assert data["pr_number"] == 42
        assert "isError" not in data
```

Integration tests require `gh` authentication:

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_github_list_issues_live():
    """Requires: gh auth login"""
    server = create_github_tools_server()
    # Test with real GitHub API
```
