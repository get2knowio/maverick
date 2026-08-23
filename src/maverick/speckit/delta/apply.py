"""Apply a validated delta document: rewrite ``spec.md``/``tasks.md``,
detect impacts, and archive the document.

See ``specs/059-spec-delta-layer/contracts/cli-delta.md`` for the command
contract and research R8 for the atomicity shape this module implements:
both files' new contents are computed **fully in memory** and validated
before anything is written — a failure at any point before the first
write leaves the pre-apply state exactly. Writes no beads (FR-011); bead
consequences belong to the next explicit ``refuel --speckit``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from maverick.beads.client import BeadClient
from maverick.speckit.bead_lookup import find_epic_id
from maverick.speckit.delta.archive import archive_delta, extract_applied_at
from maverick.speckit.delta.errors import StaleAcknowledgementError
from maverick.speckit.delta.impacts import detect_impacts
from maverick.speckit.delta.models import (
    OPERATION_ORDER,
    Acknowledgement,
    ApplicationRecord,
    DeltaDocument,
    DeltaOperation,
    Impact,
    RequirementEntry,
    TaskEntry,
)
from maverick.speckit.delta.validate import DeltaValidationError, validate_delta
from maverick.speckit.models import SpeckitPhase
from maverick.speckit.parser import (
    _TASK_LINE_RE,  # noqa: SLF001 -- reuse, not reimplement
    parse_tasks_md,
)
from maverick.speckit.requirements import (
    PassthroughLines,
    RequirementBlock,
    RequirementSection,
    parse_requirements,
    parse_single_block,
    render_requirements,
)
from maverick.utils.atomic import atomic_write_text


@dataclass(frozen=True, slots=True)
class RequirementSummary:
    """Requirement operations actually applied, by id."""

    added: tuple[str, ...] = ()
    modified: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    renamed: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class TaskSummary:
    """Task entries actually applied, by id."""

    added: tuple[str, ...] = ()
    withdrawn: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ApplyOutcome:
    """Every terminal shape ``delta apply`` (or ``--dry-run``) can reach.

    Attributes:
        status: ``"already_applied"`` (FR-010, exit 0, nothing touched),
            ``"blocked"`` (unacknowledged impacts, exit 1, nothing
            written), ``"dry_run"`` (reports everything, writes nothing),
            or ``"applied"`` (everything written, archived).
        applied_at: Set for ``"already_applied"`` (read from the archived
            record) and ``"applied"`` (this run's timestamp).
        requirements: Populated for ``"dry_run"``/``"applied"``.
        tasks: Populated for ``"dry_run"``/``"applied"``.
        acknowledgements: Populated for ``"applied"`` only — the impact's
            state *at the time it was cleared* (FR-015a).
        declared_reductions: MODIFIED entries carrying ``[shrink-intended]``.
        archived_to: Set for ``"applied"`` only.
        impacts: Populated for ``"blocked"``/``"dry_run"``.
        would_block: ``"dry_run"`` only — whether impacts exist (FR-012:
            a dry run reports, it never refuses).
    """

    status: Literal["already_applied", "blocked", "dry_run", "applied"]
    applied_at: str | None = None
    requirements: RequirementSummary = field(default_factory=RequirementSummary)
    tasks: TaskSummary = field(default_factory=TaskSummary)
    acknowledgements: tuple[Acknowledgement, ...] = ()
    declared_reductions: tuple[str, ...] = ()
    archived_to: Path | None = None
    impacts: tuple[Impact, ...] = ()
    would_block: bool = False


def _find_block_index(elements: list[object], req_id: str) -> int | None:
    for idx, el in enumerate(elements):
        if isinstance(el, RequirementBlock) and el.req_id == req_id:
            return idx
    return None


def _ends_blank(elements: list[object]) -> bool:
    if not elements:
        return True
    last = elements[-1]
    if isinstance(last, RequirementBlock):
        last_line = last.all_lines[-1] if last.all_lines else ""
    else:
        assert isinstance(last, PassthroughLines)
        last_line = last.lines[-1] if last.lines else ""
    return not last_line.strip()


def apply_requirement_operations(
    section: RequirementSection, entries: tuple[RequirementEntry, ...]
) -> tuple[RequirementSection, RequirementSummary]:
    """Apply every requirement entry to *section*, in ``OPERATION_ORDER``.

    Requirements the delta does not name are untouched — same tuple
    positions, same objects — which is what keeps them byte-identical
    after rendering (T015/FR-004a).

    Args:
        section: The target spec's parsed requirements section.
        entries: The delta document's requirement entries, any order.

    Returns:
        ``(new_section, summary)``.
    """
    elements: list[object] = list(section.elements)
    by_operation: dict[DeltaOperation, list[RequirementEntry]] = {}
    for entry in entries:
        by_operation.setdefault(entry.operation, []).append(entry)

    added: list[str] = []
    modified: list[str] = []
    removed: list[str] = []
    renamed: list[tuple[str, str]] = []

    for operation in OPERATION_ORDER:
        for entry in by_operation.get(operation, ()):
            if operation is DeltaOperation.RENAMED:
                idx = _find_block_index(elements, entry.req_id)
                if idx is None or entry.new_req_id is None:
                    continue
                block = elements[idx]
                assert isinstance(block, RequirementBlock)
                new_header = block.header_line.replace(
                    f"**{entry.req_id}**", f"**{entry.new_req_id}**", 1
                )
                elements[idx] = block.model_copy(
                    update={"req_id": entry.new_req_id, "header_line": new_header}
                )
                renamed.append((entry.req_id, entry.new_req_id))

            elif operation is DeltaOperation.REMOVED:
                idx = _find_block_index(elements, entry.req_id)
                if idx is not None:
                    del elements[idx]
                removed.append(entry.req_id)

            elif operation is DeltaOperation.MODIFIED:
                if entry.after is None:
                    continue
                new_block = parse_single_block(entry.after, line_number=entry.line_number)
                idx = _find_block_index(elements, entry.req_id)
                if idx is not None:
                    old_block = elements[idx]
                    assert isinstance(old_block, RequirementBlock)
                    old_trailing = old_block.trailing_blanks
                    new_trailing = new_block.trailing_blanks
                    if old_trailing > new_trailing:
                        new_block = new_block.model_copy(
                            update={
                                "body_lines": (
                                    *new_block.body_lines,
                                    *(("\n",) * (old_trailing - new_trailing)),
                                )
                            }
                        )
                    elements[idx] = new_block
                else:
                    elements.append(new_block)
                modified.append(entry.req_id)

            elif operation is DeltaOperation.ADDED:
                if entry.after is None:
                    continue
                new_block = parse_single_block(entry.after, line_number=entry.line_number)
                if not _ends_blank(elements):
                    elements.append(PassthroughLines(lines=("\n",), start_line=1))
                elements.append(new_block)
                added.append(entry.req_id)

    if elements and not _ends_blank(elements):
        elements.append(PassthroughLines(lines=("\n",), start_line=1))

    new_section = section.model_copy(update={"elements": tuple(elements)})
    summary = RequirementSummary(
        added=tuple(added),
        modified=tuple(modified),
        removed=tuple(removed),
        renamed=tuple(renamed),
    )
    return new_section, summary


def _task_summary(task_entries: tuple[TaskEntry, ...]) -> TaskSummary:
    added = tuple(e.task_id for e in task_entries if e.kind == "added")
    withdrawn = tuple(e.task_id for e in task_entries if e.kind == "withdrawn")
    return TaskSummary(added=added, withdrawn=withdrawn)


def _rewrite_tasks_lines(
    raw_lines: list[str],
    phases: tuple[SpeckitPhase, ...],
    added_entries: list[TaskEntry],
    withdrawn_ids: list[str],
) -> list[str]:
    """Insert ADDED lines and remove WITHDRAWN ids, leaving every other
    line byte-identical (T020).

    ADDED lines land immediately after the last existing task sharing
    the same ``[USn]`` marker (Spec Kit's template convention is one
    phase per user story), or at the end of the last phase carrying any
    tasks when there is no story match or marker.
    """
    all_tasks = [task for phase in phases for task in phase.tasks]
    task_by_id = {task.task_id: task for task in all_tasks}

    withdrawn_line_numbers = {
        task_by_id[task_id].line_number for task_id in withdrawn_ids if task_id in task_by_id
    }

    story_last_line: dict[str, int] = {}
    for task in all_tasks:
        if task.story_id:
            story_last_line[task.story_id] = max(
                story_last_line.get(task.story_id, 0), task.line_number
            )

    default_anchor: int | None = None
    for phase in reversed(phases):
        if phase.tasks:
            default_anchor = phase.tasks[-1].line_number
            break

    insert_after: dict[int, list[str]] = {}
    tail_insertions: list[str] = []
    for entry in added_entries:
        assert entry.line is not None
        synthetic = f"- [ ] {entry.line}"
        task_m = _TASK_LINE_RE.match(synthetic)
        story_id = f"US{task_m.group(4)}" if task_m and task_m.group(4) else None
        anchor = story_last_line.get(story_id) if story_id else None
        if anchor is None:
            anchor = default_anchor
        new_line = f"{synthetic}\n"
        if anchor is not None:
            insert_after.setdefault(anchor, []).append(new_line)
        else:
            tail_insertions.append(new_line)

    result: list[str] = []
    for idx, line in enumerate(raw_lines):
        line_no = idx + 1
        # A withdrawn line still anchors any insertion keyed to it — only
        # the withdrawn line's own text is dropped. Checking this before
        # the withdrawal `continue` is what it is; skipping it silently
        # dropped an ADDED task whose only anchor was a line also being
        # withdrawn in the same delta.
        if line_no not in withdrawn_line_numbers:
            result.append(line)
        if line_no in insert_after:
            result.extend(insert_after[line_no])

    if tail_insertions:
        if result and not result[-1].endswith("\n"):
            result[-1] = f"{result[-1]}\n"
        result.extend(tail_insertions)

    return result


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def apply_delta(
    document: DeltaDocument,
    *,
    document_text: str,
    feature_dir: Path,
    client: BeadClient | None,
    acknowledged_task_ids: frozenset[str] = frozenset(),
    dry_run: bool = False,
) -> ApplyOutcome:
    """Validate, detect impacts, and (unless refused/dry-run) apply *document*.

    Args:
        document: The parsed delta document (pending or already applied).
        document_text: Its raw on-disk text — read once by the caller so
            this function never re-reads the delta file itself.
        feature_dir: The target feature's ``specs/NNN-name/`` directory.
        client: A :class:`~maverick.beads.client.BeadClient`, or ``None``
            when impact detection cannot run (no bd available) — a delta
            with no task entries never needs it (FR-007b).
        acknowledged_task_ids: Task ids passed via repeatable ``--ack``.
        dry_run: Report everything, write nothing (FR-012).

    Returns:
        An :class:`ApplyOutcome`.

    Raises:
        DeltaValidationError: Any problem in ``delta-document-format.md``'s
            validation table.
    """
    if document.is_applied:
        return ApplyOutcome(status="already_applied", applied_at=extract_applied_at(document_text))

    # Narrow interruption-window recovery (research R8): the write order
    # below is spec.md -> tasks.md -> archive copy -> unlink pending. A
    # process death between the archive write and the unlink leaves BOTH
    # copies on disk with spec.md/tasks.md already rewritten — is_applied
    # above is False (the pending path is still outside deltas/archive/),
    # so re-validating this document would incorrectly refuse (typically
    # "stale-before", since spec.md no longer matches `before`). Detect
    # that the archive copy already exists and finish the cleanup instead
    # of re-processing a delta whose target files were already rewritten.
    prospective_archive_path = document.path.parent / "archive" / document.path.name
    if prospective_archive_path.is_file():
        archived_text = prospective_archive_path.read_text(encoding="utf-8")
        if not dry_run:
            document.path.unlink(missing_ok=True)
        return ApplyOutcome(status="already_applied", applied_at=extract_applied_at(archived_text))

    spec_path = feature_dir / "spec.md"
    tasks_path = feature_dir / "tasks.md"
    spec_text = spec_path.read_text(encoding="utf-8")
    tasks_text = tasks_path.read_text(encoding="utf-8")

    spec_section = parse_requirements(spec_text, file=str(spec_path))
    phases, _story_deps = parse_tasks_md(tasks_text, file=str(tasks_path))

    problems = validate_delta(document, spec_section=spec_section, tasks_phases=phases)
    if problems:
        raise DeltaValidationError(problems)

    impacts: tuple[Impact, ...] = ()
    if document.task_entries and client is not None:
        epic_id = await find_epic_id(client, feature_dir.name)
        if epic_id is not None:
            impacts = await detect_impacts(document, client=client, epic_id=epic_id)

    impact_task_ids = {impact.task_id for impact in impacts if impact.task_id}
    stale_acks = tuple(sorted(acknowledged_task_ids - impact_task_ids))
    if stale_acks:
        raise StaleAcknowledgementError(stale_acks)

    outstanding = tuple(
        impact
        for impact in impacts
        if not impact.task_id or impact.task_id not in acknowledged_task_ids
    )

    if document.requirement_entries:
        new_section, req_summary = apply_requirement_operations(
            spec_section, document.requirement_entries
        )
    else:
        new_section, req_summary = spec_section, RequirementSummary()
    task_summary = _task_summary(document.task_entries)

    if dry_run:
        return ApplyOutcome(
            status="dry_run",
            requirements=req_summary,
            tasks=task_summary,
            impacts=impacts,
            would_block=bool(outstanding),
        )

    if outstanding:
        return ApplyOutcome(status="blocked", impacts=impacts)

    new_spec_text = render_requirements(new_section) if document.requirement_entries else spec_text

    added_task_entries = [entry for entry in document.task_entries if entry.kind == "added"]
    withdrawn_ids = [entry.task_id for entry in document.task_entries if entry.kind == "withdrawn"]
    if document.task_entries:
        new_tasks_lines = _rewrite_tasks_lines(
            tasks_text.splitlines(keepends=True), phases, added_task_entries, withdrawn_ids
        )
        new_tasks_text = "".join(new_tasks_lines)
    else:
        new_tasks_text = tasks_text

    now = _utc_now_iso()
    acknowledgements = tuple(
        Acknowledgement(
            task_id=impact.task_id,
            bead_id=impact.bead_id,
            bead_status=impact.bead_status,
            acknowledged_at=now,
        )
        for impact in impacts
        if impact.task_id in acknowledged_task_ids
    )
    declared_reductions = tuple(
        entry.req_id
        for entry in document.requirement_entries
        if entry.operation is DeltaOperation.MODIFIED and entry.shrink_intended
    )
    record = ApplicationRecord(
        applied_at=now,
        counts={
            "added": len(req_summary.added),
            "modified": len(req_summary.modified),
            "removed": len(req_summary.removed),
            "renamed": len(req_summary.renamed),
        },
        task_counts={"added": len(task_summary.added), "withdrawn": len(task_summary.withdrawn)},
        acknowledgements=acknowledgements,
        shrink_intended_ids=declared_reductions,
    )
    archived_text, archived_path = archive_delta(
        document_text, record=record, source_path=document.path
    )

    # Every computation above must succeed before any write happens
    # (research R8) — the archive move is last, so an interruption
    # between writes at worst leaves the artifacts rewritten with the
    # delta still pending, which a re-run detects as already applied.
    atomic_write_text(spec_path, new_spec_text)
    atomic_write_text(tasks_path, new_tasks_text)
    atomic_write_text(archived_path, archived_text)
    document.path.unlink()

    return ApplyOutcome(
        status="applied",
        applied_at=now,
        requirements=req_summary,
        tasks=task_summary,
        acknowledgements=acknowledgements,
        declared_reductions=declared_reductions,
        archived_to=archived_path,
    )


__all__ = [
    "ApplyOutcome",
    "RequirementSummary",
    "TaskSummary",
    "apply_delta",
    "apply_requirement_operations",
]
