"""CuratorAgent — one-shot history rewrite planner.

Receives pre-gathered ``jj log`` and per-commit diff stats.  Returns a
structured JSON plan of jj commands to reorganize history before pushing.

Uses CURATOR_TOOLS (empty frozenset) — no file system access needed.
All context is provided in the prompt by the ``land`` command.
"""

from __future__ import annotations

import json
from typing import Any

from maverick.agents.generators.base import GeneratorAgent
from maverick.agents.result import AgentUsage
from maverick.agents.tools import CURATOR_TOOLS
from maverick.logging import get_logger

__all__ = ["CuratorAgent"]

logger = get_logger(__name__)

# =============================================================================
# System prompt
# =============================================================================

SYSTEM_PROMPT = """\
You are a commit-history curator for a software project that uses Jujutsu (jj) \
for version control.

You will receive a list of commits (change ID, description, and file-stats) \
between a base revision and the current working copy.  Your job is to produce \
a *plan* — a JSON array of jj commands — that reorganizes these commits into \
cleaner, more logical history before they are pushed.

## Rules

1. **Squash fix/fixup/lint/format/typecheck commits** into their logical \
parent.  Use ``jj squash -r <change_id>`` (squashes into parent).
2. **Improve commit messages** that are vague, duplicated, or inconsistent. \
Use ``jj describe -r <change_id> -m "<new message>"``.
3. **Reorder commits** for logical flow when independent changes are \
interleaved.  Use ``jj rebase -r <change_id> --after <target_id>``.
4. **Never split commits** — that is too risky for a one-shot plan.
5. **Be conservative** — only propose changes with clear benefit.  If the \
history already looks clean, return an empty array ``[]``.
6. Process commits from newest to oldest when squashing to avoid invalidating \
change IDs.

## Output format

Return ONLY a JSON array (no markdown fences, no explanation outside the JSON). \
Each element is an object:

```
{"command": "<jj subcommand>", "args": ["<arg1>", ...], "reason": "<why>"}
```

Valid commands: ``squash``, ``describe``, ``rebase``.

If no changes are needed, return ``[]``.
"""


# =============================================================================
# Agent class
# =============================================================================


class CuratorAgent(GeneratorAgent):
    """One-shot agent that produces a jj history rewrite plan.

    Receives commit log + per-commit stats as context.  Returns a
    structured JSON plan of jj commands to reorganize history.

    Uses CURATOR_TOOLS (empty) — no file system access needed.
    All context is pre-gathered and passed in the prompt.
    """

    def __init__(self, model: str | None = None) -> None:
        from maverick.constants import DEFAULT_MODEL

        super().__init__(
            name="curator",
            system_prompt=SYSTEM_PROMPT,
            model=model or DEFAULT_MODEL,
            temperature=0.0,
        )

    async def generate(
        self,
        context: dict[str, Any],
        return_usage: bool = False,
    ) -> str | tuple[str, AgentUsage]:
        """Generate a curation plan from commit context.

        Args:
            context: Dict with:
                - commits: list of {change_id, description, stats}
                - log_summary: Full jj log --stat output
            return_usage: If True, return (text, usage) tuple.

        Returns:
            JSON string of the curation plan, or (json_str, usage).
        """
        commits = context.get("commits", [])
        log_summary = context.get("log_summary", "")

        if not commits:
            return ("[]", AgentUsage(0, 0, None, 0)) if return_usage else "[]"

        # Build prompt with all commit data
        parts = [
            f"## Commits ({len(commits)} total)\n",
            f"### Log summary\n```\n{log_summary}\n```\n",
            "### Per-commit details\n",
        ]
        for commit in commits:
            parts.append(
                f"**{commit['change_id']}**: {commit['description']}\n"
                f"```\n{commit.get('stats', '(no stats)')}\n```\n"
            )

        prompt = "\n".join(parts)

        if return_usage:
            return await self._query_with_usage(prompt)
        return await self._query(prompt)

    def parse_plan(self, raw_output: str) -> list[dict[str, Any]]:
        """Parse the agent's raw JSON output into a plan list.

        Handles common LLM quirks: markdown fences, trailing text.

        Args:
            raw_output: Raw text from the agent.

        Returns:
            List of plan step dicts, or empty list on parse failure.
        """
        text = raw_output.strip()

        # Strip markdown code fences if present
        if text.startswith("```"):
            lines = text.splitlines()
            # Remove first and last fence lines
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            text = "\n".join(lines).strip()

        # Try to find JSON array
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1:
            logger.warning("curator: no JSON array found in response")
            return []

        try:
            plan = json.loads(text[start : end + 1])
        except json.JSONDecodeError as e:
            logger.warning("curator: JSON parse error: %s", e)
            return []

        if not isinstance(plan, list):
            logger.warning("curator: expected list, got %s", type(plan).__name__)
            return []

        # Validate each step has required keys
        valid_commands = {"squash", "describe", "rebase"}
        validated: list[dict[str, Any]] = []
        for step in plan:
            if not isinstance(step, dict):
                continue
            command = step.get("command", "")
            if command not in valid_commands:
                logger.warning("curator: skipping invalid command: %s", command)
                continue
            validated.append(
                {
                    "command": command,
                    "args": step.get("args", []),
                    "reason": step.get("reason", ""),
                }
            )

        return validated


# Re-export CURATOR_TOOLS so consumers can verify the tool set
_ = CURATOR_TOOLS  # ensure the import is used
