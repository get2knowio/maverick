"""Pure grammar functions for Spec Kit artifacts (tasks.md, spec.md).

Modeled on ``maverick.flight.parser``: no I/O, deterministic, table-driven.
See ``specs/048-speckit-refuel-ingestion/contracts/tasks-md-grammar.md``
for the grammar this module implements.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from maverick.speckit.errors import SpeckitParseError, SpeckitValidationError
from maverick.speckit.models import ParsedSpec, SpeckitPhase, SpeckitTask


@dataclass
class _OpenPhase:
    """Mutable accumulator for the phase currently being parsed."""

    number: int
    title: str


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

_PHASE_HEADING_RE = re.compile(r"^## Phase (\d+)(?::\s*(.*))?$")
_DEPENDENCIES_HEADING_RE = re.compile(r"^## Dependencies(?:\s*&\s*Execution Order)?\s*$")
_OTHER_H2_RE = re.compile(r"^## ")
_CHECKBOX_SHAPE_RE = re.compile(r"^-\s+\[[ xX]\]")
_TASK_LINE_RE = re.compile(r"^-\s+\[([ xX])\]\s+(T\d{3,})( \[P\])?(?: \[US(\d+)\])?\s+(.+)$")
_STORY_DEP_RE = re.compile(
    r"^-\s+(US\d+):\s*Depends on\s+(US\d+(?:\s*,\s*US\d+)*)\.?\s*$",
    re.IGNORECASE,
)
_DEPENDS_ON_RE = re.compile(r"\(?depends on:?\s*((?:T\d{3,}\s*,?\s*)+)\)?", re.IGNORECASE)
_TASK_ID_TOKEN_RE = re.compile(r"T\d{3,}")
_FENCE_RE = re.compile(r"^\s*```")
_HTML_COMMENT_END_RE = re.compile(r"-->")

_TITLE_RE = re.compile(r"^# Feature Specification:\s*(.+)$", re.MULTILINE)
_H1_FALLBACK_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_SC_BULLET_RE = re.compile(r"^-\s+(\*\*SC-\d+\*\*:.*)$")
_STORY_HEADING_RE = re.compile(r"^User Story\s+(\d+)\b")
_NUMBERED_ITEM_RE = re.compile(r"^\d+\.\s+(.+)$")


# ---------------------------------------------------------------------------
# tasks.md grammar
# ---------------------------------------------------------------------------


def _extract_file_paths(text: str) -> tuple[str, ...]:
    """Best-effort extraction of file-path tokens from a description.

    Whitespace-delimited tokens containing ``/`` and either a file
    extension or a trailing ``/``.
    """
    paths: list[str] = []
    for raw_tok in text.split():
        tok = raw_tok.strip(".,;:()[]{}'\"")
        if "/" not in tok:
            continue
        if tok.endswith("/") or re.search(r"\.[A-Za-z0-9_]+$", tok):
            paths.append(tok)
    return tuple(paths)


def _extract_explicit_deps(text: str) -> tuple[str, ...]:
    """Extract explicit `depends on T012[, T013]` references from a description."""
    m = _DEPENDS_ON_RE.search(text)
    if not m:
        return ()
    return tuple(_TASK_ID_TOKEN_RE.findall(m.group(1)))


def parse_tasks_md(
    content: str,
    *,
    file: str = "tasks.md",
) -> tuple[tuple[SpeckitPhase, ...], tuple[tuple[str, str], ...]]:
    """Parse tasks.md into ordered phases plus story-level dependency pairs.

    Pure function — no I/O. Deterministic: identical input always
    produces identical output (contract guarantee #1).

    Args:
        content: Raw tasks.md text.
        file: File path used in error messages (for multi-file callers).

    Returns:
        Two-tuple of (phases in file order, story_deps as
        (dependent_story, blocker_story) pairs).

    Raises:
        SpeckitParseError: Malformed task-shaped line, or non-increasing
            phase numbers (E05).
        SpeckitValidationError: Duplicate task ID, or unknown explicit
            dependency reference (E06).
    """
    phases: list[SpeckitPhase] = []
    current_phase: _OpenPhase | None = None
    current_tasks: list[SpeckitTask] = []
    seen_task_ids: dict[str, int] = {}
    all_tasks: list[SpeckitTask] = []
    story_deps: list[tuple[str, str]] = []
    last_phase_number: int | None = None

    in_fence = False
    in_comment = False
    in_dependencies_section = False

    def _finalize_phase() -> None:
        nonlocal current_phase, current_tasks
        if current_phase is not None:
            phases.append(
                SpeckitPhase(
                    number=current_phase.number,
                    title=current_phase.title,
                    tasks=tuple(current_tasks),
                )
            )
        current_phase = None
        current_tasks = []

    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.rstrip()

        if in_fence:
            if _FENCE_RE.match(line):
                in_fence = False
            continue
        if _FENCE_RE.match(line):
            in_fence = True
            continue

        # Only a line that *starts* with ``<!--`` opens a comment block —
        # matching ``<!--`` anywhere (e.g. a trailing inline comment on a
        # task line) would silently drop that task, and an unclosed inline
        # ``<!--`` would swallow every following line until ``-->``.
        comment_line = line.lstrip()
        if in_comment:
            if _HTML_COMMENT_END_RE.search(line):
                in_comment = False
            continue
        if comment_line.startswith("<!--") and not _HTML_COMMENT_END_RE.search(line):
            in_comment = True
            continue
        if comment_line.startswith("<!--") and _HTML_COMMENT_END_RE.search(line):
            continue

        phase_m = _PHASE_HEADING_RE.match(line)
        if phase_m:
            _finalize_phase()
            in_dependencies_section = False
            number = int(phase_m.group(1))
            if last_phase_number is not None and number <= last_phase_number:
                raise SpeckitParseError(
                    f"{file}:{line_number}: phase numbers must be strictly "
                    f"increasing (got {number} after {last_phase_number})",
                    file=file,
                    line=line_number,
                    expected="## Phase <n>: <title> with n > previous phase number",
                    suggestion=f"renumber this phase to {last_phase_number + 1} or higher",
                )
            last_phase_number = number
            current_phase = _OpenPhase(number=number, title=(phase_m.group(2) or "").strip())
            current_tasks = []
            continue

        if _DEPENDENCIES_HEADING_RE.match(line):
            _finalize_phase()
            in_dependencies_section = True
            continue

        if _OTHER_H2_RE.match(line):
            _finalize_phase()
            in_dependencies_section = False
            continue

        if in_dependencies_section:
            dep_m = _STORY_DEP_RE.match(line.strip())
            if dep_m:
                dependent_story = dep_m.group(1).upper()
                blockers = [b.strip().upper() for b in dep_m.group(2).split(",")]
                for blocker in blockers:
                    story_deps.append((dependent_story, blocker))
            continue

        if current_phase is None:
            continue

        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("**Checkpoint"):
            continue
        if stripped.startswith("### "):
            continue

        if _CHECKBOX_SHAPE_RE.match(line):
            task_m = _TASK_LINE_RE.match(line)
            if not task_m:
                raise SpeckitParseError(
                    f"{file}:{line_number}: malformed task line: {line!r}",
                    file=file,
                    line=line_number,
                    expected=(
                        "- [ ] T### [P] [USn] description "
                        "(checkbox, task ID, optional [P], optional [USn], description)"
                    ),
                    suggestion="add a T### task ID immediately after the checkbox",
                )
            checkbox, task_id, p_marker, story_num, description = task_m.groups()
            if task_id in seen_task_ids:
                raise SpeckitValidationError(
                    f"{file}: duplicate task ID {task_id} at lines "
                    f"{seen_task_ids[task_id]} and {line_number}",
                    file=file,
                    task_id=task_id,
                    lines=(seen_task_ids[task_id], line_number),
                )
            seen_task_ids[task_id] = line_number

            task = SpeckitTask(
                task_id=task_id,
                description=description.strip(),
                completed=checkbox.lower() == "x",
                parallel=p_marker is not None,
                story_id=f"US{story_num}" if story_num else None,
                phase_number=current_phase.number,
                file_paths=_extract_file_paths(description),
                explicit_deps=_extract_explicit_deps(description),
                line_number=line_number,
            )
            current_tasks.append(task)
            all_tasks.append(task)
            continue

        # Prose / other ignored content inside a phase section.
        continue

    _finalize_phase()

    # Validate explicit dependency references against the full task-ID set.
    for task in all_tasks:
        for dep_id in task.explicit_deps:
            if dep_id not in seen_task_ids:
                raise SpeckitValidationError(
                    f"{file}:{task.line_number}: task {task.task_id} references "
                    f"unknown dependency {dep_id}",
                    file=file,
                    task_id=task.task_id,
                    lines=(task.line_number,),
                    unknown_ref=dep_id,
                )

    return tuple(phases), tuple(story_deps)


# ---------------------------------------------------------------------------
# spec.md extraction
# ---------------------------------------------------------------------------


def _split_h2_sections(body: str) -> dict[str, str]:
    """Split a Markdown body on ``## `` headings (heading text -> content)."""
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = line[3:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_key is not None:
        sections[current_key] = "\n".join(current_lines).strip()
    return sections


def _split_h3_sections(body: str) -> dict[str, str]:
    """Split a Markdown body on ``### `` sub-headings (heading text -> content)."""
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("### "):
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = line[4:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_key is not None:
        sections[current_key] = "\n".join(current_lines).strip()
    return sections


def _find_h2_prefixed(h2: dict[str, str], prefix: str) -> str:
    """Find an h2 section whose heading text starts with *prefix*.

    Headings sometimes carry a trailing annotation (e.g.
    ``## Success Criteria *(mandatory)*``), so exact-key lookup would
    miss them.
    """
    for key, value in h2.items():
        if key.strip().startswith(prefix):
            return value
    return ""


def _extract_success_criteria(content: str) -> tuple[str, ...]:
    h2 = _split_h2_sections(content)
    sc_section = _find_h2_prefixed(h2, "Success Criteria")
    bullets: list[str] = []
    for line in sc_section.splitlines():
        m = _SC_BULLET_RE.match(line.strip())
        if m:
            bullets.append(m.group(1).strip())
    return tuple(bullets)


def _extract_story_scenarios(content: str) -> dict[str, tuple[str, ...]]:
    h3 = _split_h3_sections(content)
    result: dict[str, tuple[str, ...]] = {}
    for heading, body in h3.items():
        m = _STORY_HEADING_RE.match(heading.strip())
        if not m:
            continue
        story_id = f"US{m.group(1)}"
        idx = body.find("**Acceptance Scenarios**")
        scenario_text = body[idx:] if idx != -1 else ""
        items: list[str] = []
        for line in scenario_text.splitlines():
            im = _NUMBERED_ITEM_RE.match(line.strip())
            if im:
                items.append(im.group(1).strip())
        result[story_id] = tuple(items)
    return result


def parse_spec_md(content: str, *, file: str = "spec.md") -> ParsedSpec:
    """Extract title, success criteria, and per-story scenarios from spec.md.

    Pure function — no I/O. Best-effort except where noted (contract:
    ``tasks-md-grammar.md`` spec.md extraction table).

    Args:
        content: Raw spec.md text.
        file: File path used in error messages.

    Returns:
        A :class:`ParsedSpec`.

    Raises:
        SpeckitParseError: spec.md yields no title, no success criteria,
            and no story scenarios (E05 — likely not a Spec Kit spec).
    """
    title_m = _TITLE_RE.search(content)
    if title_m:
        title = title_m.group(1).strip()
    else:
        h1_m = _H1_FALLBACK_RE.search(content)
        title = h1_m.group(1).strip() if h1_m else ""

    success_criteria = _extract_success_criteria(content)
    story_scenarios = _extract_story_scenarios(content)

    if not title and not success_criteria and not story_scenarios:
        raise SpeckitParseError(
            f"{file}: no title, success criteria, or story scenarios found "
            "(this does not look like a Spec Kit spec.md)",
            file=file,
            line=1,
            expected="# Feature Specification: <title> plus ## Success Criteria",
            suggestion="verify this file was generated by Spec Kit's specify template",
        )

    return ParsedSpec(
        title=title,
        success_criteria=success_criteria,
        story_scenarios=story_scenarios,
    )


__all__ = [
    "parse_spec_md",
    "parse_tasks_md",
]
