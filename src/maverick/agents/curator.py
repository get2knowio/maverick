"""CuratorAgent — one-shot history rewrite planner.

Receives pre-gathered ``jj log`` and per-commit diff stats.  Returns a
structured JSON plan of jj commands to reorganize history before pushing.

Uses CURATOR_TOOLS (empty frozenset) — no file system access needed.
All context is provided in the prompt by the ``land`` command.
"""

from __future__ import annotations

import json
import re
from typing import Any

from maverick.agents.generator_base import GeneratorAgent
from maverick.agents.tools import CURATOR_TOOLS
from maverick.logging import get_logger

__all__ = ["CuratorAgent", "ensure_refs_trailers", "extract_bead_ids"]

logger = get_logger(__name__)

# Matches ``bead(<id>):`` prefix in pre-curator commit subjects, where
# ``<id>`` is e.g. ``sample_maverick_project-e6c.8``. The id may contain
# letters, digits, dashes, dots, and underscores. Anchored at line start
# so we don't match the substring inside an unrelated body sentence.
_BEAD_PREFIX_RE = re.compile(r"^bead\(([^)]+)\):", re.MULTILINE)

# Detects an existing ``Refs:`` trailer line so post-processing doesn't
# double-inject when the curator already followed the prompt instruction.
_REFS_TRAILER_RE = re.compile(r"^Refs:\s*\S", re.MULTILINE)

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

   **Strip pipeline mechanics from the subject and body**: remove the \
``bead(project-xyz.N):`` prefix from the subject, remove follow-up / \
re-plan phrasing (``Address review findings from ...``), and write the \
message as if a developer authored it — conventional commit format \
(``type(scope): imperative description``).  The permanent git history \
must read like human-authored commits, not pipeline output.

   **BUT preserve bead provenance as a `Refs:` trailer.**  At the bottom \
of every rewritten message, append a single trailer line listing the \
bead IDs that contributed to the resulting commit.  Format:

   ```
   Refs: project-xyz.N, project-xyz.M
   ```

   - One ``Refs:`` line per ``describe``, comma-separated values.
   - List **every** bead from the source commits being collapsed into \
this commit.  When you ``squash -r A`` and then ``describe`` the squash \
target, the trailer must include A's bead AND the target's bead.
   - Bead IDs come from the source commit subjects: extract the ``id`` \
from each ``bead(id):`` prefix you encounter in the input.
   - If a source commit had no ``bead(...)`` prefix (e.g. a snapshot \
commit), it contributes no entry to the trailer.
   - If the resulting commit has zero bead sources (pure snapshot), \
omit the trailer entirely.
   - Separate the trailer from the body with a blank line, matching \
the ``Signed-off-by:`` / ``Co-Authored-By:`` convention.

   The trailer is the join key from public git history back to runway \
(provider, model, prompt history) — eval tooling depends on it. \
Reads as human-authored, since ``Refs:`` is a standard git trailer.
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

    def build_prompt(self, context: dict[str, Any]) -> str:
        """Construct the prompt string from commit context (FR-017).

        Args:
            context: Dict with:
                - commits: list of {change_id, description, stats}
                - log_summary: Full jj log --stat output

        Returns:
            Complete prompt text ready for the agent.
        """
        commits = context.get("commits", [])
        log_summary = context.get("log_summary", "")

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

        return "\n".join(parts)

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


def extract_bead_ids(commit_description: str) -> list[str]:
    """Return bead IDs found in a pre-curator commit description.

    Pre-curator commits are written by ``commit_bead`` as
    ``bead({id}): {title}``. This helper extracts the ``{id}`` from every
    such prefix it finds. Snapshot commits and other non-bead commits
    return an empty list. Results preserve order and de-duplicate.
    """
    seen: set[str] = set()
    out: list[str] = []
    for match in _BEAD_PREFIX_RE.finditer(commit_description):
        bead_id = match.group(1).strip()
        if bead_id and bead_id not in seen:
            seen.add(bead_id)
            out.append(bead_id)
    return out


def ensure_refs_trailers(
    plan: list[dict[str, Any]],
    commits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Safety net for the ``Refs:`` trailer (FUTURE.md §3.9).

    For each ``describe`` step in *plan*, ensure the ``-m`` argument
    ends in a ``Refs:`` trailer pointing at the source bead(s). When the
    curator already produced a trailer (it followed the system prompt),
    this is a no-op. When it didn't, append a trailer derived from the
    bead IDs in the *target change_id*'s original description.

    Caveat: this safety net only knows about the describe target's own
    bead IDs. If the curator squashed other commits into the target,
    those squashed-in beads are *not* recovered here — the system
    prompt is what teaches the LLM to attribute squashed beads, and we
    rely on it for that case. The post-process guarantees a trailer
    exists for every named target; the LLM is responsible for
    completeness when squashes are involved.

    Args:
        plan: Validated plan list from :meth:`CuratorAgent.parse_plan`.
        commits: Original commit list passed to the curator. Each entry
            must have ``change_id`` and ``description`` keys.

    Returns:
        A new plan list with ``-m`` arguments rewritten as needed.
    """
    by_change_id = {c["change_id"]: c for c in commits if "change_id" in c}
    out: list[dict[str, Any]] = []
    for step in plan:
        if step.get("command") != "describe":
            out.append(step)
            continue
        args = list(step.get("args", []))
        change_id, message = _extract_describe_target_and_message(args)
        if change_id is None or message is None:
            # Malformed describe — leave it alone; execute_curation_plan
            # will surface the error.
            out.append(step)
            continue
        if _REFS_TRAILER_RE.search(message):
            # Curator already added a trailer; trust it.
            out.append(step)
            continue
        source = by_change_id.get(change_id)
        if source is None:
            out.append(step)
            continue
        bead_ids = extract_bead_ids(source.get("description", ""))
        if not bead_ids:
            # Snapshot or other non-bead commit — no trailer to add.
            out.append(step)
            continue
        new_message = _append_refs_trailer(message, bead_ids)
        new_args = _replace_describe_message(args, new_message)
        logger.debug(
            "curator: injected Refs trailer for change_id=%s beads=%s",
            change_id,
            bead_ids,
        )
        out.append({**step, "args": new_args})
    return out


def _extract_describe_target_and_message(
    args: list[str],
) -> tuple[str | None, str | None]:
    """Pull the ``change_id`` and ``-m`` value out of a describe args list."""
    change_id: str | None = None
    message: str | None = None
    i = 0
    while i < len(args):
        token = args[i]
        if token == "-r" and i + 1 < len(args):
            change_id = args[i + 1]
            i += 2
            continue
        if token == "-m" and i + 1 < len(args):
            message = args[i + 1]
            i += 2
            continue
        i += 1
    return change_id, message


def _replace_describe_message(args: list[str], new_message: str) -> list[str]:
    """Return a copy of *args* with the ``-m`` value replaced."""
    out: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "-m" and i + 1 < len(args):
            out.extend(["-m", new_message])
            i += 2
            continue
        out.append(args[i])
        i += 1
    return out


def _append_refs_trailer(message: str, bead_ids: list[str]) -> str:
    """Append ``Refs: bead-id, ...`` to *message*, preserving body shape.

    Adds a blank line between the body and the trailer when the body
    has content, matching the ``Signed-off-by:`` / ``Co-Authored-By:``
    convention. Strips trailing whitespace from the body first so we
    don't double-blank.
    """
    body = message.rstrip()
    trailer = "Refs: " + ", ".join(bead_ids)
    if not body:
        return trailer
    return f"{body}\n\n{trailer}"


# Re-export CURATOR_TOOLS so consumers can verify the tool set
_ = CURATOR_TOOLS  # ensure the import is used
