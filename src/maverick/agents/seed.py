"""RunwaySeedAgent for brownfield codebase analysis.

Analyzes project context (git log, directory tree, config files) and produces
semantic markdown files for the runway knowledge store.
"""

from __future__ import annotations

from typing import Any

from maverick.agents.base import MaverickAgent
from maverick.runway.seed import SeedContext, SeedOutput

__all__ = ["RunwaySeedAgent"]

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_INSTRUCTIONS = """\
You are a codebase analyst. You receive structured context about a software
project and produce a set of markdown knowledge files that capture the
project's architecture, conventions, review patterns, and technology stack.

## Your Task

Analyze the provided project context and produce exactly 4 markdown files.
Each file should be concise, actionable, and useful for an AI agent that will
later implement features and review code in this project.

## Output Files

1. **architecture.md** — Project structure and design patterns:
   - Module/package organization and responsibilities
   - Key abstractions and their relationships
   - Data flow and control flow patterns
   - Entry points and public APIs

2. **conventions.md** — Coding style and patterns:
   - Naming conventions (files, classes, functions, variables)
   - Import organization patterns
   - Error handling patterns
   - Testing patterns and conventions
   - Common idioms used in the codebase

3. **review-patterns.md** — Common issues and review themes:
   - Recurring patterns in commit messages that suggest past issues
   - Areas of the codebase that change frequently (potential hotspots)
   - Common categories of changes (features, fixes, refactors)
   - Risks or complexity areas to watch during reviews

4. **tech-stack.md** — Technologies and tooling:
   - Programming languages and versions
   - Frameworks and major dependencies
   - Build tools and package managers
   - Testing frameworks
   - Linting, formatting, and CI tools

## Guidelines

- Be specific to THIS project, not generic advice
- Reference actual file paths and module names from the directory tree
- Keep each file under 2000 words — be concise
- Use markdown headers, bullet points, and code references
- If git history is empty, focus on what you can infer from the tree and config files
- If information is insufficient for a section, say so briefly rather than guessing
"""


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------


class RunwaySeedAgent(MaverickAgent[SeedContext, SeedOutput]):
    """Agent that analyzes a codebase and produces runway seed files.

    Uses no tools — all context is provided in the prompt. Returns structured
    JSON matching the SeedOutput schema.
    """

    def __init__(self) -> None:
        super().__init__(
            name="runway_seed",
            instructions=_INSTRUCTIONS,
            allowed_tools=[],
            output_model=SeedOutput,
        )

    def build_prompt(self, context: SeedContext | dict[str, Any]) -> str:
        """Build prompt from gathered project context."""
        if isinstance(context, dict):
            context = SeedContext(**context)

        sections: list[str] = []

        # Git log
        if context.git_log:
            lines = [
                f"- {c.short_sha} {c.message} ({c.author})" for c in context.git_log
            ]
            sections.append("## Recent Git History\n\n" + "\n".join(lines))
        else:
            sections.append("## Recent Git History\n\n(No git history available)")

        # Directory tree
        if context.directory_tree:
            sections.append(
                "## Directory Tree\n\n```\n" + context.directory_tree + "\n```"
            )

        # Config files
        if context.config_files:
            parts: list[str] = []
            for name, content in context.config_files.items():
                parts.append(f"### {name}\n\n```\n{content}\n```")
            sections.append("## Configuration Files\n\n" + "\n\n".join(parts))

        # File type distribution
        if context.file_type_counts:
            top = list(context.file_type_counts.items())[:20]
            lines = [f"- {ext}: {count}" for ext, count in top]
            sections.append("## File Type Distribution\n\n" + "\n".join(lines))

        return (
            "Analyze the following project context and produce the 4 semantic "
            "knowledge files as described in your instructions.\n\n"
            + "\n\n".join(sections)
        )
