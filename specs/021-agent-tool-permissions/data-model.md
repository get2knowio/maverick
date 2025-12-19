# Data Model: Agent Tool Permissions

**Feature Branch**: `021-agent-tool-permissions`
**Date**: 2025-12-19

## Overview

This feature introduces a centralized tool permission system for Maverick agents. The data model is intentionally simple - tool sets are immutable constants, not runtime entities.

---

## Entities

### 1. ToolSet (Constant)

**Description**: An immutable set of tool name strings representing permissions for a category of agent operations.

**Type**: `frozenset[str]`

**Location**: `src/maverick/agents/tools.py`

**Instances**:

| Constant Name | Tools | Purpose |
|---------------|-------|---------|
| `REVIEWER_TOOLS` | Read, Glob, Grep | Read-only code analysis |
| `IMPLEMENTER_TOOLS` | Read, Write, Edit, Glob, Grep | Code modification without execution |
| `FIXER_TOOLS` | Read, Write, Edit | Targeted file fixes |
| `ISSUE_FIXER_TOOLS` | Read, Write, Edit, Glob, Grep | Issue resolution with search |
| `GENERATOR_TOOLS` | (empty) | Text generation only |

**Validation Rules**:
- All tool names must exist in `BUILTIN_TOOLS` or match MCP server patterns
- Sets are frozen at module load time
- No runtime modification possible

---

### 2. Agent (Updated)

**Description**: Existing agent classes with updated `allowed_tools` configuration.

**Changes**:

```python
# Before: Tools defined inline
class ImplementerAgent(MaverickAgent):
    TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]  # Inline

# After: Tools imported from centralized module
from maverick.agents.tools import IMPLEMENTER_TOOLS

class ImplementerAgent(MaverickAgent):
    def __init__(self, ...):
        super().__init__(
            allowed_tools=list(IMPLEMENTER_TOOLS),  # From tools.py
            ...
        )
```

**Affected Classes**:

| Agent Class | Old Tools | New Tools | Change |
|-------------|-----------|-----------|--------|
| `ImplementerAgent` | Read, Write, Edit, Bash, Glob, Grep | Read, Write, Edit, Glob, Grep | -Bash |
| `CodeReviewerAgent` | Read, Glob, Grep, Bash | Read, Glob, Grep | -Bash |
| `IssueFixerAgent` | Read, Write, Edit, Bash, Glob, Grep | Read, Write, Edit, Glob, Grep | -Bash |
| `GeneratorAgent` | (none) | (none) | No change |

---

### 3. FixerAgent (New)

**Description**: New minimal agent class for applying targeted validation fixes.

**Location**: `src/maverick/agents/fixer.py`

**Attributes**:

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | "fixer" |
| `system_prompt` | `str` | Constrained prompt for targeted fixes |
| `allowed_tools` | `list[str]` | `list(FIXER_TOOLS)` = ["Read", "Write", "Edit"] |
| `model` | `str` | Inherited from config |

**Methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `execute` | `async def execute(context: AgentContext) -> AgentResult` | Apply fix to specified file |

**Input Context** (via AgentContext prompt):
```python
@dataclass
class FixerInput:
    file_path: str          # Absolute path to file
    error_message: str      # Validation error description
    line_number: int | None # Optional line number
    fix_hint: str | None    # Optional suggested fix
```

**Output** (via AgentResult):
```python
@dataclass
class FixerOutput:
    success: bool           # Whether fix was applied
    file_modified: bool     # Whether file was changed
    changes_made: str       # Description of changes
    error: str | None       # Error if unsuccessful
```

---

## Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                    tools.py (constants)                      │
├─────────────────────────────────────────────────────────────┤
│  REVIEWER_TOOLS      ─────────────►  CodeReviewerAgent      │
│  IMPLEMENTER_TOOLS   ─────────────►  ImplementerAgent       │
│  FIXER_TOOLS         ─────────────►  FixerAgent (NEW)       │
│  ISSUE_FIXER_TOOLS   ─────────────►  IssueFixerAgent        │
│  GENERATOR_TOOLS     ─────────────►  GeneratorAgent (base)  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    base.py (validation)                      │
├─────────────────────────────────────────────────────────────┤
│  BUILTIN_TOOLS       ◄──────────── Validates all tool names │
└─────────────────────────────────────────────────────────────┘
```

---

## State Transitions

This feature does not introduce state machines. Tool permissions are static at agent construction time.

**Agent Lifecycle**:
1. Agent class imports tool set from `tools.py`
2. Agent constructor receives tools via `allowed_tools` parameter
3. `MaverickAgent._validate_tools()` validates against `BUILTIN_TOOLS`
4. Tools are fixed for the agent's lifetime
5. Claude Agent SDK receives `allowed_tools` in options

---

## Validation Rules

### Tool Set Validation

**Location**: `MaverickAgent._validate_tools()` in `base.py`

**Rules**:
1. Each tool name must be in `BUILTIN_TOOLS` OR
2. Match pattern `mcp__{server}__*` where `server` is in `mcp_servers`
3. Unknown tools raise `InvalidToolError`

**Existing Implementation** (no changes needed):
```python
def _validate_tools(self, allowed_tools: list[str], mcp_servers: dict[str, Any]) -> None:
    mcp_tool_prefixes = {f"mcp__{server}__" for server in mcp_servers}

    for tool in allowed_tools:
        if tool in BUILTIN_TOOLS:
            continue
        is_mcp_tool = any(tool.startswith(prefix) for prefix in mcp_tool_prefixes)
        if is_mcp_tool:
            continue
        raise InvalidToolError(tool, sorted(BUILTIN_TOOLS) + [...])
```

---

## Constants Definition

### BUILTIN_TOOLS (Existing)

**Location**: `src/maverick/agents/base.py`

**Current Value**:
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

**Note**: `BUILTIN_TOOLS` defines what tools *exist*. The new `tools.py` module defines what tools each *agent type* can use (subset of BUILTIN_TOOLS).

---

## Test Requirements

### Unit Tests for Tool Sets

**Location**: `tests/unit/agents/test_tools.py`

| Test | Assertion |
|------|-----------|
| `test_reviewer_tools_are_readonly` | REVIEWER_TOOLS ⊆ {"Read", "Glob", "Grep"} |
| `test_implementer_tools_no_bash` | "Bash" ∉ IMPLEMENTER_TOOLS |
| `test_fixer_tools_minimal` | FIXER_TOOLS == {"Read", "Write", "Edit"} |
| `test_generator_tools_empty` | GENERATOR_TOOLS == frozenset() |
| `test_all_tools_are_valid` | All tool sets ⊆ BUILTIN_TOOLS |
| `test_tools_are_frozen` | All sets are frozenset instances |

### Agent Configuration Tests

**Location**: Per-agent test files

| Test | Assertion |
|------|-----------|
| `test_implementer_uses_implementer_tools` | agent.allowed_tools == list(IMPLEMENTER_TOOLS) |
| `test_reviewer_uses_reviewer_tools` | agent.allowed_tools == list(REVIEWER_TOOLS) |
| `test_fixer_uses_fixer_tools` | agent.allowed_tools == list(FIXER_TOOLS) |
| `test_issue_fixer_uses_issue_fixer_tools` | agent.allowed_tools == list(ISSUE_FIXER_TOOLS) |

---

## Migration Notes

### Breaking Changes
- Agents no longer have `Bash` tool access
- Workflows must provide all context upfront (enforced by spec 020)

### Backward Compatibility
- Agent public interfaces unchanged
- AgentContext / AgentResult unchanged
- Workflow APIs unchanged

### Migration Path
1. Deploy updated tool constants
2. Update agent constructors to use constants
3. Update system prompts
4. Verify workflow context gathering
5. Run test suite
