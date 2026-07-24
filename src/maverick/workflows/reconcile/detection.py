"""Changed-answer detection and stack ordering (research R1/R2)."""

from __future__ import annotations

from pathlib import Path

from maverick.assumptions.ledger import answered_unreconciled_entries
from maverick.assumptions.models import KEY_ANSWER
from maverick.beads.client import BeadClient
from maverick.jj.client import JjClient
from maverick.workflows.reconcile.models import ChangedAnswer

__all__ = ["build_changed_answers", "resolve_target_against_current_stack"]

#: ``stack_index`` sentinel for entries whose target change is unlocatable
#: (empty ``stamped_change_ids``, or none of them resolve in ``::@``).
#: Such entries are never scheduled for mutation (data-model.md §2 —
#: ``target_change_id is None`` implies a terminal ``needs-interactive-
#: review`` outcome before any mutation), so any value larger than every
#: real stack position works; this is intentionally far past the
#: ``log(limit=1000)`` ceiling so it never collides with a real index.
_UNLOCATABLE_STACK_INDEX = 1_000_000


async def build_changed_answers(client: BeadClient, *, cwd: Path) -> tuple[ChangedAnswer, ...]:
    """Build the changed-answer worklist for this reconcile run.

    Detection (research R1) is delegated entirely to
    :func:`maverick.assumptions.ledger.answered_unreconciled_entries` — this
    function trusts its output and does not re-filter. Its own job is
    purely the stack-position / correction-target resolution from research
    R2:

    1. Query :func:`answered_unreconciled_entries`. If there are no
       candidates, return ``()`` immediately without touching jj at all —
       the zero-model-call, zero-jj-call fast path.
    2. Otherwise, run exactly one ``jj log -r "::@"`` (via
       :meth:`JjClient.log`) to capture the full ancestor stack of the
       working copy, and index every change id by its position with 0 =
       earliest (oldest). ``JjClient.log`` returns changes newest-first
       (``@`` first, root last, confirmed against jj 0.43 locally) so the
       index is built over the *reversed* list.
    3. For each candidate record, resolve ``target_change_id`` as the
       earliest-in-stack id among ``record.change_ids`` that still exists
       in the index (research R2 — "earliest stamped change that still
       exists"); later stamps and stamps that no longer resolve (rewritten
       out of the stack) are ignored for targeting purposes. If none
       resolve (including the empty-``change_ids`` case),
       ``target_change_id`` is ``None`` and ``stack_index`` is set to the
       ``_UNLOCATABLE_STACK_INDEX`` sentinel.
    4. ``human_answer`` isn't carried by ``AssumptionRecord`` itself, so it
       is fetched directly via ``client.show(bead_id)`` and the
       ``assumption_answer`` (``KEY_ANSWER``) state key.

    The returned tuple is unordered with respect to ``stack_index`` — a
    later task sorts by it before batch processing (data-model.md §2 sort
    key note).

    Args:
        client: Bead client used for both the ledger query and per-entry
            state fetches.
        cwd: Repository working directory the jj stack is read from.

    Returns:
        One :class:`ChangedAnswer` per detected candidate.
    """
    records = await answered_unreconciled_entries(client)
    if not records:
        return ()

    jj_client = JjClient(cwd=cwd)
    log_result = await jj_client.log(revset="::@", limit=1000)
    # jj log is newest-first (``@`` first, root last); reverse so index 0
    # is the earliest (oldest) change in the stack.
    stack_index_by_change_id = {
        change.change_id: index for index, change in enumerate(reversed(log_result.changes))
    }

    changed_answers: list[ChangedAnswer] = []
    for record in records:
        target_change_id, stack_index = _resolve_target(
            record.change_ids, stack_index_by_change_id
        )
        details = await client.show(record.bead_id)
        human_answer = (details.state or {}).get(KEY_ANSWER, "")
        changed_answers.append(
            ChangedAnswer(
                entry_id=record.bead_id,
                question=record.question,
                adopted_answer=record.adopted_answer,
                human_answer=human_answer,
                severity=record.severity,
                owner_spec=record.owner_spec,
                stamped_change_ids=record.change_ids,
                target_change_id=target_change_id,
                stack_index=stack_index,
            )
        )
    return tuple(changed_answers)


async def resolve_target_against_current_stack(
    stamped_change_ids: tuple[str, ...],
    *,
    cwd: Path,
) -> tuple[str | None, int]:
    """Re-resolve a target against a FRESH snapshot (research R2/R13, T033).

    :func:`build_changed_answers` resolves every candidate's
    ``target_change_id``/``stack_index`` against a single ``::@`` snapshot
    taken once at the start of a run — correct there, since at that point
    ``@`` genuinely sits at the tip of the branch every changed-answer
    target descends from. Within a batch run
    (``workflows/reconcile/workflow.py``), correcting one answer folds a
    delta into its target via ``jj squash --into`` (:func:`apply_correction
    <maverick.workflows.reconcile.correction.apply_correction>`), which
    auto-rebases every descendant onto the corrected target in the same jj
    operation — but jj also recreates the working copy as a NEW EMPTY CHILD
    OF THAT SAME TARGET, i.e. a *sibling* of the just-rebased descendants,
    not an ancestor of them. Confirmed empirically against jj 0.43: after
    squashing a correction into ``A`` in a stack ``base <- A <- B <- C``,
    ``jj log -r '::@'`` shows only ``base``/``A``/``@`` — ``B``/``C`` are
    rebased and still exist, but are no longer reachable from ``@`` at all.
    Re-resolving a later answer's target (which may be one of those
    now-sibling descendants) against ``::@`` would therefore wrongly report
    it unlocatable. This function queries ``all()`` instead — every commit
    in the repo, existence-only, unanchored to wherever ``@`` currently
    happens to sit — so a genuinely still-existing target (mutable or
    otherwise; mutability is a separate, later guard) is never lost to this
    quirk of jj's post-squash working-copy placement.

    Change ids themselves are stable across rebase (research R13), so the
    SAME stamped ids are re-checked here — this just re-runs the
    stack-position half of the resolution (:func:`_resolve_target` /
    :func:`_find_stack_match`) against a fresh snapshot rather than the
    stale one computed before any repair happened.

    This is deliberately a thin wrapper, not a re-run of full detection: it
    does not re-query the ledger (``answered_unreconciled_entries``) at
    all — only the jj-side half of resolution, which is the only half that
    can have changed mid-run.

    Args:
        stamped_change_ids: The same ``ChangedAnswer.stamped_change_ids``
            already computed for this answer — unchanged across a run
            (append-only stamps aren't touched by reconcile itself).
        cwd: Repository working directory the jj stack is read from.

    Returns:
        ``(target_change_id, stack_index)`` — same shape as
        :func:`_resolve_target`; ``(None, _UNLOCATABLE_STACK_INDEX)`` when
        nothing resolves.
    """
    jj_client = JjClient(cwd=cwd)
    log_result = await jj_client.log(revset="all()", limit=1000)
    # Same reversal as build_changed_answers: jj log is newest-first, so
    # index 0 = earliest (oldest) change across the whole repo.
    stack_index_by_change_id = {
        change.change_id: index for index, change in enumerate(reversed(log_result.changes))
    }
    return _resolve_target(stamped_change_ids, stack_index_by_change_id)


def _resolve_target(
    stamped_change_ids: tuple[str, ...],
    stack_index_by_change_id: dict[str, int],
) -> tuple[str | None, int]:
    """Resolve the earliest-in-stack, still-existing stamped change id.

    Returns ``(target_change_id, stack_index)``; ``(None,
    _UNLOCATABLE_STACK_INDEX)`` when no stamped id resolves (research
    R2/FR-015).
    """
    resolvable = [
        match
        for change_id in stamped_change_ids
        if (match := _find_stack_match(change_id, stack_index_by_change_id)) is not None
    ]
    if not resolvable:
        return None, _UNLOCATABLE_STACK_INDEX
    index, change_id = min(resolvable)
    return change_id, index


def _find_stack_match(
    change_id: str,
    stack_index_by_change_id: dict[str, int],
) -> tuple[int, str] | None:
    """Match *change_id* against the stack index, tolerating short/full-id mismatches.

    ``JjClient.log()`` always renders change ids via ``change_id.short()``
    (client.py's ``log()`` template) — the minimal prefix that disambiguates
    *at render time*. ``JjClient.commit()``/``.new()`` — the source of every
    stamped id via ``assumptions.ledger.stamp_change_id`` — deliberately
    resolve via the unabbreviated ``change_id`` template instead
    (client.py's ``_resolve_change_id``): a short id is only guaranteed
    unique at render time and would be unsafe to persist as a permanent bd
    state value, so stamping always stores the full form.

    A jj short change id is always a literal prefix of its full form
    (confirmed against jj 0.43 locally: ``tyktvonpqypp`` is a prefix of
    ``tyktvonpqyppqtlwnxxmxvvrnlsqzwlt``) — so a real stamped (full) id
    never exact-matches this stack index's (short) keys, and matching must
    be prefix-aware in both directions to work regardless of which form
    either side happens to carry.

    Returns ``(stack_index, change_id)`` — *change_id* echoed back
    unchanged (the caller resolves ``target_change_id`` to the stamped
    form, not the index's short key) — or ``None`` if no entry matches.
    """
    if change_id in stack_index_by_change_id:
        return stack_index_by_change_id[change_id], change_id
    for log_change_id, index in stack_index_by_change_id.items():
        if change_id.startswith(log_change_id) or log_change_id.startswith(change_id):
            return index, change_id
    return None
