"""Workflow value objects for reconcile (data-model.md §2-3)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from maverick.assumptions.models import Severity

__all__ = [
    "AnswerOutcome",
    "ChangedAnswer",
    "ReconcileReport",
    "ReconcileStage",
]


class ReconcileStage(StrEnum):
    """Per-answer state machine stage (data-model.md §3).

    Shared by :class:`AnswerOutcome.stage_reached` here and by
    ``state.py``'s ``AnswerState.stage`` field — this enum is the single
    source of truth for both.

    Transitions: ``PENDING -> SNAPSHOTTED -> CORRECTED ->
    CONFLICTS_RESOLVED -> SEMANTIC_DONE -> GATED -> TERMINAL``. Any stage
    before ``TERMINAL``, on failure or interruption discovery, restores via
    ``restore_operation(restore_op_id)`` and lands at
    ``TERMINAL`` with a ``needs_interactive_review`` terminal status.

    Attributes:
        PENDING: Detected as a changed answer; no mutation attempted yet.
        SNAPSHOTTED: Restore point (jj op id) captured for this answer.
        CORRECTED: Correction agent applied and squashed/absorbed.
        CONFLICTS_RESOLVED: Descendant rebase conflicts resolved (if any).
        SEMANTIC_DONE: Semantic-dependents pass completed.
        GATED: Independent gate (format/lint/typecheck/test) has run.
        TERMINAL: Answer processing finished — reconciled, skipped, or
            needs-interactive-review.
    """

    PENDING = "pending"
    SNAPSHOTTED = "snapshotted"
    CORRECTED = "corrected"
    CONFLICTS_RESOLVED = "conflicts_resolved"
    SEMANTIC_DONE = "semantic_done"
    GATED = "gated"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class ChangedAnswer:
    """One human answer that changed since it was last stamped (data-model.md §2).

    Validation: ``target_change_id is None`` implies a terminal
    ``needs-interactive-review`` outcome before any mutation is attempted
    (the target stamp is unlocatable, e.g. rewritten out of the stack).

    Attributes:
        entry_id: The ledger entry's bd bead id.
        question: The question, parsed from the entry's description.
        adopted_answer: The old adopted answer, parsed from the description.
        human_answer: The current ``assumption_answer`` state value.
        severity: The entry's enforcement severity.
        owner_spec: Owning spec identifier.
        stamped_change_ids: Raw jj change ids stamped on this entry.
        target_change_id: Earliest resolvable stamp (research R2); ``None``
            when unlocatable.
        stack_index: Position in ``::@`` (0 = earliest) — sort key (FR-002).
    """

    entry_id: str
    question: str
    adopted_answer: str
    human_answer: str
    severity: Severity
    owner_spec: str
    stamped_change_ids: tuple[str, ...]
    target_change_id: str | None
    stack_index: int


@dataclass(frozen=True, slots=True)
class AnswerOutcome:
    """Terminal outcome for one changed answer (data-model.md §2, FR-019).

    Status taxonomy — exactly one terminal status per answer, spelled three
    different ways across three layers (one status, three per-layer
    spellings; this dataclass owns the Python spelling):

    | Layer                                          | Spelling                     |
    |-------------------------------------------------|-------------------------------|
    | bd state value (``assumption_reconcile_status``) | ``needs-interactive-review``  |
    | Python ``AnswerOutcome.status`` literal          | ``needs_interactive_review``  |
    | CLI summary table                                | ``needs interactive review``  |

    ``skipped`` = no mutation attempted (immutable or unlocatable target).
    ``needs_interactive_review`` = application attempted and rolled back.
    Both write the ``needs-interactive-review`` ledger state so the FR-017
    re-arm rule applies uniformly.

    Attributes:
        entry_id: The ledger entry's bd bead id.
        status: ``"reconciled"`` | ``"skipped"`` | ``"needs_interactive_review"``.
        reason: Short explanation; empty for ``"reconciled"``.
        stage_reached: The furthest :class:`ReconcileStage` reached.
        target_change_id: Post-fold change id, set when reconciled.
        escalation_bead_id: Set when a review bead was created on exhaustion.
        gate_passed: ``None`` if the independent gate never ran.
        no_change_required: True for the empty-delta edge case (the
            correction agent found nothing to change).
    """

    entry_id: str
    status: Literal["reconciled", "skipped", "needs_interactive_review"]
    stage_reached: ReconcileStage
    reason: str = ""
    target_change_id: str | None = None
    escalation_bead_id: str | None = None
    gate_passed: bool | None = None
    no_change_required: bool = False


@dataclass(frozen=True, slots=True)
class ReconcileReport:
    """Final run summary returned to the CLI (data-model.md §2).

    Attributes:
        run_id: Matches the ``.maverick/runs/<run-id>/`` directory name.
        outcomes: One :class:`AnswerOutcome` per processed changed answer.
        dry_run: True when the run only previewed changed answers.
        started_at: UTC ISO-8601 run start timestamp.
        finished_at: UTC ISO-8601 run end timestamp.
    """

    run_id: str
    outcomes: tuple[AnswerOutcome, ...]
    dry_run: bool
    started_at: str
    finished_at: str

    @property
    def exit_success(self) -> bool:
        """Whether the run should exit 0 (data-model.md §2 exit-code rule).

        True when every outcome is ``"reconciled"``, or there were no
        outcomes at all (nothing to reconcile). False otherwise — maps to
        the CLI's SUCCESS/FAILURE exit codes.
        """
        return all(outcome.status == "reconciled" for outcome in self.outcomes)

    def to_dict(self) -> dict[str, object]:
        """JSON-friendly shape returned as the workflow's ``final_output``.

        Mirrors ``SpecChainReport.to_dict()``'s pattern (one flat dict,
        nested records expanded by hand rather than via ``dataclasses.asdict``
        so enum members serialize as their string value). The CLI (T018)
        and later transaction-boundary work (T020/T021) both consume this
        shape, so it also carries the derived ``exit_success`` flag rather
        than making every caller recompute it.
        """
        return {
            "run_id": self.run_id,
            "outcomes": [
                {
                    "entry_id": outcome.entry_id,
                    "status": outcome.status,
                    "reason": outcome.reason,
                    "stage_reached": outcome.stage_reached.value,
                    "target_change_id": outcome.target_change_id,
                    "escalation_bead_id": outcome.escalation_bead_id,
                    "gate_passed": outcome.gate_passed,
                    "no_change_required": outcome.no_change_required,
                }
                for outcome in self.outcomes
            ],
            "dry_run": self.dry_run,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_success": self.exit_success,
        }
