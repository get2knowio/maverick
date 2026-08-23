"""Grammar parser for delta documents.

See ``specs/059-spec-delta-layer/contracts/delta-document-format.md`` for
the normative grammar. Parses with zero model calls (FR-003) and fails
loudly on any structural ambiguity rather than guessing — see
:class:`~maverick.speckit.delta.errors.DeltaFormatError`.

Cross-referencing checks against the target spec/tasks (dangling
references, duplicate ids, conflicting operations, content loss, staleness)
are deliberately **not** done here — they need a parsed
:class:`~maverick.speckit.models.SpeckitFeature` to check against and
belong to ``validate.py``, which collects every such problem instead of
failing on the first.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from maverick.speckit.delta.errors import DeltaFormatError
from maverick.speckit.delta.models import (
    DeltaDocument,
    DeltaOperation,
    RequirementEntry,
    TaskEntry,
)
from maverick.speckit.parser import (
    _TASK_LINE_RE,  # noqa: SLF001 -- reuse, not reimplement (Guardrail 5)
)


def _build_requirement_entry(
    *,
    operation: DeltaOperation,
    req_id: str,
    line_number: int,
    new_req_id: str | None = None,
    before: str | None = None,
    after: str | None = None,
    shrink_intended: bool = False,
) -> RequirementEntry:
    """``RequirementEntry(...)``, with the model's own operation/field
    validators translated into :class:`DeltaFormatError` instead of a raw
    ``pydantic.ValidationError`` (e.g. ``[shrink-intended]`` written on an
    ADDED/REMOVED heading, or a stray ``### After`` under a REMOVED
    section) — the grammar regexes here are deliberately permissive about
    *which* subsections/markers can follow a heading; the model is what
    actually enforces per-operation shape, so its rejection must still
    surface as a structured, line-numbered grammar error rather than an
    uncaught exception the CLI has no handler for.
    """
    try:
        return RequirementEntry(
            operation=operation,
            req_id=req_id,
            new_req_id=new_req_id,
            before=before,
            after=after,
            shrink_intended=shrink_intended,
            line_number=line_number,
        )
    except ValidationError as exc:
        raise DeltaFormatError(
            f"line {line_number}: {exc.errors()[0]['msg']}",
            code="malformed-document",
            line=line_number,
        ) from exc


def _build_task_entry(
    *,
    kind: Literal["added", "withdrawn"],
    task_id: str,
    line_number: int,
    line: str | None = None,
) -> TaskEntry:
    """``TaskEntry(...)``, with the same ValidationError -> DeltaFormatError
    translation as :func:`_build_requirement_entry` — e.g. a ``WITHDRAWN:``
    line naming something that isn't a valid ``T\\d{3,}`` task id."""
    try:
        return TaskEntry(kind=kind, task_id=task_id, line=line, line_number=line_number)
    except ValidationError as exc:
        raise DeltaFormatError(
            f"line {line_number}: {exc.errors()[0]['msg']}",
            code="malformed-document",
            line=line_number,
        ) from exc


_TITLE_RE = re.compile(r"^#\s*Delta:\s*(.+)$")
_TARGET_RE = re.compile(r"^\*\*Target\*\*:\s*(.+)$")
_OP_SECTION_RE = re.compile(
    r"^##\s+(ADDED|MODIFIED|REMOVED)\s+(FR-\d{3}[a-z]?)(?:\s+\[shrink-intended\])?\s*$"
)
_RENAMED_HEADING_RE = re.compile(r"^##\s+RENAMED\s*$")
_TASKS_HEADING_RE = re.compile(r"^##\s+TASKS\s*$")
_APPLIED_HEADING_RE = re.compile(r"^##\s+Applied\s*$")
_ANY_H2_RE = re.compile(r"^##\s+")
_ANY_H3_RE = re.compile(r"^###\s+")
#: A markdown horizontal rule — the separator ``archive.py``'s
#: ``render_application_record`` inserts before the appended ``## Applied``
#: record. Never valid content inside any of this grammar's sections, so
#: every section-body scan below stops at it just as it would at a
#: heading — otherwise re-parsing an already-archived document (to check
#: ``is_applied``) fails on the appended record's own separator line.
_HR_RE = re.compile(r"^-{3,}\s*$")


def _is_section_boundary(line: str) -> bool:
    return bool(_ANY_H2_RE.match(line) or _HR_RE.match(line))


_BEFORE_HEADING_RE = re.compile(r"^###\s+Before\s*$")
_AFTER_HEADING_RE = re.compile(r"^###\s+After\s*$")
_RENAME_FROM_RE = re.compile(r"^-\s*FROM:\s*(FR-\d{3}[a-z]?)\s*$")
_RENAME_TO_RE = re.compile(r"^-\s*TO:\s*(FR-\d{3}[a-z]?)\s*$")
_TASK_ADDED_RE = re.compile(r"^-\s*ADDED:\s*(.+)$")
_TASK_WITHDRAWN_RE = re.compile(r"^-\s*WITHDRAWN:\s*(\S+)\s*$")
_SEQUENCE_PREFIX_RE = re.compile(r"^(\d+)-")


def _numeric_prefix(stem: str) -> int:
    m = _SEQUENCE_PREFIX_RE.match(stem)
    return int(m.group(1)) if m else 0


def _consume_subsection(
    lines: list[str], i: int, heading_re: re.Pattern[str]
) -> tuple[str | None, int]:
    """Consume an optional ``### Before``/``### After`` subsection at *i*.

    Returns:
        ``(verbatim_body_text, next_i)`` — text is ``None`` when *lines[i]*
        does not match *heading_re* at all (the subsection is absent).
    """
    n = len(lines)
    while i < n and not lines[i].strip():
        i += 1
    if i >= n or not heading_re.match(lines[i]):
        return None, i
    heading_line_no = i + 1
    i += 1
    body: list[str] = []
    while i < n and not _is_section_boundary(lines[i]) and not _ANY_H3_RE.match(lines[i]):
        body.append(lines[i])
        i += 1
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()
    if not body:
        raise DeltaFormatError(
            f"line {heading_line_no}: this section has no content",
            code="malformed-document",
            line=heading_line_no,
        )
    return "\n".join(body) + "\n", i


def _consume_renamed(
    lines: list[str], i: int, section_line_no: int
) -> tuple[list[tuple[str, str, int]], int]:
    n = len(lines)
    pending_from: tuple[str, int] | None = None
    pairs: list[tuple[str, str, int]] = []
    while i < n and not _is_section_boundary(lines[i]):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        from_m = _RENAME_FROM_RE.match(stripped)
        if from_m:
            if pending_from is not None:
                raise DeltaFormatError(
                    f"line {i + 1}: 'FROM: {from_m.group(1)}' with no matching 'TO:' "
                    f"for the previous 'FROM: {pending_from[0]}'",
                    code="unbalanced-rename",
                    line=i + 1,
                )
            pending_from = (from_m.group(1), i + 1)
            i += 1
            continue
        to_m = _RENAME_TO_RE.match(stripped)
        if to_m:
            if pending_from is None:
                raise DeltaFormatError(
                    f"line {i + 1}: 'TO: {to_m.group(1)}' with no preceding 'FROM:'",
                    code="unbalanced-rename",
                    line=i + 1,
                )
            from_id, from_line = pending_from
            pairs.append((from_id, to_m.group(1), from_line))
            pending_from = None
            i += 1
            continue
        raise DeltaFormatError(
            f"line {i + 1}: malformed '## RENAMED' entry: {stripped!r}",
            code="unbalanced-rename",
            line=i + 1,
        )
    if pending_from is not None:
        raise DeltaFormatError(
            f"'## RENAMED' section: 'FROM: {pending_from[0]}' with no matching 'TO:'",
            code="unbalanced-rename",
            line=pending_from[1],
        )
    if not pairs:
        raise DeltaFormatError(
            f"line {section_line_no}: '## RENAMED' section has no FROM/TO pairs",
            code="malformed-document",
            line=section_line_no,
        )
    return pairs, i


def _consume_tasks(lines: list[str], i: int) -> tuple[list[TaskEntry], int]:
    n = len(lines)
    entries: list[TaskEntry] = []
    while i < n and not _is_section_boundary(lines[i]):
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        added_m = _TASK_ADDED_RE.match(stripped)
        if added_m:
            full_line = added_m.group(1).strip()
            synthetic = f"- [ ] {full_line}"
            task_m = _TASK_LINE_RE.match(synthetic)
            if not task_m:
                raise DeltaFormatError(
                    f"line {i + 1}: ADDED task line does not parse under the task "
                    f"grammar: {full_line!r}",
                    code="malformed-task-line",
                    line=i + 1,
                )
            task_id = task_m.group(2)
            entries.append(
                _build_task_entry(kind="added", task_id=task_id, line=full_line, line_number=i + 1)
            )
            i += 1
            continue
        withdrawn_m = _TASK_WITHDRAWN_RE.match(stripped)
        if withdrawn_m:
            entries.append(
                _build_task_entry(
                    kind="withdrawn", task_id=withdrawn_m.group(1), line_number=i + 1
                )
            )
            i += 1
            continue
        raise DeltaFormatError(
            f"line {i + 1}: malformed '## TASKS' entry: {stripped!r}",
            code="malformed-document",
            line=i + 1,
        )
    return entries, i


def parse_delta_md(text: str, *, path: Path) -> DeltaDocument:
    """Parse a delta document into a :class:`DeltaDocument`.

    Pure function — no I/O beyond what *path* is used for (naming and
    archive-ordering; the file itself is not read here).

    Args:
        text: Raw delta document content.
        path: Where the document lives — decides pending vs. applied
            (:attr:`DeltaDocument.is_applied`) and the archive sequence.

    Returns:
        A :class:`DeltaDocument`.

    Raises:
        DeltaFormatError: Any structural grammar violation.
    """
    lines = text.splitlines()
    n = len(lines)

    i = 0
    title: str | None = None
    while i < n:
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        m = _TITLE_RE.match(lines[i])
        if not m:
            raise DeltaFormatError(
                f"line {i + 1}: expected '# Delta: <title>' as the first non-blank line",
                code="malformed-document",
                line=i + 1,
            )
        title = m.group(1).strip()
        i += 1
        break
    if title is None:
        raise DeltaFormatError(
            "empty document: no '# Delta:' heading found", code="malformed-document", line=1
        )

    target: str | None = None
    while i < n and not _is_section_boundary(lines[i]):
        m = _TARGET_RE.match(lines[i].strip())
        if m:
            if target is not None:
                raise DeltaFormatError(
                    f"line {i + 1}: duplicate '**Target**:' declaration",
                    code="malformed-document",
                    line=i + 1,
                )
            target = m.group(1).strip()
        i += 1
    if target is None:
        raise DeltaFormatError(
            "no '**Target**:' declaration found", code="malformed-document", line=1
        )

    requirement_entries: list[RequirementEntry] = []
    task_entries: list[TaskEntry] = []

    while i < n:
        line = lines[i]
        if not _ANY_H2_RE.match(line):
            i += 1
            continue

        op_m = _OP_SECTION_RE.match(line)
        if op_m:
            operation = DeltaOperation(op_m.group(1))
            req_id = op_m.group(2)
            shrink_intended = "[shrink-intended]" in line
            section_line_no = i + 1
            i += 1
            before_text, i = _consume_subsection(lines, i, _BEFORE_HEADING_RE)
            after_text, i = _consume_subsection(lines, i, _AFTER_HEADING_RE)
            requirement_entries.append(
                _build_requirement_entry(
                    operation=operation,
                    req_id=req_id,
                    before=before_text,
                    after=after_text,
                    shrink_intended=shrink_intended,
                    line_number=section_line_no,
                )
            )
            continue

        if _RENAMED_HEADING_RE.match(line):
            section_line_no = i + 1
            i += 1
            pairs, i = _consume_renamed(lines, i, section_line_no)
            for from_id, to_id, pair_line in pairs:
                requirement_entries.append(
                    _build_requirement_entry(
                        operation=DeltaOperation.RENAMED,
                        req_id=from_id,
                        new_req_id=to_id,
                        line_number=pair_line,
                    )
                )
            continue

        if _TASKS_HEADING_RE.match(line):
            i += 1
            entries, i = _consume_tasks(lines, i)
            task_entries.extend(entries)
            continue

        if _APPLIED_HEADING_RE.match(line):
            # The application record appended as this document moved to
            # deltas/archive/ (archive.py's render_application_record) —
            # not part of the delta grammar itself. Everything from here
            # to EOF is provenance, not further entries; stop scanning so
            # an already-applied document remains parseable at all (its
            # `is_applied` property is what CLI code actually branches
            # on — this just keeps `parse_delta_md` from rejecting the
            # file it will be handed for the "already applied" check).
            break

        raise DeltaFormatError(
            f"line {i + 1}: unknown section heading: {line.strip()!r}",
            code="malformed-document",
            line=i + 1,
        )

    return DeltaDocument(
        path=path,
        title=title,
        target_feature=target,
        requirement_entries=tuple(requirement_entries),
        task_entries=tuple(task_entries),
        sequence=_numeric_prefix(path.stem),
    )


__all__ = ["parse_delta_md"]
