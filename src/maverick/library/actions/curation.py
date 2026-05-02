"""Helpers for the ``maverick land`` curation flow.

The bundled OpenCode persona :file:`maverick.curator.md` is the source
of truth for the curator's system prompt and behaviour.  This module
hosts the deterministic Python pieces that wrap around it:

* :func:`build_curator_prompt` — turns gathered jj-log + commit-stats
  context into the per-call user message.
* :func:`parse_curation_plan` — robustly parses the curator's JSON
  array response (markdown fences, trailing prose) into a validated
  list of jj plan steps.
* :func:`extract_bead_ids` and :func:`ensure_refs_trailers` — provide
  the ``Refs:`` trailer safety net that guarantees every rewritten
  commit retains bead provenance even when the LLM forgets to follow
  the system-prompt instruction (FUTURE.md §3.9).

Originally these lived on ``maverick.agents.curator.CuratorAgent``.
That class was deleted when the OpenCode-substrate migration
collapsed the text-mode :class:`MaverickAgent` path; the helpers
remain because the deterministic plan execution still needs them.
"""

from __future__ import annotations

import json
import re
from typing import Any

from maverick.logging import get_logger

__all__ = [
    "build_curator_prompt",
    "ensure_refs_trailers",
    "extract_bead_ids",
    "parse_curation_plan",
]

logger = get_logger(__name__)

# Matches ``bead(<id>):`` prefix in pre-curator commit subjects, where
# ``<id>`` is e.g. ``sample_maverick_project-e6c.8``. The id may contain
# letters, digits, dashes, dots, and underscores. Anchored at line start
# so we don't match the substring inside an unrelated body sentence.
_BEAD_PREFIX_RE = re.compile(r"^bead\(([^)]+)\):", re.MULTILINE)

# Detects an existing ``Refs:`` trailer line so post-processing doesn't
# double-inject when the curator already followed the prompt instruction.
_REFS_TRAILER_RE = re.compile(r"^Refs:\s*\S", re.MULTILINE)

# jj subcommands the curator is permitted to plan.
_VALID_COMMANDS: frozenset[str] = frozenset({"squash", "describe", "rebase"})


def build_curator_prompt(context: dict[str, Any]) -> str:
    """Construct the curator user prompt from gathered commit context.

    Args:
        context: Dict with:
            - ``commits``: list of ``{change_id, description, stats}``
            - ``log_summary``: full ``jj log --stat`` output

    Returns:
        Complete user-prompt text ready to send to the
        :file:`maverick.curator` persona.
    """
    commits = context.get("commits", [])
    log_summary = context.get("log_summary", "")

    parts: list[str] = [
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


def parse_curation_plan(raw_output: str) -> list[dict[str, Any]]:
    """Parse the curator's raw JSON output into a validated plan list.

    Handles common LLM quirks: markdown fences, trailing text. Returns
    an empty list on parse failure (logged at WARN) — the caller is
    expected to treat that as a no-op plan.
    """
    text = raw_output.strip()

    # Strip markdown code fences if present.
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [ln for ln in lines if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()

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

    validated: list[dict[str, Any]] = []
    for step in plan:
        if not isinstance(step, dict):
            continue
        command = step.get("command", "")
        if command not in _VALID_COMMANDS:
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
    ``bead({id}): {title}``. This helper extracts the ``{id}`` from
    every such prefix it finds. Snapshot commits and other non-bead
    commits return an empty list. Results preserve order and
    de-duplicate.
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
    ends in a ``Refs:`` trailer pointing at the source bead(s). When
    the curator already produced a trailer (it followed the system
    prompt), this is a no-op. When it didn't, append a trailer derived
    from the bead IDs in the *target change_id*'s original description.

    Caveat: this safety net only knows about the describe target's own
    bead IDs. If the curator squashed other commits into the target,
    those squashed-in beads are *not* recovered here — the system
    prompt is what teaches the LLM to attribute squashed beads, and we
    rely on it for that case. The post-process guarantees a trailer
    exists for every named target; the LLM is responsible for
    completeness when squashes are involved.

    Args:
        plan: Validated plan list from :func:`parse_curation_plan`.
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
