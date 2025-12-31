# Quickstart: Agent Tool Permissions

**Feature Branch**: `021-agent-tool-permissions`
**Date**: 2025-12-19

## Overview

This guide explains how to work with the updated agent tool permission system in Maverick. After this feature, agents have reduced tool access to enforce the separation between agent judgment tasks and workflow orchestration.

---

## Quick Reference

### Tool Sets by Agent Type

| Agent | Tools | Use Case |
|-------|-------|----------|
| `CodeReviewerAgent` | Read, Glob, Grep | Analyze code (read-only) |
| `ImplementerAgent` | Read, Write, Edit, Glob, Grep | Modify code |
| `FixerAgent` | Read, Write, Edit | Apply targeted fixes |
| `IssueFixerAgent` | Read, Write, Edit, Glob, Grep | Fix GitHub issues |
| `GeneratorAgent` | (none) | Generate text |

### Key Changes

- **Bash removed**: No agent can execute shell commands
- **New FixerAgent**: Minimal agent for validation fixes
- **Centralized constants**: All tool sets in `maverick.agents.tools`
- **Updated prompts**: System prompts reflect constrained roles

---

## Using Tool Sets

### Import Tool Constants

```python
from maverick.agents.tools import (
    REVIEWER_TOOLS,      # frozenset({"Read", "Glob", "Grep"})
    IMPLEMENTER_TOOLS,   # frozenset({"Read", "Write", "Edit", "Glob", "Grep"})
    FIXER_TOOLS,         # frozenset({"Read", "Write", "Edit"})
    ISSUE_FIXER_TOOLS,   # frozenset({"Read", "Write", "Edit", "Glob", "Grep"})
    GENERATOR_TOOLS,     # frozenset()
)
```

### Create an Agent with Tool Set

```python
from maverick.agents.base import MaverickAgent
from maverick.agents.tools import REVIEWER_TOOLS

class MyReviewAgent(MaverickAgent):
    def __init__(self):
        super().__init__(
            name="my-reviewer",
            system_prompt="You are a code reviewer...",
            allowed_tools=list(REVIEWER_TOOLS),  # Convert frozenset to list
        )
```

### Using the New FixerAgent

```python
from maverick.agents.fixer import FixerAgent
from maverick.agents.context import AgentContext

async def apply_fix():
    agent = FixerAgent()

    context = AgentContext(
        prompt="""
Fix the following linting error:

File: src/utils/helpers.py
Line: 42
Error: Ruff E501: Line too long (120 > 88)
""",
        cwd=Path("/workspaces/maverick"),
    )

    result = await agent.execute(context)
    print(f"Fix applied: {result.success}")
```

---

## Workflow Integration

### Providing Context to Constrained Agents

Since agents no longer have Bash access, workflows must pre-gather context:

```python
from maverick.utils.git_operations import GitOperations
from maverick.utils.context_builder import ContextBuilder

async def run_code_review(branch: str):
    git = GitOperations()
    ctx = ContextBuilder()

    # Pre-gather context (orchestration layer responsibility)
    diff = await git.get_diff("main", branch)
    files = await ctx.read_changed_files(diff)
    conventions = await ctx.read_conventions()

    # Provide context in prompt (agent only analyzes)
    prompt = f"""
## Git Diff
{diff}

## Changed Files
{format_files(files)}

## Conventions
{conventions}

Analyze these changes and provide findings.
"""

    context = AgentContext(prompt=prompt, cwd=Path.cwd())
    result = await reviewer.execute(context)
```

### Migration from Bash-Dependent Code

**Before** (agent executed commands):
```python
# Old pattern - agent ran git commands itself
result = await agent.execute(AgentContext(
    prompt="Review the changes on this branch",
))
```

**After** (orchestration provides context):
```python
# New pattern - orchestration gathers, agent analyzes
diff = await git.get_diff("main", "feature-branch")
result = await agent.execute(AgentContext(
    prompt=f"Review these changes:\n\n{diff}",
))
```

---

## Testing Tool Permissions

### Verify Agent Tools

```python
import pytest
from maverick.agents.implementer import ImplementerAgent
from maverick.agents.tools import IMPLEMENTER_TOOLS

def test_implementer_has_correct_tools():
    agent = ImplementerAgent(config=mock_config)
    assert set(agent.allowed_tools) == IMPLEMENTER_TOOLS
    assert "Bash" not in agent.allowed_tools
```

### Verify Tool Set Properties

```python
from maverick.agents.tools import (
    REVIEWER_TOOLS,
    IMPLEMENTER_TOOLS,
    FIXER_TOOLS,
)
from maverick.agents.base import BUILTIN_TOOLS

def test_all_tools_are_valid():
    """All tool sets must be subsets of BUILTIN_TOOLS."""
    assert REVIEWER_TOOLS.issubset(BUILTIN_TOOLS)
    assert IMPLEMENTER_TOOLS.issubset(BUILTIN_TOOLS)
    assert FIXER_TOOLS.issubset(BUILTIN_TOOLS)

def test_tool_sets_are_immutable():
    """Tool sets must be frozenset for immutability."""
    assert isinstance(REVIEWER_TOOLS, frozenset)
    assert isinstance(IMPLEMENTER_TOOLS, frozenset)
    assert isinstance(FIXER_TOOLS, frozenset)
```

---

## Common Patterns

### Choose the Right Agent

| Need | Agent | Why |
|------|-------|-----|
| Analyze code without changes | `CodeReviewerAgent` | Read-only tools |
| Implement a feature | `ImplementerAgent` | Full code modification |
| Fix a specific error | `FixerAgent` | Minimal, targeted |
| Resolve a GitHub issue | `IssueFixerAgent` | Investigation + fix |
| Generate commit message | `CommitMessageGenerator` | No tools needed |

### Compose Tool Sets (Advanced)

```python
from maverick.agents.tools import REVIEWER_TOOLS, FIXER_TOOLS

# Union: combine capabilities
READ_WRITE_TOOLS = REVIEWER_TOOLS | FIXER_TOOLS
# {"Read", "Glob", "Grep", "Write", "Edit"}

# Intersection: common tools
COMMON_TOOLS = REVIEWER_TOOLS & IMPLEMENTER_TOOLS
# {"Read", "Glob", "Grep"}

# Difference: what reviewers have that fixers don't
SEARCH_ONLY = REVIEWER_TOOLS - FIXER_TOOLS
# {"Glob", "Grep"}
```

---

## Troubleshooting

### "Agent tried to use unavailable tool"

**Cause**: Agent's system prompt mentions tools it doesn't have.

**Fix**: Update system prompt to remove references to unavailable tools.

### "Missing context for review"

**Cause**: Workflow didn't pre-gather required context.

**Fix**: Ensure workflow gathers git diffs, file contents, etc. before invoking agent.

### "InvalidToolError on agent creation"

**Cause**: Tool set contains invalid tool name.

**Fix**: Verify all tools exist in `BUILTIN_TOOLS`:
```python
from maverick.agents.base import BUILTIN_TOOLS
print(BUILTIN_TOOLS)  # See available tools
```

---

## Next Steps

1. **Review existing agents**: Check if any depend on Bash
2. **Update workflows**: Ensure context is pre-gathered
3. **Test permissions**: Verify agents have expected tools
4. **Use FixerAgent**: For validation error fixes
