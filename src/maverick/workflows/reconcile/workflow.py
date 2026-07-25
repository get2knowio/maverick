"""``ReconcileWorkflow`` — transaction boundaries, gates, ledger terminal writes.

Orchestration (T017/T020-T022/T026): recover any interrupted prior run ->
clean-working-copy + concurrency preconditions (fly-flying guard, reconcile
lockfile) -> detect -> order -> per-answer {re-resolve target against
current stack (T032/T033, second+ answers only) -> snapshot -> correct ->
resolve conflicts -> gate -> mark reconciled} -> final landing.
Rollback-on-failure (jj op restore) is threaded through
:meth:`ReconcileWorkflow._process_one_answer` / :meth:`_finish_needs_review`;
interrupted-run recovery is :meth:`_recover_interrupted_run`. Conflict
resolution (T026) sits between the correction and gate stages, calling
:func:`maverick.workflows.reconcile.conflicts.resolve_conflicts`; on failure
(unresolvable files, budget exhaustion, or an internal action error)
``_finish_needs_review`` also creates an escalation bead via
``assumptions.ledger.create_reconcile_escalation`` (research R8: only after
the jj rollback completes) before the terminal ledger write. The semantic-
dependents pass (T030) sits between ``CONFLICTS_RESOLVED`` and the gate,
calling :func:`maverick.workflows.reconcile.semantic.run_semantic_pass`
with the correction stage's captured ``correction_diff``; on failure
(budget exhaustion or an internal action error) it escalates the same way,
via ``_finish_needs_review``'s ``escalation_kind="semantic"`` path. The
mutability/skip guard (T034) runs two pre-mutation checks — unlocatable
target, then (once resolved) :func:`~maverick.library.actions.jj.jj_check_mutability`
— both BEFORE ``jj_snapshot_operation`` is ever called, since nothing is
mutated if either trips; both terminal-mark ``status="skipped"`` (data-model.md
§2) via ``_finish_needs_review``'s ``outcome_status`` parameter. ``--dry-run``
(T035, :meth:`_predict_dry_run_outcomes`) branches right after detection +
ordering: every precondition above (interrupted-run recovery, clean working
copy, fly-flying guard, reconcile lockfile) still runs unchanged, but the
per-answer mutation pipeline (snapshot/correct/conflicts/semantic/gate/
ledger-write/run-state-checkpoint) never runs at all — only the same two
pre-mutation guards used by ``_process_one_answer`` run (read-only), and the
predicted outcome is returned immediately with zero calls to
``jj_snapshot_operation``, ``ReconcileSquadron``, ``mark_reconciled``, or
``save_run_state`` (contract: "zero jj/bd/filesystem mutations"). See
specs/051-reconcile-changed-answers/research.md R2/R4/R5/R6/R7/R8/R9/R13/R14
and data-model.md for the full contract.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from maverick.assumptions.ledger import (
    create_reconcile_escalation,
    mark_needs_interactive_review,
    mark_reconciled,
)
from maverick.assumptions.models import AssumptionRecord
from maverick.beads.client import BeadClient
from maverick.exceptions import WorkflowError
from maverick.jj.client import JjClient
from maverick.library.actions.jj import (
    jj_check_mutability,
    jj_list_conflicts,
    jj_new_child,
    jj_restore_operation,
    jj_snapshot_operation,
)
from maverick.library.actions.validation import (
    run_independent_gate,
    validation_commands_from_config,
)
from maverick.logging import get_logger
from maverick.runway.run_metadata import RunMetadata, read_metadata
from maverick.squadron.reconcile import ReconcileSquadron
from maverick.workflows.base import PythonWorkflow
from maverick.workflows.reconcile.conflicts import resolve_conflicts
from maverick.workflows.reconcile.correction import apply_correction
from maverick.workflows.reconcile.detection import (
    build_changed_answers,
    resolve_target_against_current_stack,
)
from maverick.workflows.reconcile.models import (
    AnswerOutcome,
    ChangedAnswer,
    ReconcileReport,
    ReconcileStage,
)
from maverick.workflows.reconcile.semantic import run_semantic_pass
from maverick.workflows.reconcile.state import (
    AnswerState,
    ReconcileRunState,
    acquire_lock,
    discover_resumable,
    release_lock,
    save_run_state,
)

__all__ = ["WORKFLOW_NAME", "ReconcileWorkflow"]

logger = get_logger(__name__)

#: Read by the CLI (T018) from this module's namespace.
WORKFLOW_NAME = "reconcile"

#: The independent gate suite (research R7) — full stages, unlike fly's
#: per-bead gate, because reconcile rewrites arbitrary history and must
#: prove the whole head green, not just one bead's slice.
_GATE_STAGES: tuple[str, ...] = ("format", "lint", "typecheck", "test")


def _utcnow_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def _answer_as_assumption_record(answer: ChangedAnswer) -> AssumptionRecord:
    """Build the minimal ``AssumptionRecord`` shape ``create_reconcile_escalation`` needs.

    Shared by every escalation call site in :meth:`ReconcileWorkflow._finish_needs_review`
    (conflicts, T026; semantic-dependents, T030) — both need only the
    question/adopted-answer/severity/owner-spec fields ``create_reconcile_escalation``
    reads to build the escalation bead's description; the rest are
    placeholder values the ledger layer doesn't consult for this path.
    """
    return AssumptionRecord(
        bead_id=answer.entry_id,
        question=answer.question,
        adopted_answer=answer.adopted_answer,
        alternatives=(),
        severity=answer.severity,
        severity_defaulted=False,
        status="answered",
        owner_spec=answer.owner_spec,
        source_bead="",
        change_ids=answer.stamped_change_ids,
        is_legacy=False,
    )


def _find_flying_run(cwd: Path, *, exclude_run_id: str | None = None) -> RunMetadata | None:
    """Return metadata for any *other* fly run currently mid-flight ("flying").

    Implements contract precondition 4's "no fly run metadata in status
    flying" half (the other half is the reconcile lockfile, guarded
    separately via ``acquire_lock``). ``maverick.runway.run_metadata`` has
    no ready-made "is anything flying right now" query —
    ``find_run_for_epic``/``find_latest_run`` both require a specific
    epic/plan key as the lookup, but this guard is repo-wide (reconcile
    isn't scoped to one epic). This mirrors those functions' own
    directory-scan mechanics — plain sync file reads called directly from
    async code, same as every existing call site in
    ``fly_beads/workflow.py`` — with no filter beyond status.

    ``exclude_run_id`` (052-conditional-landing, research R7) is the
    calling fly run's own ``run_id`` when this reconcile is invoked
    in-process as a mid-flight pass — that run is, by construction,
    parked at a safe boundary awaiting this pass, so its own "flying"
    metadata must not trip the guard. Any *other* run still flying still
    raises. The standalone CLI passes nothing, so ``None`` never matches
    and behavior there is unchanged.
    """
    runs_dir = cwd / ".maverick" / "runs"
    if not runs_dir.is_dir():
        return None
    for candidate in runs_dir.iterdir():
        meta = read_metadata(candidate)
        if meta is None or meta.status != "flying":
            continue
        if exclude_run_id is not None and meta.run_id == exclude_run_id:
            continue
        return meta
    return None


def _replace_answer_state(
    run_state: ReconcileRunState,
    entry_id: str,
    **updates: Any,
) -> ReconcileRunState:
    """Return *run_state* with the named answer's checkpoint updated.

    ``AnswerState`` and ``ReconcileRunState`` are frozen Pydantic models —
    every transition builds fresh copies (same functional-update pattern as
    spec-chain's ``_set_step``).
    """
    new_answers = [
        answer_state.model_copy(update=updates)
        if answer_state.entry_id == entry_id
        else answer_state
        for answer_state in run_state.answers
    ]
    return run_state.model_copy(update={"answers": new_answers, "updated_at": _utcnow_iso()})


class ReconcileWorkflow(PythonWorkflow):
    """Runs the transactional reconcile pass over changed assumption answers."""

    def __init__(self, **kwargs: Any) -> None:
        if "workflow_name" not in kwargs:
            kwargs["workflow_name"] = WORKFLOW_NAME
        super().__init__(**kwargs)

    async def _run(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute one reconcile run.

        Args:
            inputs: Required: ``run_id`` (str — caller-supplied, like
                spec-chain), ``cwd`` (str, user checkout). Optional:
                ``active_fly_run_id`` (str | None, default None) — set by
                fly's mid-flight pass (052-conditional-landing) to the
                calling fly run's own ``run_id`` so the concurrent-fly
                guard excludes it (see :func:`_find_flying_run`); the
                standalone CLI never sets this.

        Returns:
            :meth:`ReconcileReport.to_dict`.

        Raises:
            WorkflowError: If the working copy is not clean (FR-014), if a
                *different* fly run is currently in status "flying", or if
                the reconcile lockfile is held by another live process.
        """
        run_id: str = inputs["run_id"]
        cwd = Path(inputs["cwd"])
        dry_run = bool(inputs.get("dry_run", False))
        active_fly_run_id: str | None = inputs.get("active_fly_run_id")
        started_at = _utcnow_iso()

        bead_client = BeadClient(cwd=cwd)

        # Dry-run is a read-only preview (contract cli-reconcile.md: "zero
        # jj/bd/filesystem mutations"), so it branches out BEFORE the two
        # mutating steps every real run performs — interrupted-run recovery
        # (jj op restore + bd mark + run-state write) and lockfile
        # acquisition — and never touches them. Only detection, ordering, and
        # the read-only mutability guard run.
        if dry_run:
            return await self._run_dry_run(
                run_id=run_id, cwd=cwd, bead_client=bead_client, started_at=started_at
            )

        # Interrupted-run recovery (FR-016, research R9) runs unconditionally
        # first — before the clean-working-copy check below and before the
        # concurrency guards. Ordering rationale in the method's own
        # docstring: a crashed run's in-flight answer can leave `@` dirty,
        # and this is what repairs that; per contracts/cli-reconcile.md's
        # "Preconditions" exception, an interrupted prior run must never be
        # treated as a blocking concurrent run either.
        await self._recover_interrupted_run(bead_client, cwd=cwd)

        await self.emit_step_started("detect", display_label="Detecting changed answers")

        jj_client = JjClient(cwd=cwd)
        working_copy_stat = await jj_client.diff_stat(revision="@")
        if working_copy_stat.files_changed != 0:
            raise WorkflowError(
                "working copy is not clean — commit or discard changes before running reconcile"
            )

        # Concurrency guards (contract "Preconditions" item 4). The
        # fly-flying check is a cheap read-only metadata scan, so it runs
        # before lock acquisition, which mutates the filesystem.
        flying_run = _find_flying_run(cwd, exclude_run_id=active_fly_run_id)
        if flying_run is not None:
            raise WorkflowError("cannot run reconcile while a fly run is in progress")

        acquired = await acquire_lock(cwd)
        if not acquired:
            raise WorkflowError(
                "another reconcile run is already in progress (lockfile held by a live process)"
            )

        try:
            # Original tip, captured before any mutation (research R13):
            # change ids are stable across rebase, so re-resolving this at
            # the end finds its new position on the rebased head for the
            # final landing.
            original_parent_log = await jj_client.log(revset="@-", limit=1)
            original_parent_change_id = original_parent_log.changes[0].change_id

            # Earliest-in-stack first (FR-002). Detection + this sort run
            # once, before any repair — the per-answer loop below (T032/T033,
            # research R2/R13) re-resolves each subsequent answer's target
            # against a fresh stack snapshot immediately before it is
            # processed, since an earlier answer's fold may have just rebased
            # this stack.
            ordered_answers = await self._detect_and_order(bead_client, cwd=cwd)
            await self.emit_step_completed("detect", output={"count": len(ordered_answers)})

            if not ordered_answers:
                await self.emit_output(
                    "detect", "No changed answers — nothing to reconcile.", level="info"
                )
                report = ReconcileReport(
                    run_id=run_id,
                    outcomes=(),
                    dry_run=False,
                    started_at=started_at,
                    finished_at=_utcnow_iso(),
                )
                return report.to_dict()

            run_state = ReconcileRunState(
                run_id=run_id,
                status="running",
                updated_at=_utcnow_iso(),
                answers=[
                    AnswerState(
                        entry_id=answer.entry_id,
                        target_change_id=answer.target_change_id,
                        restore_op_id=None,
                        stage=ReconcileStage.PENDING,
                    )
                    for answer in ordered_answers
                ],
            )
            await save_run_state(run_state, cwd)

            outcomes: list[AnswerOutcome] = []
            async with ReconcileSquadron(cwd=cwd, config=self._config, cost_sink=None) as squadron:
                for index, answer in enumerate(ordered_answers):
                    # Post-repair re-resolution (T032/T033, research R2/R13):
                    # the batch-wide stack_index sort above ran once against
                    # the pre-run stack. By the time the SECOND (or later)
                    # answer reaches this point, every prior answer's
                    # correction has already folded via squash/absorb, which
                    # auto-rebases descendants in the same jj operation — so
                    # this answer's previously-computed target/position may
                    # now be stale. Change ids are stable across rebase
                    # (R13), so the same stamped ids are re-verified here
                    # against a FRESH `all()` snapshot rather than trusting the
                    # one computed at the top of this run. The first answer
                    # is skipped: nothing has been rebased yet when it is
                    # processed, so its pre-run resolution is still current.
                    if index > 0:
                        (
                            new_target_change_id,
                            new_stack_index,
                        ) = await resolve_target_against_current_stack(
                            answer.stamped_change_ids, cwd=cwd
                        )
                        if (new_target_change_id, new_stack_index) != (
                            answer.target_change_id,
                            answer.stack_index,
                        ):
                            logger.info(
                                "reconcile_answer_target_reresolved",
                                entry_id=answer.entry_id,
                                old_target_change_id=answer.target_change_id,
                                new_target_change_id=new_target_change_id,
                                old_stack_index=answer.stack_index,
                                new_stack_index=new_stack_index,
                            )
                            answer = dataclasses.replace(
                                answer,
                                target_change_id=new_target_change_id,
                                stack_index=new_stack_index,
                            )
                            run_state = _replace_answer_state(
                                run_state,
                                answer.entry_id,
                                target_change_id=new_target_change_id,
                            )
                            await save_run_state(run_state, cwd)

                    outcome, run_state = await self._process_one_answer(
                        answer,
                        squadron=squadron,
                        bead_client=bead_client,
                        cwd=cwd,
                        run_state=run_state,
                    )
                    outcomes.append(outcome)

            # Land the final empty working copy on the rebased head (R13).
            # Best-effort — cosmetic, must never fail the run.
            try:
                resolved_log = await jj_client.log(revset=original_parent_change_id, limit=1)
                if resolved_log.changes:
                    await jj_new_child(parent=resolved_log.changes[0].change_id, cwd=cwd)
            except Exception as exc:  # noqa: BLE001 - final landing is cosmetic, best-effort
                logger.warning("reconcile_final_landing_failed", error=str(exc))

            # Run-completion checkpoint is post-commit bookkeeping: every
            # answer's outcome is already terminal-marked in the ledger, so a
            # failure persisting the "completed" run-state must not surface as
            # a run crash (which would misreport already-committed work as
            # failed). Best-effort, same rationale as the final landing above.
            try:
                run_state = run_state.model_copy(
                    update={"status": "completed", "updated_at": _utcnow_iso()}
                )
                await save_run_state(run_state, cwd)
            except Exception as exc:  # noqa: BLE001 - completion checkpoint is best-effort
                logger.warning("reconcile_completion_checkpoint_failed", error=str(exc))

            report = ReconcileReport(
                run_id=run_id,
                outcomes=tuple(outcomes),
                dry_run=False,
                started_at=started_at,
                finished_at=_utcnow_iso(),
            )
            logger.info(
                "reconcile_finished",
                run_id=run_id,
                reconciled=sum(1 for o in outcomes if o.status == "reconciled"),
                needs_review=sum(1 for o in outcomes if o.status != "reconciled"),
            )
            return report.to_dict()
        finally:
            # Releases on every exit — success, a raised WorkflowError/other
            # exception, or `asyncio.CancelledError` from a Ctrl-C: Python's
            # `finally` unwinds identically for all three, so a single block
            # covers what a `register_rollback`-based interrupt handler
            # would (see spec_chain/workflow.py's
            # `_checkpoint_halted_on_cancel` for that alternative pattern —
            # not needed here since nothing after this point needs to run
            # *outside* this call frame). The one case neither this nor
            # `register_rollback` can cover is a hard crash (`kill -9`),
            # which runs no Python cleanup at all; `acquire_lock`'s
            # stale-pid reclaim (state.py) is what closes that gap on the
            # next invocation.
            await release_lock(cwd)

    async def _detect_and_order(
        self,
        bead_client: BeadClient,
        *,
        cwd: Path,
    ) -> tuple[ChangedAnswer, ...]:
        """Detect changed answers and order them earliest-in-stack first (FR-002).

        Read-only (jj log + bd query); shared verbatim by the real-run and
        dry-run paths so the two can never diverge on what counts as a
        changed answer or how the worklist is ordered.
        """
        changed_answers = await build_changed_answers(bead_client, cwd=cwd)
        return tuple(sorted(changed_answers, key=lambda answer: answer.stack_index))

    async def _run_dry_run(
        self,
        *,
        run_id: str,
        cwd: Path,
        bead_client: BeadClient,
        started_at: str,
    ) -> dict[str, Any]:
        """Dry-run preview path: detection + ordering + mutability guard only.

        Per contract (``contracts/cli-reconcile.md`` "Preconditions"),
        ``--dry-run`` performs "zero jj/bd/filesystem mutations". This path
        therefore never runs interrupted-run recovery or acquires the run
        lock (both mutate) and never enters the concurrency guards — it only
        reads. Outcomes are predicted by :meth:`_predict_dry_run_outcomes`,
        which stops at the read-only mutability guard.
        """
        await self.emit_step_started("detect", display_label="Detecting changed answers")
        ordered_answers = await self._detect_and_order(bead_client, cwd=cwd)
        await self.emit_step_completed("detect", output={"count": len(ordered_answers)})

        if not ordered_answers:
            await self.emit_output(
                "detect", "No changed answers — nothing to reconcile.", level="info"
            )
            outcomes: tuple[AnswerOutcome, ...] = ()
        else:
            outcomes = await self._predict_dry_run_outcomes(ordered_answers, cwd=cwd)

        report = ReconcileReport(
            run_id=run_id,
            outcomes=outcomes,
            dry_run=True,
            started_at=started_at,
            finished_at=_utcnow_iso(),
        )
        return report.to_dict()

    async def _predict_dry_run_outcomes(
        self,
        ordered_answers: tuple[ChangedAnswer, ...],
        *,
        cwd: Path,
    ) -> tuple[AnswerOutcome, ...]:
        """Predict a terminal outcome per answer with zero mutations (T035).

        Mirrors the first two pre-mutation guards of
        :meth:`_process_one_answer` (unlocatable target, then
        :func:`~maverick.library.actions.jj.jj_check_mutability`) — both
        read-only or no-op — and stops there: a mutable, resolved target is
        predicted ``"reconciled"`` without ever constructing a
        :class:`~maverick.squadron.reconcile.ReconcileSquadron`, calling
        :func:`~maverick.library.actions.jj.jj_snapshot_operation`, or
        applying a correction. Per the contract
        (``contracts/cli-reconcile.md`` "Invocation"), ``--dry-run`` is
        "detection, stack ordering, target resolution, and mutability
        checks only" with "zero jj/bd/filesystem mutations" — this predicts
        the same terminal status the real run would reach for that pair of
        guards, without running anything past them (no gate, no conflict
        resolution, no semantic pass, no ledger writes, no run-state
        checkpointing). Answers are processed independently and in order,
        but — unlike the real per-answer loop — never re-resolved against a
        post-fold stack snapshot (T032/T033): nothing mutates between
        answers in a dry run, so the batch-wide resolution computed once by
        :func:`~maverick.workflows.reconcile.detection.build_changed_answers`
        stays valid for every answer in the batch.

        Args:
            ordered_answers: Changed answers, already sorted by
                ``stack_index`` (FR-002).
            cwd: Repository working directory.

        Returns:
            One :class:`AnswerOutcome` per answer, each ``stage_reached``
            :attr:`ReconcileStage.PENDING` (no stage was ever entered) and
            ``status`` either ``"reconciled"`` or ``"skipped"`` — never
            ``"needs_interactive_review"``, since nothing is ever attempted
            (data-model.md §2: that status is reserved for an attempted-
            then-rolled-back mutation).
        """
        outcomes: list[AnswerOutcome] = []
        for answer in ordered_answers:
            if answer.target_change_id is None:
                outcomes.append(
                    AnswerOutcome(
                        entry_id=answer.entry_id,
                        status="skipped",
                        stage_reached=ReconcileStage.PENDING,
                        reason="unresolvable correction target",
                    )
                )
                continue

            mutability = await jj_check_mutability(target=answer.target_change_id, cwd=cwd)
            if not mutability["success"]:
                outcomes.append(
                    AnswerOutcome(
                        entry_id=answer.entry_id,
                        status="skipped",
                        stage_reached=ReconcileStage.PENDING,
                        reason=(
                            "mutability check failed, failing safe: "
                            f"{mutability.get('error') or 'unknown error'}"
                        ),
                        target_change_id=answer.target_change_id,
                    )
                )
                continue
            if not mutability["mutable"]:
                immutable_ids = ", ".join(mutability["immutable_change_ids"])
                outcomes.append(
                    AnswerOutcome(
                        entry_id=answer.entry_id,
                        status="skipped",
                        stage_reached=ReconcileStage.PENDING,
                        reason=(
                            "correction target or a descendant it would rebase is "
                            f"immutable: {immutable_ids}"
                        ),
                        target_change_id=answer.target_change_id,
                    )
                )
                continue

            outcomes.append(
                AnswerOutcome(
                    entry_id=answer.entry_id,
                    status="reconciled",
                    stage_reached=ReconcileStage.PENDING,
                    target_change_id=answer.target_change_id,
                    reason="",
                )
            )
        return tuple(outcomes)

    async def _recover_interrupted_run(self, bead_client: BeadClient, *, cwd: Path) -> None:
        """Recover a crashed/stuck prior reconcile run before this one starts.

        research.md R9 + contracts/cli-reconcile.md "Preconditions"
        exception: a discovered ``status="running"`` prior run *is* the
        crash signal (reconcile has no separate "halted" status, unlike
        spec-chain) — it does NOT block this invocation. Any answer left
        in a non-terminal stage is rolled back via its captured
        ``restore_op_id`` and terminal-marked needs-interactive-review
        (reason ``"interrupted"``); the old run's state is then retired to
        ``status="failed"`` so :func:`discover_resumable` never finds it
        again. This invocation continues as a fresh run — the retired
        answer, now excluded from ``answered_unreconciled_entries()`` by
        its terminal reconcile status, simply won't reappear in this run's
        own detection pass; no special-casing is needed there.

        Defensive against more than one non-terminal answer even though the
        workflow only ever has one in flight at a time (sequential
        per-answer processing, checkpointed after every transition).

        A failed restore is logged at error level but does not stop the
        rest of recovery (or this run) — matches ``_finish_needs_review``'s
        rollback-failure handling: a rollback failing is more serious than
        an ordinary needs-review exit, but must never crash the caller.
        """
        resumable = await discover_resumable(cwd)
        if resumable is None:
            return

        non_terminal = [
            answer_state
            for answer_state in resumable.answers
            if answer_state.stage != ReconcileStage.TERMINAL
        ]
        for answer_state in non_terminal:
            if answer_state.restore_op_id is not None:
                try:
                    await jj_restore_operation(answer_state.restore_op_id, cwd=cwd)
                except Exception as exc:  # noqa: BLE001 - recovery must not crash this run
                    logger.error(
                        "reconcile_interrupted_run_restore_failed",
                        entry_id=answer_state.entry_id,
                        restore_op_id=answer_state.restore_op_id,
                        error=str(exc),
                    )
            await mark_needs_interactive_review(
                bead_client, entry_id=answer_state.entry_id, reason="interrupted"
            )

        retired = resumable.model_copy(update={"status": "failed", "updated_at": _utcnow_iso()})
        await save_run_state(retired, cwd)
        logger.info(
            "reconcile_interrupted_run_recovered",
            run_id=resumable.run_id,
            recovered_answers=[answer_state.entry_id for answer_state in non_terminal],
        )

    async def _process_one_answer(
        self,
        answer: ChangedAnswer,
        *,
        squadron: ReconcileSquadron,
        bead_client: BeadClient,
        cwd: Path,
        run_state: ReconcileRunState,
    ) -> tuple[AnswerOutcome, ReconcileRunState]:
        """Run the per-answer stage sequence for one changed answer.

        Conflict resolution (T026) runs between CORRECTED and the gate:
        :func:`~maverick.workflows.reconcile.conflicts.resolve_conflicts`
        resolves any descendant rebase conflicts left by the fold within a
        ``reconcile.resolution_rounds`` budget; a non-resolved outcome
        (agent-declared unresolvable files, budget exhaustion, or an
        internal action error) escalates via ``_finish_needs_review``'s
        ``escalation_kind="conflicts"`` path. The semantic-dependents pass
        (T030) runs next, between CONFLICTS_RESOLVED and the gate, calling
        :func:`~maverick.workflows.reconcile.semantic.run_semantic_pass`
        with the correction stage's ``correction_diff``; a non-completed
        outcome (budget exhaustion or an internal action error) escalates
        the same way via ``escalation_kind="semantic"``. The mutability/skip
        guard (T034) runs two pre-mutation checks, both before SNAPSHOTTED:
        an unlocatable target (``target_change_id is None``), then — once a
        target is resolved — :func:`~maverick.library.actions.jj.jj_check_mutability`.
        Either tripping produces ``status="skipped"`` (data-model.md §2:
        no mutation was ever attempted), never ``needs_interactive_review``.
        Any unexpected exception anywhere in this sequence is caught so one
        answer's failure never crashes the run (the bare-except is
        intentional here — see the docstring for the broad catch below).

        Transaction boundary (T020/T021/T026/T030, research R8, data-model.md
        §3): once ``restore_op_id`` is captured, every failure exit —
        correction failure, conflict-resolution failure, semantic-pass
        failure, post-semantic conflict guard, gate failure, or the broad
        exception handler — MUST restore the jj operation log to that point
        *before* writing any bd terminal state (including any escalation
        bead). ``_finish_needs_review`` enforces that ordering; callers here
        only need to thread ``restore_op_id`` through. The two ``"skipped"``
        exits (unlocatable target, mutability guard) are the documented
        exceptions — both happen before any snapshot exists, so there is
        nothing to restore. The boundary CLOSES at ``mark_reconciled``: once
        the ledger records the entry reconciled the correction is committed,
        so ``restore_op_id`` is cleared and the trailing run-state/event
        bookkeeping is best-effort — a failure there must never roll the
        committed correction back (it would strand the entry permanently).
        """
        step_name = f"answer.{answer.entry_id}"
        await self.emit_step_started(step_name, display_label=f"Reconciling {answer.entry_id}")

        stage_reached = ReconcileStage.PENDING
        # Set once the restore-point snapshot is captured below; stays
        # None for the two pre-mutation "skipped" exits (unlocatable
        # target, mutability guard), which both precede any snapshot and
        # therefore have nothing to roll back (research R8).
        restore_op_id: str | None = None
        try:
            # Session rotation is inside the try (nothing is snapshotted
            # yet, so restore_op_id stays None): a rotation failure must
            # escalate this one answer via the broad handler below, never
            # crash the whole run (the per-answer isolation contract).
            await squadron.rotate_for_new_bead()
            if answer.target_change_id is None:
                # data-model.md §2: target_change_id is None => "skipped"
                # (no mutation ever attempted, FR-015) — NOT
                # needs_interactive_review. Cheapest check, no jj call at
                # all, so it runs before the mutability guard below.
                return await self._finish_needs_review(
                    answer,
                    bead_client=bead_client,
                    cwd=cwd,
                    run_state=run_state,
                    step_name=step_name,
                    stage_reached=stage_reached,
                    reason="unresolvable correction target",
                    outcome_status="skipped",
                )

            # Mutability guard (T034, research R4/FR-011/FR-012): one
            # read-only jj revset query (jj_check_mutability is `jj log`
            # under the hood — no mutation), run only once the target IS
            # resolved, and strictly before jj_snapshot_operation below —
            # nothing has been touched yet, so a tripped guard needs no
            # restore point and produces "skipped", never
            # needs_interactive_review (data-model.md §2).
            mutability = await jj_check_mutability(target=answer.target_change_id, cwd=cwd)
            if not mutability["success"]:
                # The check itself failed (e.g. transient jj error) — fail
                # safe: do not assume mutability and risk touching
                # something immutable.
                return await self._finish_needs_review(
                    answer,
                    bead_client=bead_client,
                    cwd=cwd,
                    run_state=run_state,
                    step_name=step_name,
                    stage_reached=stage_reached,
                    reason=(
                        "mutability check failed, failing safe: "
                        f"{mutability.get('error') or 'unknown error'}"
                    ),
                    outcome_status="skipped",
                )
            if not mutability["mutable"]:
                immutable_ids = ", ".join(mutability["immutable_change_ids"])
                return await self._finish_needs_review(
                    answer,
                    bead_client=bead_client,
                    cwd=cwd,
                    run_state=run_state,
                    step_name=step_name,
                    stage_reached=stage_reached,
                    reason=(
                        "correction target or a descendant it would rebase is "
                        f"immutable: {immutable_ids}"
                    ),
                    outcome_status="skipped",
                )

            snapshot = await jj_snapshot_operation(cwd=cwd)
            restore_op_id = snapshot["operation_id"]
            stage_reached = ReconcileStage.SNAPSHOTTED
            run_state = _replace_answer_state(
                run_state,
                answer.entry_id,
                restore_op_id=restore_op_id,
                stage=ReconcileStage.SNAPSHOTTED,
            )
            await save_run_state(run_state, cwd)

            correction_result = await apply_correction(squadron.reconciler, answer, cwd=cwd)
            if not correction_result.applied:
                return await self._finish_needs_review(
                    answer,
                    bead_client=bead_client,
                    cwd=cwd,
                    run_state=run_state,
                    step_name=step_name,
                    stage_reached=stage_reached,
                    reason=correction_result.error or "correction failed",
                    restore_op_id=restore_op_id,
                )

            stage_reached = ReconcileStage.CORRECTED
            run_state = _replace_answer_state(
                run_state, answer.entry_id, stage=ReconcileStage.CORRECTED
            )
            await save_run_state(run_state, cwd)

            conflict_outcome = await resolve_conflicts(
                squadron.reconciler,
                answer,
                cwd=cwd,
                max_rounds=self._config.reconcile.resolution_rounds,
            )
            if not conflict_outcome.resolved:
                if conflict_outcome.unresolvable:
                    remaining: tuple[str, ...] = conflict_outcome.unresolvable
                    reason = (
                        "conflict resolution declared unresolvable files: "
                        f"{', '.join(conflict_outcome.unresolvable)}"
                    )
                elif conflict_outcome.error:
                    remaining = (f"internal error: {conflict_outcome.error}",)
                    reason = f"conflict resolution failed: {conflict_outcome.error}"
                else:
                    remaining = (
                        f"budget exhausted after {conflict_outcome.rounds_used} round(s) "
                        "with conflicts still unresolved",
                    )
                    reason = (
                        "conflict resolution budget exhausted after "
                        f"{conflict_outcome.rounds_used} round(s)"
                    )
                return await self._finish_needs_review(
                    answer,
                    bead_client=bead_client,
                    cwd=cwd,
                    run_state=run_state,
                    step_name=step_name,
                    stage_reached=stage_reached,
                    reason=reason,
                    restore_op_id=restore_op_id,
                    escalation_kind="conflicts",
                    escalation_remaining=remaining,
                )

            stage_reached = ReconcileStage.CONFLICTS_RESOLVED
            run_state = _replace_answer_state(
                run_state, answer.entry_id, stage=ReconcileStage.CONFLICTS_RESOLVED
            )
            await save_run_state(run_state, cwd)

            semantic_outcome = await run_semantic_pass(
                squadron.reconciler,
                squadron.semantic,
                answer,
                correction_result.correction_diff,
                cwd=cwd,
                max_rounds=self._config.reconcile.semantic_rounds,
            )
            if not semantic_outcome.completed:
                if semantic_outcome.error:
                    remaining = (semantic_outcome.error,)
                    reason = f"semantic-dependents pass failed: {semantic_outcome.error}"
                else:
                    remaining = (
                        f"semantic pass exhausted after {semantic_outcome.rounds_used} round(s)",
                    )
                    reason = (
                        "semantic-dependents pass budget exhausted after "
                        f"{semantic_outcome.rounds_used} round(s)"
                    )
                return await self._finish_needs_review(
                    answer,
                    bead_client=bead_client,
                    cwd=cwd,
                    run_state=run_state,
                    step_name=step_name,
                    stage_reached=stage_reached,
                    reason=reason,
                    restore_op_id=restore_op_id,
                    escalation_kind="semantic",
                    escalation_remaining=remaining,
                )

            stage_reached = ReconcileStage.SEMANTIC_DONE
            run_state = _replace_answer_state(
                run_state, answer.entry_id, stage=ReconcileStage.SEMANTIC_DONE
            )
            await save_run_state(run_state, cwd)

            # Post-semantic conflict guard: the semantic-dependents pass folds
            # fixes into descendants AFTER the round-budgeted conflict pass
            # already ran, so a semantic fix can itself introduce a fresh
            # rebase conflict in a deeper descendant that conflict pass never
            # saw. The independent gate below is the primary defense, but it
            # only exercises compiled/tested files — a conflict in a data or
            # doc file the gate never touches would otherwise be committed
            # with literal markers. Refuse to mark reconciled while ANY
            # conflict remains under the target: roll back and escalate rather
            # than commit conflict markers into reconciled history.
            remaining_conflicts = await jj_list_conflicts(
                revset_scope=f"descendants({answer.target_change_id})", cwd=cwd
            )
            if not remaining_conflicts["success"]:
                return await self._finish_needs_review(
                    answer,
                    bead_client=bead_client,
                    cwd=cwd,
                    run_state=run_state,
                    step_name=step_name,
                    stage_reached=stage_reached,
                    reason=(
                        "post-semantic conflict check failed, failing safe: "
                        f"{remaining_conflicts.get('error') or 'unknown error'}"
                    ),
                    restore_op_id=restore_op_id,
                )
            if remaining_conflicts["change_ids"]:
                return await self._finish_needs_review(
                    answer,
                    bead_client=bead_client,
                    cwd=cwd,
                    run_state=run_state,
                    step_name=step_name,
                    stage_reached=stage_reached,
                    reason=(
                        "unresolved conflicts remain after the semantic-dependents "
                        f"pass: {', '.join(remaining_conflicts['change_ids'])}"
                    ),
                    restore_op_id=restore_op_id,
                    escalation_kind="conflicts",
                    escalation_remaining=tuple(remaining_conflicts["change_ids"]),
                )

            gate_result = await run_independent_gate(
                stages=list(_GATE_STAGES),
                cwd=str(cwd),
                validation_commands=validation_commands_from_config(self._config.validation),
                timeout_seconds=self._config.validation.timeout_seconds,
            )
            if not gate_result["passed"]:
                return await self._finish_needs_review(
                    answer,
                    bead_client=bead_client,
                    cwd=cwd,
                    run_state=run_state,
                    step_name=step_name,
                    stage_reached=stage_reached,
                    reason=gate_result.get("summary", "gate failed"),
                    gate_passed=False,
                    restore_op_id=restore_op_id,
                )

            stage_reached = ReconcileStage.GATED
            run_state = _replace_answer_state(
                run_state, answer.entry_id, stage=ReconcileStage.GATED
            )
            await save_run_state(run_state, cwd)

            assert answer.target_change_id is not None  # narrowed above
            await mark_reconciled(
                bead_client,
                entry_id=answer.entry_id,
                applied_answer=answer.human_answer,
                change_id=answer.target_change_id,
            )
            outcome = AnswerOutcome(
                entry_id=answer.entry_id,
                status="reconciled",
                stage_reached=ReconcileStage.TERMINAL,
                target_change_id=answer.target_change_id,
                gate_passed=True,
                no_change_required=correction_result.no_change_required,
            )
            # Transaction COMMITTED: the correction has landed and the ledger
            # records it reconciled (with the applied answer, so detection's
            # idempotence guard now excludes it). A failure in the trailing
            # bookkeeping below MUST NOT reach the broad handler's rollback —
            # restoring the jj op there would undo the good correction while
            # the ledger still says reconciled, stranding the entry forever
            # (research R8's all-or-nothing boundary ends here). Clear the
            # restore point and finish the checkpoint/event best-effort.
            restore_op_id = None
            try:
                run_state = _replace_answer_state(
                    run_state,
                    answer.entry_id,
                    stage=ReconcileStage.TERMINAL,
                    terminal_status=outcome.status,
                )
                await save_run_state(run_state, cwd)
                await self.emit_step_completed(step_name, output={"status": outcome.status})
            except Exception as exc:  # noqa: BLE001 - post-commit bookkeeping is best-effort
                logger.warning(
                    "reconcile_answer_post_commit_bookkeeping_failed",
                    entry_id=answer.entry_id,
                    error=str(exc),
                )
            return outcome, run_state

        except Exception as exc:  # noqa: BLE001 - one answer's failure must not crash the run
            logger.warning(
                "reconcile_answer_processing_failed",
                entry_id=answer.entry_id,
                error=str(exc),
            )
            return await self._finish_needs_review(
                answer,
                bead_client=bead_client,
                cwd=cwd,
                run_state=run_state,
                step_name=step_name,
                stage_reached=stage_reached,
                reason=str(exc),
                restore_op_id=restore_op_id,
            )

    async def _finish_needs_review(
        self,
        answer: ChangedAnswer,
        *,
        bead_client: BeadClient,
        cwd: Path,
        run_state: ReconcileRunState,
        step_name: str,
        stage_reached: ReconcileStage,
        reason: str,
        gate_passed: bool | None = None,
        restore_op_id: str | None = None,
        escalation_kind: Literal["conflicts", "semantic"] | None = None,
        escalation_remaining: Sequence[str] = (),
        outcome_status: Literal["skipped", "needs_interactive_review"] = (
            "needs_interactive_review"
        ),
    ) -> tuple[AnswerOutcome, ReconcileRunState]:
        """Terminal-mark one answer ``skipped`` or ``needs_interactive_review``.

        Shared by every non-success exit from :meth:`_process_one_answer`
        (unlocatable target, immutable target, correction failure,
        conflict-resolution failure, gate failure, unexpected exception) —
        all write the same ledger state (FR-019, via
        ``mark_needs_interactive_review`` regardless of ``outcome_status``)
        and the same run-state shape, differing only in
        ``stage_reached``/``reason``/escalation/``outcome_status``.

        ``outcome_status`` (data-model.md §2) distinguishes the two
        pre-mutation "skipped" guards (unlocatable target, mutability
        guard — no mutation was ever attempted, so ``restore_op_id`` is
        always ``None`` and ``escalation_kind`` is always ``None`` for
        these callers) from every other exit, which attempted a mutation
        that was then rolled back and is ``"needs_interactive_review"``
        (the default). Both spellings write the identical
        ``needs-interactive-review`` bd state — only the Python
        ``AnswerOutcome.status`` literal and the CLI display column
        differ (FR-019/data-model.md §2's spelling table).

        Transaction-boundary ordering (research R8, data-model.md §3): when
        ``restore_op_id`` is set (every exit past the unlocatable-target
        case), the jj operation log is restored to that point *before* any
        bd write happens here — bd's store lives outside the jj op log, so
        a bd write sequenced before the restore would survive a rollback
        and violate all-or-nothing (FR-009). A failed restore is logged at
        error level (a rollback failure is more serious than an ordinary
        needs-review exit) and the reason is augmented, but never raised —
        one answer's rollback failing must not crash the run.

        When ``escalation_kind`` is given (conflict-resolution or
        semantic-dependents exhaustion), a human-triage bead is created via
        ``assumptions.ledger.create_reconcile_escalation`` — strictly after
        the restore above, per R8 — and its id both augments ``reason`` and
        lands on the returned :class:`AnswerOutcome.escalation_bead_id`.
        ``create_reconcile_escalation`` never raises (its own contract); a
        ``None`` return (bd-layer failure creating the bead) still allows
        this method to finish normally with ``escalation_bead_id=None`` —
        one escalation bead failing to be created must not crash the run
        or prevent the entry from being terminal-marked.
        """
        if restore_op_id is not None:
            try:
                restore_result = await jj_restore_operation(restore_op_id, cwd=cwd)
            except Exception as exc:  # noqa: BLE001 - rollback failure must not crash the run
                logger.error(
                    "reconcile_restore_operation_failed",
                    entry_id=answer.entry_id,
                    restore_op_id=restore_op_id,
                    error=str(exc),
                )
                reason = f"{reason} (rollback also failed: {exc})"
            else:
                if not restore_result.get("success", True):
                    restore_error = restore_result.get("error") or "restore reported failure"
                    logger.error(
                        "reconcile_restore_operation_failed",
                        entry_id=answer.entry_id,
                        restore_op_id=restore_op_id,
                        error=restore_error,
                    )
                    reason = f"{reason} (rollback also failed: {restore_error})"

        escalation_bead_id: str | None = None
        if escalation_kind is not None:
            escalation_entry = _answer_as_assumption_record(answer)
            escalation_bead_id = await create_reconcile_escalation(
                bead_client,
                entry=escalation_entry,
                remaining=tuple(escalation_remaining),
                kind=escalation_kind,
            )
            if escalation_bead_id:
                reason = f"{reason} (escalation bead: {escalation_bead_id})"
            else:
                logger.warning(
                    "reconcile_escalation_bead_creation_failed",
                    entry_id=answer.entry_id,
                    kind=escalation_kind,
                )
                reason = f"{reason} (escalation bead creation failed)"

        await mark_needs_interactive_review(bead_client, entry_id=answer.entry_id, reason=reason)
        outcome = AnswerOutcome(
            entry_id=answer.entry_id,
            status=outcome_status,
            stage_reached=stage_reached,
            reason=reason,
            escalation_bead_id=escalation_bead_id,
            gate_passed=gate_passed,
        )
        run_state = _replace_answer_state(
            run_state,
            answer.entry_id,
            stage=ReconcileStage.TERMINAL,
            terminal_status=outcome.status,
            reason=reason,
        )
        await save_run_state(run_state, cwd)
        await self.emit_step_completed(
            step_name, output={"status": outcome.status, "reason": reason}
        )
        return outcome, run_state
