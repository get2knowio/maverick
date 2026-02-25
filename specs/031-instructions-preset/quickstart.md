# Quickstart: Creating Agents with Instructions Preset

**Feature**: 031-instructions-preset
**Date**: 2026-02-22

## Overview

Maverick agents use the Claude Code system prompt preset as their foundation. You provide agent-specific guidance via the `instructions` parameter, which is appended to the preset. This gives every interactive agent Claude Code's built-in capabilities (tool usage, code editing, safety guardrails) automatically.

## Creating an Interactive Agent (MaverickAgent)

Interactive agents use tools, have multi-turn conversations, and benefit from the Claude Code preset.

```python
from __future__ import annotations

from maverick.agents.base import MaverickAgent
from maverick.agents.context import AgentContext
from maverick.agents.result import AgentResult

class MyReviewerAgent(MaverickAgent[AgentContext, AgentResult]):
    """Agent that reviews documentation for consistency."""

    def __init__(self) -> None:
        super().__init__(
            name="doc-reviewer",
            instructions=(
                "You are a documentation reviewer. Check for:\n"
                "- Consistency between code and docs\n"
                "- Missing API documentation\n"
                "- Broken links and outdated examples\n"
                "\n"
                "Report findings in a structured list with severity."
            ),
            allowed_tools=["Read", "Glob", "Grep"],  # Read-only tools
        )

    async def execute(self, context: AgentContext) -> AgentResult:
        prompt = f"Review documentation in {context.cwd}"
        async for message in self.query(prompt, cwd=context.cwd):
            pass  # Process messages
        return AgentResult.success_result(output="Review complete")
```

**What happens under the hood**:
- The Claude Code preset provides: file editing conventions, tool usage patterns, safety guardrails
- Your `instructions` are appended: the agent knows its specific role
- Project config (CLAUDE.md) is loaded: project conventions are respected
- User config is loaded: personal preferences are applied

## Creating a One-Shot Generator (GeneratorAgent)

Generators produce structured text in a single turn without tools. They use `system_prompt` directly (no preset).

```python
from __future__ import annotations

from typing import Any

from maverick.agents.generators.base import GeneratorAgent
from maverick.agents.result import AgentUsage

class SummaryGenerator(GeneratorAgent):
    """Generates concise summaries of code changes."""

    def __init__(self) -> None:
        super().__init__(
            name="summary-generator",
            system_prompt=(
                "You generate concise, one-paragraph summaries of code changes. "
                "Focus on the 'why' (motivation), not the 'what' (file list). "
                "Output ONLY the summary paragraph, no preamble."
            ),
        )

    async def generate(
        self,
        context: dict[str, Any],
        return_usage: bool = False,
    ) -> str | tuple[str, AgentUsage]:
        prompt = f"Summarize these changes:\n\n{context['diff']}"
        if return_usage:
            return await self._query_with_usage(prompt)
        return await self._query(prompt)
```

## Key Differences

| Aspect | MaverickAgent | GeneratorAgent |
|--------|--------------|----------------|
| **Base prompt** | Claude Code preset (automatic) | Direct `system_prompt` (you provide) |
| **Parameter name** | `instructions` (appended to preset) | `system_prompt` (replaces everything) |
| **Tools** | Configurable via `allowed_tools` | None (no tools) |
| **Turns** | Multi-turn (interactive) | Single-turn (one-shot) |
| **Project config** | Loaded automatically via `setting_sources` | Not loaded |
| **Use case** | Implementation, review, fixing | Text generation, formatting |

## Common Patterns

### Empty Instructions

An agent with empty instructions operates using the Claude Code preset alone:

```python
# Valid — agent has full Claude Code capabilities with no additional role guidance
agent = MyAgent(name="general", instructions="", allowed_tools=["Read", "Write"])
```

### Rich Instructions with Markdown

Instructions can contain markdown formatting:

```python
instructions = """
You are a **security auditor**. Focus on:

## Scope
- OWASP Top 10 vulnerabilities
- SQL injection, XSS, command injection

## Output Format
Report each finding as:
- **Severity**: Critical/High/Medium/Low
- **Location**: file:line
- **Description**: What's wrong
- **Remediation**: How to fix
"""
```

### Instructions with Dynamic Content

Instructions can be templated with runtime values:

```python
TEMPLATE = """You are a code implementer for the {project_name} project.

Follow these conventions:
{conventions}

Validation commands:
{validation_commands}
"""

instructions = TEMPLATE.format(
    project_name="maverick",
    conventions=load_conventions(),
    validation_commands="\n".join(validation_cmds),
)
```
