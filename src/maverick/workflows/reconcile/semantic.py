"""Semantic-dependents pass: diff-vs-diff analysis fan-out (research R6).

Standalone module — **not** wired into ``workflow.py`` yet (that's T030,
serialized after this task). Exposes :func:`run_semantic_pass`, which the
workflow will call between the conflicts stage and the gate stage.

Algorithm (research R6):

1. Enumerate the target's mutable descendants once via
   ``JjClient.log(revset=f"descendants({target}) & mutable() & ~{target}")``
   — the same direct-``JjClient`` pattern ``detection.py`` uses for ``::@``,
   rather than the ``jj_log`` action wrapper (which only returns display
   text, not structured :class:`~maverick.jj.models.JjChangeInfo` entries).
   jj returns changes newest-first; this pass never depends on descendant
   order (each round analyzes a *batch*, not a sequence), so the raw jj
   order is kept as-is and not reversed like ``detection.py`` does for its
   stack index.
2. Zero descendants short-circuits before any agent call.
3. Rounds (budget ``max_rounds``, from ``ReconcileConfig.semantic_rounds``):
   round 1 analyzes every descendant; each subsequent round re-analyzes
   *only* the descendants flagged ``dependent=True`` in the previous round
   (verifying the fix actually resolved the dependency). A round with zero
   flagged findings ends the pass successfully. Reaching ``max_rounds``
   with findings still flagged is budget exhaustion.
4. Per round: capture each to-analyze descendant's diff via the same
   ``jj_diff`` action ``correction.py`` uses, call
   ``SemanticDependentsAgent.analyze(...)``, then cross-check the
   contract's ids-subset rule ourselves (the payload validator only
   enforces per-finding shape, not fleet membership, per
   contracts/payloads.md): findings whose ``change_id`` was not in this
   round's supplied set are dropped (logged as a warning — an
   unexpected/hallucinated id); supplied ids with no matching finding are
   treated as ``dependent=False`` (contract's "missing ids treated as
   dependent=false").
5. Every valid ``dependent=True`` finding gets its fix applied via the
   *same* child -> agent -> verify -> squash-into mechanism
   ``correction.py`` already implements for the primary correction —
   **reuse option (i)** from the task brief: build a modified
   ``ChangedAnswer`` via ``dataclasses.replace(answer,
   target_change_id=finding.change_id, stamped_change_ids=(finding.change_id,))``
   and call ``apply_correction(reconciler, modified_answer, cwd=cwd)``
   unchanged. ``stamped_change_ids`` is also overridden (not just
   ``target_change_id``) because ``apply_correction`` reads its length to
   choose the fold path (``jj_absorb`` for ``len > 1``, ``jj_squash_into``
   otherwise, research R3) — a semantic fix targets exactly one specific
   descendant change, never a multi-stamp delta, so pinning it to a
   single-element tuple forces the deterministic squash-into path
   regardless of how many stamps the *original* entry carried.

   Chosen over option (ii) (a local variant calling
   ``ReconcilerAgent.correct`` directly with ``fix_instructions`` folded
   in) because it requires zero changes to already-tested
   ``correction.py``/``ReconcilerAgent`` surfaces and
   ``ReconcilerAgent.correct``'s only context slots are ``{question,
   adopted_answer, human_answer, target_diff}`` — ``target_diff`` here is
   the flagged descendant's *own* diff, which is meaningful judgment
   context (what the descendant currently does) even without the semantic
   reviewer's specific ``fix_instructions`` prose. **Known limitation for
   T030**: the semantic reviewer's ``reason``/``fix_instructions`` text is
   therefore *not* threaded into the fix prompt — only the descendant's
   diff and the original question/answer pair are. If fix quality proves
   insufficient in practice, promoting to option (ii) (a
   ``fix_instructions``-aware prompt) is the documented next step.
6. Any ``apply_correction`` failure (``result.applied is False``) halts
   the pass immediately with ``completed=False`` and the failure's
   ``error`` message — the caller (T030) owns rollback via the same
   per-answer transaction boundary ``correction.py``'s failures already
   flow through. Agent-level exceptions from ``analyze``/``correct`` are
   *not* caught here, matching ``correction.py``'s convention of letting
   them propagate to the workflow's snapshot/restore boundary (research
   R8) rather than swallowing them at the stage level.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from maverick.jj.client import JjClient
from maverick.jj.errors import JjError
from maverick.library.actions.jj import jj_diff
from maverick.logging import get_logger
from maverick.workflows.reconcile.correction import CorrectionResult, apply_correction
from maverick.workflows.reconcile.models import ChangedAnswer

if TYPE_CHECKING:
    from pathlib import Path

    from maverick.agents.reconciler import ReconcilerAgent
    from maverick.agents.semantic_reviewer import SemanticDependentsAgent

logger = get_logger(__name__)

__all__ = ["SemanticOutcome", "run_semantic_pass"]


@dataclass(frozen=True, slots=True)
class SemanticOutcome:
    """Outcome of the semantic-dependents pass for one changed answer.

    T030 (wiring this into ``workflow.py``) consumes this shape directly,
    so it is documented here as the stable contract between this module
    and the workflow:

    Attributes:
        completed: True when the pass finished within ``max_rounds`` —
            either because there were no descendants to analyze, or
            because a round's analysis found nothing left flagged
            (including the empty-descendants fast path, round 0). False
            on budget exhaustion (still-flagged findings after the final
            round) or on any action failure (e.g. ``apply_correction``
            failing to fold a fix) — check ``error`` to distinguish the
            two: exhaustion leaves ``error=None``, a failure sets it.
        rounds_used: How many analyze-rounds actually ran. ``0`` for the
            zero-descendants fast path. Capped at ``max_rounds``.
        fixed_descendants: Change ids that had a fix successfully applied
            via ``apply_correction``, across all rounds, in application
            order. May be non-empty even when ``completed=False`` (partial
            progress before exhaustion or failure) — T030 decides whether
            partial fixes survive a rollback (they do not: rollback is
            all-or-nothing per research R8, this field is for
            escalation-bead reporting).
        error: Set (non-None) only when an action failed outright (jj
            descendant enumeration, or an ``apply_correction`` fold).
            ``None`` for both success and budget-exhaustion outcomes.
    """

    completed: bool
    rounds_used: int
    fixed_descendants: tuple[str, ...] = ()
    error: str | None = None


async def run_semantic_pass(
    reconciler: ReconcilerAgent,
    semantic: SemanticDependentsAgent,
    answer: ChangedAnswer,
    correction_diff: str,
    *,
    cwd: Path,
    max_rounds: int,
) -> SemanticOutcome:
    """Run the semantic-dependents pass for one changed answer (research R6).

    Args:
        reconciler: An opened ``ReconcilerAgent`` for this answer's session
            (the caller owns open/close/rotate_session, same contract as
            ``apply_correction``).
        semantic: An opened ``SemanticDependentsAgent`` for this answer's
            session.
        answer: The changed answer whose target's descendants are being
            analyzed. ``answer.target_change_id`` must already be
            resolved (non-None) — unlocatable targets are a detection-time
            outcome handled upstream, not here.
        correction_diff: The diff that was folded into ``target_change_id``
            by the primary correction (``apply_correction``'s
            ``CorrectionResult.correction_diff``), given to the semantic
            agent as context for what changed.
        cwd: Repository working directory.
        max_rounds: Round budget for this pass (``ReconcileConfig.semantic_rounds``).

    Returns:
        :class:`SemanticOutcome`.

    Raises:
        AssertionError: If ``answer.target_change_id`` is ``None``.
    """
    assert answer.target_change_id is not None, (
        "run_semantic_pass requires a resolved target_change_id"
    )
    target = answer.target_change_id

    try:
        jj_client = JjClient(cwd=cwd)
        log_result = await jj_client.log(
            revset=f"descendants({target}) & mutable() & ~{target}",
            limit=1000,
        )
    except (JjError, OSError) as exc:
        error = f"descendant enumeration failed: {exc}"
        logger.debug("run_semantic_pass_enumeration_failed", entry_id=answer.entry_id, error=error)
        return SemanticOutcome(completed=False, rounds_used=0, error=error)

    all_descendant_ids = tuple(change.change_id for change in log_result.changes)
    if not all_descendant_ids:
        return SemanticOutcome(completed=True, rounds_used=0)

    fixed_descendants: list[str] = []
    to_analyze = all_descendant_ids

    for round_num in range(1, max_rounds + 1):
        descendant_diffs = await _capture_diffs(to_analyze, cwd=cwd)

        payload = await semantic.analyze(
            question=answer.question,
            adopted_answer=answer.adopted_answer,
            human_answer=answer.human_answer,
            correction_diff=correction_diff,
            descendants=descendant_diffs,
        )

        supplied_ids = set(to_analyze)
        flagged: list[str] = []
        for finding in payload.findings:
            if finding.change_id not in supplied_ids:
                logger.warning(
                    "run_semantic_pass_unexpected_finding_id",
                    entry_id=answer.entry_id,
                    change_id=finding.change_id,
                    supplied_ids=tuple(supplied_ids),
                )
                continue
            if finding.dependent:
                flagged.append(finding.change_id)

        if not flagged:
            return SemanticOutcome(
                completed=True,
                rounds_used=round_num,
                fixed_descendants=tuple(fixed_descendants),
            )

        for change_id in flagged:
            fix_result = await _apply_fix(reconciler, answer, change_id, cwd=cwd)
            if not fix_result.applied:
                return SemanticOutcome(
                    completed=False,
                    rounds_used=round_num,
                    fixed_descendants=tuple(fixed_descendants),
                    error=fix_result.error,
                )
            if change_id not in fixed_descendants:
                fixed_descendants.append(change_id)

        to_analyze = tuple(flagged)

    return SemanticOutcome(
        completed=False,
        rounds_used=max_rounds,
        fixed_descendants=tuple(fixed_descendants),
    )


async def _capture_diffs(
    change_ids: tuple[str, ...],
    *,
    cwd: Path,
) -> tuple[tuple[str, str], ...]:
    """Capture ``(change_id, diff)`` pairs for a batch of descendants.

    Matches ``correction.py``'s exact diff-capture mechanism (the
    ``jj_diff`` action wrapper). A capture failure for one descendant
    degrades to an empty diff string for that descendant (logged) rather
    than aborting the whole batch — mirrors ``apply_correction``'s
    treatment of its own pre-agent target-diff capture.
    """
    pairs: list[tuple[str, str]] = []
    for change_id in change_ids:
        diff_result = await jj_diff(revision=change_id, cwd=cwd)
        if diff_result["success"]:
            diff_text = diff_result["output"]
        else:
            diff_text = ""
            logger.debug(
                "run_semantic_pass_diff_capture_failed",
                change_id=change_id,
                error=diff_result["error"],
            )
        pairs.append((change_id, diff_text))
    return tuple(pairs)


async def _apply_fix(
    reconciler: ReconcilerAgent,
    answer: ChangedAnswer,
    change_id: str,
    *,
    cwd: Path,
) -> CorrectionResult:
    """Apply one flagged descendant's fix via the correction mechanism.

    Reuse option (i) (see module docstring): retarget a copy of *answer*
    at the flagged descendant and hand it to ``apply_correction``
    unchanged. ``stamped_change_ids`` is pinned to a single-element tuple
    so the fold-path selection inside ``apply_correction`` always takes
    the deterministic ``jj_squash_into`` branch for this descendant,
    independent of how many stamps the original entry carried.
    """
    descendant_answer = replace(
        answer,
        target_change_id=change_id,
        stamped_change_ids=(change_id,),
    )
    return await apply_correction(reconciler, descendant_answer, cwd=cwd)
