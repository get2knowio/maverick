# Contract: Agent Tool Permissions

**Type**: Security/Configuration Contract

## Overview

This contract defines the allowed tools for each agent in the workflow refactor. All agents MUST have explicitly defined `allowed_tools` lists (FR-021). Unauthorized tool calls MUST be rejected (SC-005).

## Permission Matrix

| Agent | Allowed Tools | Rationale |
|-------|---------------|-----------|
| ImplementerAgent | Read, Write, Edit, Bash, Glob, Grep | Full code manipulation for implementation |
| CodeReviewerAgent | Read, Glob, Grep, Bash | Read-only analysis of code |
| IssueFixerAgent | Read, Write, Edit, Bash, Glob, Grep | Targeted bug fixes |
| ValidationFixerAgent | Read, Write, Edit, Glob, Grep | Fix validation failures (no Bash for safety) |
| CommitMessageGenerator | (none) | Pure text generation, no tools needed |
| PRDescriptionGenerator | (none) | Pure text generation, no tools needed |
| CodeAnalyzer | (none) | Pure text generation, no tools needed |
| ErrorExplainer | (none) | Pure text generation, no tools needed |

## Validation Rules

### At Construction Time

```python
class MaverickAgent:
    def __init__(self, allowed_tools: list[str], ...):
        self._validate_tools(allowed_tools)  # Raises InvalidToolError

    def _validate_tools(self, allowed_tools: list[str]) -> None:
        """Validate all tools are known (FR-002)."""
        for tool in allowed_tools:
            if tool not in BUILTIN_TOOLS:
                raise InvalidToolError(tool, list(BUILTIN_TOOLS))
```

### Built-in Tools

```python
BUILTIN_TOOLS: frozenset[str] = frozenset({
    "Read",
    "Write",
    "Edit",
    "Bash",
    "Glob",
    "Grep",
    "NotebookEdit",
    "WebFetch",
    "WebSearch",
    "TodoWrite",
    "Task",
    "ExitPlanMode",
})
```

## Tool Prohibition Rules

### Agents MUST NOT have:

| Agent | Prohibited | Reason |
|-------|------------|--------|
| ImplementerAgent | GitHub tools, Git tools | Deterministic ops handled by Python runners |
| CodeReviewerAgent | Write, Edit | Read-only analysis |
| ValidationFixerAgent | Bash | Prevent shell injection during auto-fix |
| All Generators | Any tools | Single-shot text generation only |

### Workflow MUST enforce:

1. Git operations via GitRunner (not agent Bash calls)
2. GitHub operations via GitHubCLIRunner (not agent tools)
3. Validation via ValidationRunner (not agent Bash calls)
4. PR creation via GitHubCLIRunner (not agent tools)

## Test Contract

### Acceptance Scenarios (from User Story 5)

```python
@pytest.mark.asyncio
async def test_implementer_has_only_file_tools():
    """SC-005: Agent tool permissions are enforced."""
    agent = ImplementerAgent()
    assert set(agent.allowed_tools) == {"Read", "Write", "Edit", "Bash", "Glob", "Grep"}
    # No GitHub tools, no Git tools

@pytest.mark.asyncio
async def test_code_reviewer_has_only_read_tools():
    """SC-005: Agent tool permissions are enforced."""
    agent = CodeReviewerAgent()
    assert set(agent.allowed_tools) == {"Read", "Glob", "Grep", "Bash"}
    # No Write, no Edit

@pytest.mark.asyncio
async def test_generator_has_no_tools():
    """SC-005: Generators have no tool access."""
    generator = CommitMessageGenerator()
    assert generator.allowed_tools == []

@pytest.mark.asyncio
async def test_unauthorized_tool_rejected():
    """SC-005: Unauthorized tool calls are rejected."""
    with pytest.raises(InvalidToolError):
        MaverickAgent(
            name="test",
            allowed_tools=["Read", "UnknownTool"],  # Invalid
        )
```

## Security Considerations

1. **Principle of Least Privilege**: Agents get only the tools they need
2. **No Shell Access for Fixers**: ValidationFixerAgent can't run arbitrary commands
3. **Separation of Concerns**: Git/GitHub operations isolated from agent control
4. **Build-time Validation**: Invalid tool configs fail fast at construction
