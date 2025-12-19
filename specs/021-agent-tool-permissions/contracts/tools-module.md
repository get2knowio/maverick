# Contract: Tool Permission Module

**Module**: `maverick.agents.tools`
**Type**: Python Constants Module

## Overview

This module defines the centralized tool permission sets for all Maverick agents. It enforces the principle of least privilege by providing named, immutable tool sets.

---

## Public API

### Constants

```python
from maverick.agents.tools import (
    REVIEWER_TOOLS,
    IMPLEMENTER_TOOLS,
    FIXER_TOOLS,
    ISSUE_FIXER_TOOLS,
    GENERATOR_TOOLS,
)
```

### Type Signatures

```python
REVIEWER_TOOLS: frozenset[str]
IMPLEMENTER_TOOLS: frozenset[str]
FIXER_TOOLS: frozenset[str]
ISSUE_FIXER_TOOLS: frozenset[str]
GENERATOR_TOOLS: frozenset[str]
```

---

## Tool Set Definitions

### REVIEWER_TOOLS

**Purpose**: Read-only tools for code analysis agents.

**Value**:
```python
frozenset({"Read", "Glob", "Grep"})
```

**Used By**: `CodeReviewerAgent`

**Rationale**: Reviewers analyze code but must not modify it. Search tools (Glob, Grep) enable finding relevant code sections.

---

### IMPLEMENTER_TOOLS

**Purpose**: Code modification tools without command execution.

**Value**:
```python
frozenset({"Read", "Write", "Edit", "Glob", "Grep"})
```

**Used By**: `ImplementerAgent`

**Rationale**: Implementers write and edit code but cannot execute commands. The orchestration layer handles test execution and validation.

---

### FIXER_TOOLS

**Purpose**: Minimal tools for targeted file fixes.

**Value**:
```python
frozenset({"Read", "Write", "Edit"})
```

**Used By**: `FixerAgent`

**Rationale**: Fixers receive explicit file paths and don't need search capabilities. This is the smallest viable tool set for code modification.

---

### ISSUE_FIXER_TOOLS

**Purpose**: Issue resolution with file search capability.

**Value**:
```python
frozenset({"Read", "Write", "Edit", "Glob", "Grep"})
```

**Used By**: `IssueFixerAgent`

**Rationale**: Issue fixers may need to search for relevant files when investigating GitHub issues. Identical to IMPLEMENTER_TOOLS.

---

### GENERATOR_TOOLS

**Purpose**: No tools for text generation agents.

**Value**:
```python
frozenset()
```

**Used By**: `GeneratorAgent`, `CommitMessageGenerator`, `PRDescriptionGenerator`, `CodeAnalyzer`, `ErrorExplainer`

**Rationale**: Generators produce text from provided context. They don't need to read files or execute commands - all context is provided in their prompts.

---

## Usage Examples

### Agent Construction

```python
from maverick.agents.tools import IMPLEMENTER_TOOLS

class ImplementerAgent(MaverickAgent):
    def __init__(self, config: AgentConfig):
        super().__init__(
            name="implementer",
            system_prompt=IMPLEMENTER_SYSTEM_PROMPT,
            allowed_tools=list(IMPLEMENTER_TOOLS),  # Convert to list
            model=config.model,
        )
```

### Tool Set Composition (Advanced)

```python
from maverick.agents.tools import REVIEWER_TOOLS, FIXER_TOOLS

# Read-write tools (union of reviewer and fixer)
READ_WRITE_TOOLS = REVIEWER_TOOLS | FIXER_TOOLS
# Result: {"Read", "Glob", "Grep", "Write", "Edit"}

# Common tools (intersection)
COMMON_TOOLS = REVIEWER_TOOLS & IMPLEMENTER_TOOLS
# Result: {"Read", "Glob", "Grep"}
```

### Testing Tool Permissions

```python
from maverick.agents.tools import IMPLEMENTER_TOOLS
from maverick.agents.base import BUILTIN_TOOLS

def test_implementer_tools_are_valid():
    assert IMPLEMENTER_TOOLS.issubset(BUILTIN_TOOLS)

def test_implementer_tools_no_bash():
    assert "Bash" not in IMPLEMENTER_TOOLS
```

---

## Constraints

1. **Immutability**: All tool sets are `frozenset` - they cannot be modified at runtime.

2. **Validation**: All tools in each set must exist in `BUILTIN_TOOLS` (from `base.py`).

3. **Subset Requirement**: Tool sets define subsets of available tools, not additions.

4. **No MCP Tools**: Tool sets only contain built-in tools. MCP tools are configured separately via `mcp_servers`.

---

## Error Handling

If an agent is constructed with tools not in `BUILTIN_TOOLS`, `InvalidToolError` is raised by `MaverickAgent._validate_tools()`.

```python
# This would fail at agent construction:
class BadAgent(MaverickAgent):
    def __init__(self):
        super().__init__(
            allowed_tools=["Read", "NonexistentTool"],  # InvalidToolError
            ...
        )
```
