"""Utilities for parsing Speckit tasks.md files deterministically."""

from __future__ import annotations

import hashlib
import re

from src.models.phase_automation import (
    PhaseDefinition,
    PhaseExecutionHints,
    TaskItem,
)


_PHASE_HEADING_PATTERN = re.compile(r"^##\s+Phase\s+(?P<ordinal>\d+):\s*(?P<title>[^\[]+?)(?:\s*\[(?P<meta>.+)\])?\s*$")
_TASK_LINE_PATTERN = re.compile(r"^-\s*\[(?P<state>[ xX])\]\s*(?P<body>.+)$")


def parse_tasks_markdown(markdown: str) -> list[PhaseDefinition]:
    """Parse markdown content into ordered phase definitions."""

    lines = markdown.splitlines()
    phases: list[PhaseDefinition] = []
    current_ordinal: int | None = None
    current_title: str | None = None
    current_metadata: str | None = None
    collected_lines: list[str] = []
    tasks: list[TaskItem] = []

    def finalize_current() -> None:
        nonlocal current_ordinal, current_title, current_metadata, collected_lines, tasks
        if current_ordinal is None or current_title is None:
            return
        hints = parse_phase_metadata(current_metadata)
        raw_markdown = "\n".join(collected_lines).strip()
        phase = PhaseDefinition(
            phase_id=f"phase-{current_ordinal}",
            ordinal=current_ordinal,
            title=current_title,
            tasks=list(tasks),
            execution_hints=hints,
            raw_markdown=raw_markdown,
        )
        phases.append(phase)
        current_ordinal = None
        current_title = None
        current_metadata = None
        collected_lines = []
        tasks = []

    for line in lines:
        heading_match = _PHASE_HEADING_PATTERN.match(line)
        if heading_match:
            finalize_current()
            ordinal = int(heading_match.group("ordinal"))
            title = heading_match.group("title").strip()
            metadata = heading_match.group("meta")
            current_ordinal = ordinal
            current_title = title
            current_metadata = metadata
            collected_lines = [line]
            tasks = []
            continue

        if current_ordinal is None:
            continue

        collected_lines.append(line)
        task_match = _TASK_LINE_PATTERN.match(line.strip())
        if not task_match:
            continue
        task = _parse_task_line(task_match.group("state"), task_match.group("body"))
        tasks.append(task)

    finalize_current()

    if not phases:
        raise ValueError("No phase headings found in tasks.md content")

    return phases


def _parse_task_line(state_token: str, body: str) -> TaskItem:
    is_complete = state_token.lower() == "x"
    tokens = body.strip().split()
    if not tokens:
        raise ValueError("Task bullet must include content")
    task_id = tokens[0]
    remaining_tokens = tokens[1:]
    tags: list[str] = []
    description_tokens: list[str] = []
    for token in remaining_tokens:
        if token.startswith("#") and len(token) > 1:
            tags.append(token[1:])
        else:
            description_tokens.append(token)
    description = " ".join(description_tokens).strip()
    if not description:
        raise ValueError("Task bullet must include description text")
    return TaskItem(
        task_id=task_id,
        description=description,
        is_complete=is_complete,
        tags=tags,
    )


def parse_phase_metadata(metadata: str | None) -> PhaseExecutionHints | None:
    """Parse the optional metadata section attached to a phase heading."""

    if metadata is None:
        return None
    metadata = metadata.strip()
    if not metadata:
        return None

    model: str | None = None
    agent: str | None = None
    extra_env: dict[str, str] = {}

    for token in metadata.split():
        if "=" not in token:
            raise ValueError(f"Unsupported metadata token '{token}'")
        key, value = token.split("=", 1)
        if key == "model":
            model = value
        elif key == "agent":
            agent = value
        elif key.startswith("env."):
            env_key = key[4:]
            if not env_key:
                raise ValueError("Environment override token must include a key")
            if not env_key.isupper():
                raise ValueError("Environment override keys must be uppercase")
            extra_env[env_key] = value
        else:
            raise ValueError(f"Unsupported metadata key '{key}'")

    return PhaseExecutionHints(model=model, agent_profile=agent, extra_env=extra_env)


def compute_tasks_md_hash(content: str) -> str:
    """Compute a deterministic BLAKE2b hash of tasks.md content."""

    return hashlib.blake2b(content.encode("utf-8"), digest_size=32).hexdigest()


def is_phase_complete(phase: PhaseDefinition) -> bool:
    """Check if all tasks in a phase are marked complete."""
    if not phase.tasks:
        return False
    return all(task.is_complete for task in phase.tasks)


def find_first_incomplete_phase_index(phases: list[PhaseDefinition]) -> int:
    """Find the index of the first phase with incomplete tasks.

    Returns -1 if all phases are complete or no phases exist.
    """
    for idx, phase in enumerate(phases):
        if not is_phase_complete(phase):
            return idx
    return -1


__all__ = [
    "compute_tasks_md_hash",
    "find_first_incomplete_phase_index",
    "is_phase_complete",
    "parse_phase_metadata",
    "parse_tasks_markdown",
]
