# Contract: FixerAgent

**Module**: `maverick.agents.fixer`
**Class**: `FixerAgent`
**Type**: Concrete Agent Implementation

## Overview

FixerAgent is a minimal agent specialized for applying targeted validation fixes to specific files. It has the smallest possible tool set and expects explicit file paths and error information in its context.

---

## Class Definition

```python
from maverick.agents.base import MaverickAgent
from maverick.agents.context import AgentContext
from maverick.agents.result import AgentResult

class FixerAgent(MaverickAgent):
    """Minimal agent for applying targeted validation fixes.

    This agent has the smallest tool set (Read, Write, Edit) and expects
    explicit file paths and error information. It does not search for files
    or investigate issues - it applies specific fixes to known locations.

    Use Cases:
        - Fixing linting errors at specific line numbers
        - Applying formatting corrections
        - Resolving type errors in identified files
        - Applying suggested fixes from code review

    Not For:
        - Investigating bug reports (use IssueFixerAgent)
        - Implementing features (use ImplementerAgent)
        - Searching for problematic code (use CodeReviewerAgent)
    """

    def __init__(
        self,
        model: str | None = None,
        mcp_servers: dict[str, Any] | None = None,
    ) -> None: ...

    async def execute(self, context: AgentContext) -> AgentResult: ...
```

---

## Constructor Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `str \| None` | `None` | Claude model ID. Uses `DEFAULT_MODEL` if not specified. |
| `mcp_servers` | `dict[str, Any] \| None` | `None` | MCP server configurations (rarely needed for fixer). |

---

## Properties (Inherited from MaverickAgent)

| Property | Type | Value |
|----------|------|-------|
| `name` | `str` | `"fixer"` |
| `system_prompt` | `str` | Constrained prompt for targeted fixes |
| `allowed_tools` | `list[str]` | `["Read", "Write", "Edit"]` |
| `model` | `str` | Configured model or `DEFAULT_MODEL` |

---

## Methods

### execute

```python
async def execute(self, context: AgentContext) -> AgentResult:
    """Apply a targeted fix based on the provided context.

    Args:
        context: Runtime context containing:
            - prompt: Description of the fix to apply (see Input Format)
            - cwd: Working directory for file operations
            - config: Optional agent configuration

    Returns:
        AgentResult with:
            - success: True if fix was applied
            - output: JSON with fix details (see Output Format)
            - metadata: Optional additional information
            - errors: List of any errors encountered
            - usage: Token usage statistics

    Raises:
        AgentError: If the fix cannot be applied after agent execution.
    """
```

---

## Input Format

The `context.prompt` should contain structured information about the fix:

```
Fix the following validation error:

File: src/maverick/agents/implementer.py
Line: 42
Error: Ruff E501: Line too long (120 > 88)

Please fix this error by reformatting the line appropriately.
```

### Required Information

| Field | Description |
|-------|-------------|
| File path | Absolute or relative path to the file |
| Error description | What needs to be fixed |

### Optional Information

| Field | Description |
|-------|-------------|
| Line number | Specific line if known |
| Fix hint | Suggested approach |
| Context | Surrounding code context |

---

## Output Format

The agent returns structured JSON in the `output` field:

```json
{
  "success": true,
  "file_modified": true,
  "file_path": "src/maverick/agents/implementer.py",
  "changes_made": "Reformatted line 42 to comply with line length limit",
  "error": null
}
```

### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | Whether the fix was successfully applied |
| `file_modified` | `bool` | Whether the file was actually changed |
| `file_path` | `str` | Path to the modified file |
| `changes_made` | `str` | Human-readable description of changes |
| `error` | `str \| null` | Error message if unsuccessful |

---

## System Prompt

```
You are a validation fixer applying targeted corrections to specific files.

Your role:
- Apply the exact fix described in the prompt
- Make minimal, focused changes
- Preserve existing code style and formatting
- Verify the fix addresses the stated error

You have access to:
- Read: Read file contents
- Write: Create or overwrite files
- Edit: Make precise edits to existing files

Constraints:
- You receive explicit file paths - do not search for files
- Make only the changes necessary to fix the stated error
- Do not refactor surrounding code
- Do not add features or improvements

Output your result as JSON with these fields:
- success: boolean
- file_modified: boolean
- file_path: string
- changes_made: string description
- error: string or null
```

---

## Usage Example

```python
from maverick.agents.fixer import FixerAgent
from maverick.agents.context import AgentContext

async def fix_linting_error(file_path: str, error: str, line: int) -> bool:
    """Apply a linting fix using FixerAgent."""
    agent = FixerAgent()

    context = AgentContext(
        prompt=f"""
Fix the following linting error:

File: {file_path}
Line: {line}
Error: {error}

Please fix this error with minimal changes.
""",
        cwd=Path.cwd(),
    )

    result = await agent.execute(context)

    if result.success:
        output = json.loads(result.output)
        return output.get("file_modified", False)

    return False
```

---

## Comparison with Other Agents

| Aspect | FixerAgent | IssueFixerAgent | ImplementerAgent |
|--------|------------|-----------------|------------------|
| **Tools** | 3 (minimal) | 5 (with search) | 5 (with search) |
| **Search** | No | Yes | Yes |
| **Purpose** | Known fixes | Issue investigation | Feature implementation |
| **Scope** | Single file | Multiple files | Multiple files |
| **Context** | Explicit paths | Issue description | Task description |

---

## Error Scenarios

| Scenario | Behavior |
|----------|----------|
| File not found | Returns `success: false` with error message |
| Cannot apply fix | Returns `success: false` with explanation |
| Agent timeout | Raises `MaverickTimeoutError` |
| SDK error | Raises wrapped `AgentError` |
