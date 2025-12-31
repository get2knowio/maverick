# Research: Agent Tool Permissions

**Feature Branch**: `021-agent-tool-permissions`
**Date**: 2025-12-19

## Research Questions

This document captures research findings for all unknowns identified in the Technical Context and feature specification.

---

## 1. Claude Agent SDK `allowed_tools` Behavior

### Question
How does the Claude Agent SDK handle tools not in the `allowed_tools` list? What happens when an agent attempts to use an unauthorized tool?

### Decision
The SDK filters tools at the configuration level - Claude only sees and can invoke tools that are in the `allowed_tools` list. The SDK does not present unauthorized tools to the model.

### Rationale
- The SDK documentation confirms that `allowed_tools` explicitly controls which tools Claude can access
- When configured with `allowed_tools=["Read", "Glob", "Grep"]`, Claude only receives those 3 tools
- This is a whitelisting approach - only listed tools are available
- No error handling is needed for unauthorized tool attempts because the model never sees those tools

### Alternatives Considered
1. **Runtime rejection**: SDK could allow Claude to see all tools but reject unauthorized calls - Not how it works
2. **canUseTool callback**: Could handle via callback - Only fires for uncovered cases, not for `allowed_tools` filtering

### Source
- [Claude Agent SDK Documentation - Permissions](https://platform.claude.com/docs/en/agent-sdk/permissions)
- [Claude Agent SDK Overview](https://platform.claude.com/docs/en/api/agent-sdk/overview)

### Known Issue (Resolved)
GitHub issue #361 reported that `allowed_tools` was being ignored in SDK versions 0.1.5-0.1.9. This issue was marked **COMPLETED** on November 25, 2025, indicating the fix has been deployed. Current SDK versions should properly respect `allowed_tools`.

---

## 2. MultiEdit Tool Availability

### Question
The spec mentions "MultiEdit" as a tool for ImplementerAgent. Does this tool exist? Should it be included?

### Decision
**Remove MultiEdit from requirements.** The tool does not exist in the current BUILTIN_TOOLS set and is not documented in the SDK.

### Rationale
- Searched codebase: `BUILTIN_TOOLS` in `base.py` does not include "MultiEdit"
- SDK documentation lists: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch, NotebookEdit, TodoWrite, Task, ExitPlanMode
- No "MultiEdit" documented
- The `Edit` tool handles single-file edits; batch operations would require multiple Edit calls
- Spec reference appears to be from an earlier design (spec 004) that assumed MultiEdit existed

### Alternatives Considered
1. **Implement MultiEdit**: Create a custom MCP tool - Out of scope for this feature
2. **Use multiple Edit calls**: Already works - This is the current approach
3. **Alias to Edit**: Create an alias - Unnecessary complexity

### Impact on Spec
- FR-002 should read: "Read, Write, Edit, Glob, and Grep tools" (not including MultiEdit)
- Acceptance Scenario 1 in User Story 1 should be updated similarly

---

## 3. Tool Set Constants Best Practices

### Question
How should tool set constants be implemented in Python for maximum type safety and immutability?

### Decision
Use `frozenset[str]` constants in a dedicated module with clear naming conventions.

### Rationale
- `frozenset` is immutable (cannot be accidentally modified)
- Hashable (can be used as dict keys if needed)
- Set operations available (union, intersection) for composition
- Type hint `frozenset[str]` provides IDE support
- Module-level constants with SCREAMING_SNAKE_CASE per constitution

### Implementation Pattern
```python
# maverick/agents/tools.py
"""Centralized tool permission sets for Maverick agents.

This module defines the tool sets available to each agent type,
enforcing the principle of least privilege.
"""
from __future__ import annotations

# Read-only tools for code analysis
REVIEWER_TOOLS: frozenset[str] = frozenset({
    "Read",
    "Glob",
    "Grep",
})

# Code modification tools (no execution)
IMPLEMENTER_TOOLS: frozenset[str] = frozenset({
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
})

# Minimal fix tools (targeted edits only)
FIXER_TOOLS: frozenset[str] = frozenset({
    "Read",
    "Write",
    "Edit",
})

# Issue resolution tools (same as implementer)
ISSUE_FIXER_TOOLS: frozenset[str] = frozenset({
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
})

# Generator agents have no tools
GENERATOR_TOOLS: frozenset[str] = frozenset()
```

### Alternatives Considered
1. **Enum**: More structure but less flexible for set operations
2. **tuple**: Immutable but no set operations, order matters
3. **list**: Mutable - rejected for safety
4. **TypedDict**: Overkill for simple string sets

---

## 4. System Prompt Patterns for Constrained Agents

### Question
What guidance should system prompts include for agents with reduced tool access?

### Decision
System prompts should:
1. Explicitly state the agent's role boundary
2. Indicate that context is pre-gathered
3. Not mention unavailable capabilities
4. Focus on the agent's judgment task

### Rationale
- Avoids wasted tokens on unavailable actions
- Reduces confusion about agent responsibilities
- Aligns with separation of concerns principle
- Makes agent behavior more predictable

### Implementation Pattern

**Before (current - problematic)**:
```
You are a code reviewer. Analyze the changes and:
- Run git commands to see the diff
- Execute tests to verify changes
- Create issues for problems found
```

**After (constrained)**:
```
You are a code reviewer analyzing pre-gathered context.

Your role:
- Analyze the provided git diff and file contents
- Identify issues, security concerns, and improvements
- Return structured findings

The orchestration layer provides:
- Git diffs (already gathered)
- Relevant file contents (already gathered)
- Convention guidelines

Focus solely on analysis. Do not attempt to:
- Execute commands
- Modify files
- Create external resources

Your output will be processed by the orchestration layer.
```

### Key Elements
1. **Role clarity**: "analyzing pre-gathered context"
2. **Explicit scope**: What the agent should do
3. **Context explanation**: Where data comes from
4. **Negative guidance**: What not to attempt
5. **Output handling**: Where results go

---

## 5. FixerAgent Design

### Question
What distinguishes FixerAgent from IssueFixerAgent? Why is a separate agent needed?

### Decision
FixerAgent is a minimal, targeted agent for validation fixes with the smallest possible tool set.

### Rationale

| Aspect | FixerAgent | IssueFixerAgent |
|--------|------------|-----------------|
| **Purpose** | Apply specific fixes to known files | Resolve GitHub issues |
| **Scope** | Single file, pre-identified | May need to search |
| **Tools** | Read, Write, Edit (3 tools) | Read, Write, Edit, Glob, Grep (5 tools) |
| **Context** | Given exact file path and error | Must investigate issue |
| **System Prompt** | Minimal, focused | Analysis-oriented |

**Use Cases**:
- FixerAgent: "Fix linting error in src/utils.py line 42"
- IssueFixerAgent: "Fix issue #123: Users can't log in"

### Alternatives Considered
1. **Use IssueFixerAgent for everything**: Larger tool set than needed for targeted fixes
2. **Add mode to IssueFixerAgent**: Complexity without benefit
3. **FixerAgent only**: Can't handle open-ended issue investigation

---

## 6. Workflow Refactoring Requirements

### Question
How should workflows provide context to constrained agents?

### Decision
Workflows must pre-gather all context before invoking agents. This is already the pattern established in spec 020 (workflow refactor).

### Rationale
- Spec 020 established Python orchestration for external operations
- Git operations already centralized in `GitOperations` utility
- Context building already exists via `ContextBuilder`
- Agents receive context in their prompts, not via tools

### Implementation Pattern
```python
# Workflow provides context, agent analyzes
async def _run_review(self, diff: str, files: dict[str, str]) -> ReviewResult:
    prompt = f"""
    ## Git Diff
    {diff}

    ## File Contents
    {format_files(files)}

    Analyze these changes and provide findings.
    """
    result = await self.reviewer.execute(AgentContext(prompt=prompt))
    return parse_review_result(result)
```

### No Changes Needed
The workflow refactor (spec 020) already establishes this pattern. This feature enforces it by removing tools that would bypass orchestration.

---

## Summary of Decisions

| Research Area | Decision | Impact |
|---------------|----------|--------|
| SDK `allowed_tools` | Works as documented (whitelist) | Confirms SDK handles unauthorized tools |
| MultiEdit | Does not exist, remove from spec | FR-002 updated to exclude MultiEdit |
| Tool constants | `frozenset[str]` in tools.py | New module created |
| System prompts | Include constrained agent guidance | All prompts updated |
| FixerAgent | Minimal agent for validation fixes | New agent class |
| Workflow context | Already handled by spec 020 | No additional changes |

---

## References

- [Claude Agent SDK - Permissions](https://platform.claude.com/docs/en/agent-sdk/permissions)
- [Claude Agent SDK - Overview](https://platform.claude.com/docs/en/api/agent-sdk/overview)
- [GitHub Issue #361 - allowed_tools ignored](https://github.com/anthropics/claude-agent-sdk-python/issues/361) (RESOLVED)
- Maverick Constitution v1.1.0 (`.specify/memory/constitution.md`)
- Spec 020: Workflow Refactor
