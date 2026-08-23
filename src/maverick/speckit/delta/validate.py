"""Semantic validation of a parsed delta document against its target spec.

See ``specs/059-spec-delta-layer/contracts/delta-document-format.md``'s
"Validation" table for the checks this module implements. Collects
**every** problem rather than failing on the first (Principle IV) —
callers see the complete list, each naming the offending entry and its
line number.

Pure function — no I/O. The caller (CLI/apply) is responsible for
parsing ``spec.md``/``tasks.md`` first and handing over the already-parsed
:class:`~maverick.speckit.requirements.RequirementSection` and
:class:`~maverick.speckit.models.SpeckitPhase` tuple.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from maverick.speckit.delta.models import (
    SHRINK_FLOOR,
    DeltaDocument,
    DeltaOperation,
    RequirementEntry,
)
from maverick.speckit.errors import SpeckitError, SpeckitParseError
from maverick.speckit.models import SpeckitPhase
from maverick.speckit.requirements import RequirementSection, parse_single_block


@dataclass(frozen=True, slots=True)
class Problem:
    """One validation failure, naming exactly where it lives."""

    line: int
    entry: str
    code: str
    message: str


class DeltaValidationError(SpeckitError):
    """Raised by ``apply.py`` when :func:`validate_delta` finds any
    problem — ``delta apply`` must validate before doing anything else,
    and this is how that failure reaches the CLI in the same shape
    ``delta validate`` reports it in.

    Attributes:
        problems: Every :class:`Problem` found, in document order.
    """

    def __init__(self, problems: tuple[Problem, ...]) -> None:
        self.problems = problems
        super().__init__(f"{len(problems)} problem(s) found in delta document")


def _entry_label(entry: RequirementEntry) -> str:
    if entry.operation is DeltaOperation.RENAMED:
        return f"RENAMED {entry.req_id} -> {entry.new_req_id}"
    return f"{entry.operation.value} {entry.req_id}"


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _content_loss_problems(entry: RequirementEntry, label: str) -> list[Problem]:
    """FR-005a: reject a dropped sub-bullet, or an after-block below
    ``SHRINK_FLOOR`` of the before-block's normalized length — unless
    ``[shrink-intended]`` declares the reduction deliberate (FR-005e)."""
    assert entry.before is not None
    assert entry.after is not None

    try:
        before_block = parse_single_block(entry.before, line_number=entry.line_number)
        after_block = parse_single_block(entry.after, line_number=entry.line_number)
    except SpeckitParseError as exc:
        return [Problem(entry.line_number, label, "malformed-document", str(exc))]

    if entry.shrink_intended:
        return []

    problems: list[Problem] = []
    dropped = len(before_block.sub_bullets) - len(after_block.sub_bullets)
    if dropped > 0:
        problems.append(
            Problem(
                entry.line_number,
                label,
                "content-loss",
                f"after-block drops {dropped} sub-bullet(s). Add [shrink-intended] "
                "if the reduction is deliberate.",
            )
        )

    before_len = before_block.normalized_length
    if before_len > 0:
        ratio = after_block.normalized_length / before_len
        if ratio < SHRINK_FLOOR:
            # floor(), not round(): the message must never claim a
            # percentage >= the floor for a ratio this branch has already
            # proven is strictly below it (e.g. ratio=0.597 would round()
            # to "60%", reading as "60% of the before-block (floor 60%)"
            # — self-contradictory to a user trying to see why a
            # borderline edit was rejected).
            shown_pct = math.floor(ratio * 100)
            problems.append(
                Problem(
                    entry.line_number,
                    label,
                    "content-loss",
                    f"after-block is {shown_pct}% of the before-block "
                    f"(floor {round(SHRINK_FLOOR * 100)}%). Add [shrink-intended] "
                    "if the reduction is deliberate.",
                )
            )
    return problems


def validate_delta(
    document: DeltaDocument,
    *,
    spec_section: RequirementSection,
    tasks_phases: tuple[SpeckitPhase, ...] = (),
) -> tuple[Problem, ...]:
    """Run every check in ``delta-document-format.md``'s Validation table.

    Args:
        document: The parsed delta document.
        spec_section: The target feature's ``### Functional Requirements``
            section, already parsed.
        tasks_phases: The target feature's parsed ``tasks.md`` phases —
            only needed when *document* carries task entries.

    Returns:
        Every problem found, in document order. Empty when the delta is
        valid.
    """
    if document.is_empty:
        return (
            Problem(
                1,
                document.title,
                "empty-delta",
                "delta has zero requirement or task entries — nothing to apply",
            ),
        )

    problems: list[Problem] = []
    existing_ids = {b.req_id for b in spec_section.blocks()}
    introduced_ids: set[str] = set()
    seen_operation_targets: set[str] = set()
    #: RENAMED's TO ids from this same document — reachable by a later
    #: MODIFIED/REMOVED entry once RENAMED runs first (OPERATION_ORDER),
    #: even though the id doesn't exist in *spec_section* yet. Without
    #: this, "rename then reword under the new id in one delta" — the
    #: exact pattern OPERATION_ORDER's own docstring and
    #: apply_requirement_operations support — is always rejected here as
    #: a false dangling-requirement before apply_delta ever gets to run
    #: the operations in order.
    renamed_new_ids = {
        e.new_req_id
        for e in document.requirement_entries
        if e.operation is DeltaOperation.RENAMED and e.new_req_id is not None
    }

    for entry in document.requirement_entries:
        label = _entry_label(entry)

        if entry.req_id in seen_operation_targets:
            problems.append(
                Problem(
                    entry.line_number,
                    label,
                    "conflicting-operations",
                    f"{entry.req_id} is named by more than one operation in this delta",
                )
            )
        seen_operation_targets.add(entry.req_id)

        if entry.operation is DeltaOperation.ADDED:
            if entry.req_id in existing_ids:
                problems.append(
                    Problem(
                        entry.line_number,
                        label,
                        "duplicate-requirement",
                        f"{entry.req_id} already exists in the spec",
                    )
                )
            elif entry.req_id in introduced_ids:
                problems.append(
                    Problem(
                        entry.line_number,
                        label,
                        "duplicate-requirement",
                        f"{entry.req_id} is introduced more than once in this delta",
                    )
                )
            introduced_ids.add(entry.req_id)

        elif entry.operation in (DeltaOperation.MODIFIED, DeltaOperation.REMOVED):
            if entry.req_id not in existing_ids and entry.req_id not in renamed_new_ids:
                problems.append(
                    Problem(
                        entry.line_number,
                        label,
                        "dangling-requirement",
                        f"{entry.req_id} is not defined in the spec",
                    )
                )
            elif entry.req_id in existing_ids:
                current_block = spec_section.block_by_id(entry.req_id)
                if (
                    current_block is not None
                    and entry.before is not None
                    and _normalize(entry.before) != _normalize(current_block.render())
                ):
                    problems.append(
                        Problem(
                            entry.line_number,
                            label,
                            "stale-before",
                            "before-block does not match the current spec — this "
                            "delta was written against an older revision",
                        )
                    )
            if (
                entry.operation is DeltaOperation.MODIFIED
                and entry.before is not None
                and entry.after is not None
            ):
                problems.extend(_content_loss_problems(entry, label))

        elif entry.operation is DeltaOperation.RENAMED:
            if entry.req_id not in existing_ids:
                problems.append(
                    Problem(
                        entry.line_number,
                        label,
                        "dangling-requirement",
                        f"{entry.req_id} is not defined in the spec",
                    )
                )
            new_id = entry.new_req_id or ""
            if new_id in existing_ids:
                problems.append(
                    Problem(
                        entry.line_number,
                        label,
                        "duplicate-requirement",
                        f"{new_id} already exists in the spec",
                    )
                )
            elif new_id in introduced_ids:
                problems.append(
                    Problem(
                        entry.line_number,
                        label,
                        "duplicate-requirement",
                        f"{new_id} is introduced more than once in this delta",
                    )
                )
            introduced_ids.add(new_id)

    existing_task_ids = {task.task_id for phase in tasks_phases for task in phase.tasks}
    seen_task_ids: set[str] = set()
    for task_entry in document.task_entries:
        label = f"{task_entry.kind.upper()} {task_entry.task_id}"
        if task_entry.task_id in seen_task_ids:
            problems.append(
                Problem(
                    task_entry.line_number,
                    label,
                    "duplicate-task",
                    f"{task_entry.task_id} appears more than once in this delta",
                )
            )
        seen_task_ids.add(task_entry.task_id)

        if task_entry.kind == "withdrawn" and task_entry.task_id not in existing_task_ids:
            problems.append(
                Problem(
                    task_entry.line_number,
                    label,
                    "unknown-task",
                    "no such task in tasks.md",
                )
            )
        elif task_entry.kind == "added" and task_entry.task_id in existing_task_ids:
            problems.append(
                Problem(
                    task_entry.line_number,
                    label,
                    "duplicate-task",
                    f"{task_entry.task_id} already exists in tasks.md",
                )
            )

    return tuple(problems)


__all__ = ["DeltaValidationError", "Problem", "validate_delta"]
