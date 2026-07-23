"""Optional enrichment: batched verification-command suggestions.

One model call covers every new task bead in a run (research D9). The
response is parsed into commands keyed by task ID and merged into each
task's ``## Verification`` section — no other section, and no task/edge
structure, ever changes (contracts/bead-encoding.md).
"""

from __future__ import annotations

import re

from maverick.speckit.build import IngestionPlan, PlannedBead

# Accept 2- or 3-hash headings: the batched prompt lists each task under a
# ``## T###`` heading, and models frequently echo that depth in the reply
# even though the requested format is ``### T###``. Tolerating both keeps
# enrichment from silently yielding zero commands.
_TASK_HEADING_RE = re.compile(r"^#{2,3}\s+(T\d{3,})\s*$")
_BULLET_RE = re.compile(r"^-\s+(.+)$")


def build_enrichment_prompt(new_tasks: tuple[PlannedBead, ...]) -> str:
    """Build one batched prompt covering every new task bead.

    Args:
        new_tasks: The plan's new task beads (never the epic).

    Returns:
        A single prompt requesting a fixed ``### T### `` + bullet-list
        response format, one section per task ID.
    """
    lines = [
        "For each task below, suggest 1-3 concrete shell commands that would "
        "verify the task is complete (e.g. running its tests, linting the "
        "changed files, or checking a build). Reply using EXACTLY this "
        "format, one section per task ID, in the same order as given:",
        "",
        "### T###",
        "- <command>",
        "",
    ]
    for pb in new_tasks:
        lines.append(f"## {pb.task_id}")
        lines.append(pb.definition.description)
        lines.append("")
    return "\n".join(lines)


def parse_enrichment_response(text: str) -> dict[str, list[str]]:
    """Parse the batched enrichment response into commands keyed by task ID."""
    commands: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        heading_m = _TASK_HEADING_RE.match(line.strip())
        if heading_m:
            current = heading_m.group(1)
            commands.setdefault(current, [])
            continue
        if current is None:
            continue
        bullet_m = _BULLET_RE.match(line.strip())
        if bullet_m:
            commands[current].append(bullet_m.group(1).strip())
    return commands


def _augment_verification(description: str, extra_commands: list[str]) -> str:
    """Append *extra_commands* to the description's ``## Verification`` section.

    Every other section is left untouched.
    """
    if not extra_commands:
        return description
    marker = "## Verification"
    extra_lines = "\n".join(f"- {c}" for c in extra_commands)
    if marker not in description:
        # Shouldn't happen (Verification is never empty per contract), but
        # degrade gracefully by appending a new section.
        return f"{description}\n\n{marker}\n{extra_lines}"
    return f"{description}\n{extra_lines}"


def apply_enrichment(
    plan: IngestionPlan,
    commands_by_task: dict[str, list[str]],
) -> IngestionPlan:
    """Return a new :class:`IngestionPlan` with new tasks' verification augmented.

    Only ``description`` changes on affected task beads; task set, edges,
    and every other field are byte-identical to the unenriched plan.
    """
    new_tasks = []
    for pb in plan.new_tasks:
        extra = commands_by_task.get(pb.task_id, [])
        if not extra:
            new_tasks.append(pb)
            continue
        augmented_description = _augment_verification(pb.definition.description, extra)
        new_definition = pb.definition.model_copy(update={"description": augmented_description})
        new_tasks.append(pb.model_copy(update={"definition": new_definition}))
    return plan.model_copy(update={"new_tasks": tuple(new_tasks)})


__all__ = ["apply_enrichment", "build_enrichment_prompt", "parse_enrichment_response"]
