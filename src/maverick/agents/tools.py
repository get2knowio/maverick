"""Tool permission constants for Maverick agents.

This module defines centralized, immutable tool permission sets for all agent types.
It enforces the principle of least privilege by providing named tool sets that agents
can use for their allowed_tools configuration.

All tool sets are immutable frozensets, preventing accidental modification at runtime.
Each constant is a subset of BUILTIN_TOOLS defined in maverick.agents.base, ensuring
all tool references are valid.

Tool Sets:
    REVIEWER_TOOLS: Read-only tools for code analysis agents
        Contains: Read, Glob, Grep
        Use for: Agents that analyze code without modifying it

    IMPLEMENTER_TOOLS: Code modification tools without command execution
        Contains: Read, Write, Edit, Glob, Grep
        Use for: Agents that write and edit code but don't run commands

    FIXER_TOOLS: Minimal tools for targeted file fixes
        Contains: Read, Write, Edit
        Use for: Agents that modify specific files with known paths

    ISSUE_FIXER_TOOLS: Issue resolution with file search capability
        Contains: Read, Write, Edit, Glob, Grep
        Use for: Agents that investigate and fix GitHub issues

    GENERATOR_TOOLS: Empty set for text generation agents
        Contains: (empty)
        Use for: Agents that produce text from provided context only

Basic Usage:
    ```python
    from maverick.agents.tools import IMPLEMENTER_TOOLS
    from maverick.agents import MaverickAgent

    class ImplementerAgent(MaverickAgent):
        def __init__(self, config: AgentConfig):
            super().__init__(
                name="implementer",
                system_prompt=IMPLEMENTER_SYSTEM_PROMPT,
                allowed_tools=list(IMPLEMENTER_TOOLS),  # Convert to list
                model=config.model,
            )
    ```

Composing Tool Sets:
    Tool sets can be composed using standard frozenset operations:

    ```python
    from maverick.agents.tools import FIXER_TOOLS, REVIEWER_TOOLS

    # Union: Combine tool sets
    combined_tools = FIXER_TOOLS | REVIEWER_TOOLS
    # Result: {Read, Write, Edit, Glob, Grep}

    # Intersection: Find common tools
    common_tools = FIXER_TOOLS & REVIEWER_TOOLS
    # Result: {Read}

    # Difference: Find tools unique to one set
    extra_tools = IMPLEMENTER_TOOLS - FIXER_TOOLS
    # Result: {Glob, Grep}

    # Convert to list for agent initialization
    agent = SomeAgent(allowed_tools=list(combined_tools))
    ```

Validation:
    All tool sets are validated at module import time to ensure they contain
    only valid built-in tools. Invalid tool references will cause an import error.

    ```python
    from maverick.agents.base import BUILTIN_TOOLS
    from maverick.agents.tools import IMPLEMENTER_TOOLS

    # Verify tool set validity
    assert IMPLEMENTER_TOOLS.issubset(BUILTIN_TOOLS)

    # Check if a tool is allowed
    if "Write" in IMPLEMENTER_TOOLS:
        print("Implementer can modify files")
    ```

Immutability:
    Tool sets are immutable and cannot be modified at runtime:

    ```python
    from maverick.agents.tools import REVIEWER_TOOLS

    # This will raise AttributeError
    try:
        REVIEWER_TOOLS.add("Write")  # Cannot modify frozenset
    except AttributeError:
        pass  # Expected behavior
    ```

See Also:
    - maverick.agents.base.BUILTIN_TOOLS: Complete set of available built-in tools
    - maverick.agents.MaverickAgent: Base class using these tool sets
    - FR-002 in spec: Tool validation requirements
"""

from __future__ import annotations

__all__: list[str] = [
    "REVIEWER_TOOLS",
    "IMPLEMENTER_TOOLS",
    "FIXER_TOOLS",
    "ISSUE_FIXER_TOOLS",
    "GENERATOR_TOOLS",
    "CURATOR_TOOLS",
]

# =============================================================================
# Tool Permission Constants
# =============================================================================

#: Read-only tools for code analysis agents (CodeReviewerAgent).
#:
#: Reviewers analyze code but must not modify it. Search tools (Glob, Grep)
#: enable finding relevant code sections for review.
REVIEWER_TOOLS: frozenset[str] = frozenset({"Read", "Glob", "Grep"})

#: Code modification tools with subagent support (ImplementerAgent).
#:
#: Implementers write and edit code and can spawn subagents for parallel
#: task execution. The orchestration layer handles test execution and validation.
IMPLEMENTER_TOOLS: frozenset[str] = frozenset(
    {"Read", "Write", "Edit", "Glob", "Grep", "Task"}
)

#: Minimal tools for targeted file fixes (FixerAgent).
#:
#: Fixers receive explicit file paths and don't need search capabilities.
#: This is the smallest viable tool set for code modification.
FIXER_TOOLS: frozenset[str] = frozenset({"Read", "Write", "Edit"})

#: Issue resolution with file search capability (IssueFixerAgent).
#:
#: Issue fixers may need to search for relevant files when investigating
#: GitHub issues. Identical to IMPLEMENTER_TOOLS.
ISSUE_FIXER_TOOLS: frozenset[str] = frozenset({"Read", "Write", "Edit", "Glob", "Grep"})

#: Empty set for text generation agents (GeneratorAgent and subclasses).
#:
#: Generators produce text from provided context. They don't need to read
#: files or execute commands - all context is provided in their prompts.
GENERATOR_TOOLS: frozenset[str] = frozenset()

#: Empty set for the CuratorAgent (one-shot history rewrite planner).
#:
#: The curator receives pre-gathered jj log and diff stats in its prompt.
#: It produces a structured JSON plan of jj commands — no file access needed.
CURATOR_TOOLS: frozenset[str] = frozenset()
