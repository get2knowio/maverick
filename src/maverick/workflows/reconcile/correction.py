"""Correction mechanism: child -> agent delta -> squash-into/absorb (research R3)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from maverick.agents.reconciler import ReconcilerAgent
from maverick.jj.client import JjClient
from maverick.library.actions.jj import jj_absorb, jj_diff, jj_new_child, jj_squash_into
from maverick.logging import get_logger
from maverick.payloads import SubmitCorrectionPayload
from maverick.workflows.reconcile.models import ChangedAnswer

logger = get_logger(__name__)

__all__ = ["CorrectionResult", "apply_correction"]


@dataclass(frozen=True, slots=True)
class CorrectionResult:
    """Outcome of applying one correction for a changed answer (research R3).

    Attributes:
        applied: True when a real correction was folded into the target
            (via ``jj_squash_into``/``jj_absorb``), or the empty-delta
            edge case was legitimately reached. False on any failure
            (``jj_new_child`` failure, a payload/diff mismatch, or a
            failed fold) — ``error`` is set in that case.
        no_change_required: True for the empty-delta edge case — the
            correction agent found the target already reflects the new
            answer and made no edits, and the working-copy diff agreed
            (zero files changed).
        correction_diff: The child's diff (git format), captured *before*
            the fold, for the later semantic-dependents pass (T029).
            Empty string for the empty-delta case and for any failure
            path where the diff was never (successfully) captured.
        payload: The agent's ``SubmitCorrectionPayload``, or ``None``
            when ``jj_new_child`` failed before the agent was ever
            called.
        error: Set (non-None) whenever ``applied`` is False, describing
            which step failed and why. ``None`` on success.
    """

    applied: bool
    no_change_required: bool
    correction_diff: str
    payload: SubmitCorrectionPayload | None = None
    error: str | None = None


async def apply_correction(
    reconciler: ReconcilerAgent,
    answer: ChangedAnswer,
    *,
    cwd: Path,
) -> CorrectionResult:
    """Apply one correction for a changed answer (research R3).

    Sequence:

    1. ``jj_new_child(parent=answer.target_change_id)`` positions ``@``
       as an empty child of the target change. A failure here
       short-circuits before any agent call.
    2. ``reconciler.correct(...)`` — the agent edits files in *cwd*
       directly, given the target's own diff as context, and returns a
       typed ``SubmitCorrectionPayload``.
    3. ``JjClient.diff_stat(revision="@")`` cross-checks the agent's
       ``no_change_required`` claim against the actual delta
       (contracts/payloads.md "submit_correction"). Agreement on empty
       (``no_change_required=True`` and zero files changed) is a
       legitimate outcome — the child is left as-is (nothing to squash;
       squashing an empty revision is a no-op the caller should not
       attempt). Any other disagreement is a correctness failure, not a
       retry: the answer fails without touching history further.
    4. On a real (non-empty) delta: capture ``jj_diff(revision="@")``
       *before* folding, then fold via ``jj_squash_into`` (the default,
       deterministic-targeting path) unless the entry has multiple
       stamped change ids (``len(answer.stamped_change_ids) > 1``), in
       which case ``jj_absorb`` is used instead (research R3's
       blame-routed fallback for deltas spanning multiple stamps).

    Args:
        reconciler: An opened ``ReconcilerAgent`` for this answer's
            session (the caller owns open/close/rotate_session).
        answer: The changed answer being corrected. Callers must have
            already resolved ``answer.target_change_id`` to a non-None
            value — unlocatable targets are a detection-time
            ``needs-interactive-review`` outcome handled upstream, not
            here.
        cwd: Repository working directory.

    Returns:
        :class:`CorrectionResult`. Callers (the workflow's per-answer
        transaction, research R8) own rollback — on any failure here the
        repo is left with the failed mutation attempted; the workflow
        restores the pre-answer jj operation via ``jj_restore_operation``
        using its own snapshot, independent of what this function did.

    Raises:
        AssertionError: If ``answer.target_change_id`` is ``None``.
    """
    assert answer.target_change_id is not None, (
        "apply_correction requires a resolved target_change_id"
    )
    target = answer.target_change_id

    new_child_result = await jj_new_child(parent=target, cwd=cwd)
    if not new_child_result["success"]:
        error = f"jj_new_child failed: {new_child_result['error']}"
        logger.debug("apply_correction_new_child_failed", entry_id=answer.entry_id, error=error)
        return CorrectionResult(
            applied=False,
            no_change_required=False,
            correction_diff="",
            error=error,
        )

    target_diff_result = await jj_diff(revision=target, cwd=cwd)
    target_diff = target_diff_result["output"] if target_diff_result["success"] else ""

    payload = await reconciler.correct(
        question=answer.question,
        adopted_answer=answer.adopted_answer,
        human_answer=answer.human_answer,
        target_diff=target_diff,
    )

    client = JjClient(cwd=cwd)
    stat = await client.diff_stat(revision="@")
    files_changed = stat.files_changed
    is_empty = files_changed == 0

    if payload.no_change_required != is_empty:
        error = (
            "payload/diff mismatch: agent reported "
            f"no_change_required={payload.no_change_required} but "
            f"the working copy has files_changed={files_changed}"
        )
        logger.debug(
            "apply_correction_payload_mismatch",
            entry_id=answer.entry_id,
            no_change_required=payload.no_change_required,
            files_changed=files_changed,
        )
        return CorrectionResult(
            applied=False,
            no_change_required=payload.no_change_required,
            correction_diff="",
            payload=payload,
            error=error,
        )

    if payload.no_change_required:
        # Empty-delta agreement: nothing to fold. The child is left as
        # the new working copy — harmless (it's empty) and cheaper than
        # an abandon round-trip; the caller decides whether to tidy it.
        return CorrectionResult(
            applied=True,
            no_change_required=True,
            correction_diff="",
            payload=payload,
        )

    # Normal path: capture the correction diff BEFORE folding.
    diff_result = await jj_diff(revision="@", cwd=cwd)
    correction_diff = diff_result["output"] if diff_result["success"] else ""

    if len(answer.stamped_change_ids) > 1:
        fold_result = await jj_absorb(cwd=cwd)
        fold_step = "jj_absorb"
    else:
        fold_result = await jj_squash_into(revision="@", into=target, cwd=cwd)
        fold_step = "jj_squash_into"

    if not fold_result["success"]:
        error = f"{fold_step} failed: {fold_result['error']}"
        logger.debug("apply_correction_fold_failed", entry_id=answer.entry_id, error=error)
        return CorrectionResult(
            applied=False,
            no_change_required=False,
            correction_diff=correction_diff,
            payload=payload,
            error=error,
        )

    return CorrectionResult(
        applied=True,
        no_change_required=False,
        correction_diff=correction_diff,
        payload=payload,
    )
