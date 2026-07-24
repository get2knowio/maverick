"""Round-budgeted conflict-resolution loop (research R4/R5)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from maverick.agents.reconciler import ReconcilerAgent
from maverick.jj.client import JjClient
from maverick.library.actions.jj import jj_list_conflicts, jj_new_child, jj_squash_into
from maverick.logging import get_logger
from maverick.workflows.reconcile.models import ChangedAnswer

logger = get_logger(__name__)

__all__ = ["ConflictOutcome", "resolve_conflicts"]

#: Text jj prints ahead of the per-file conflict listing in ``jj status``
#: output (confirmed against jj 0.43 locally). Everything from the next
#: line up to the first blank line (or a "Hint:" line) is one conflicted
#: file path per line, e.g. ``f.txt    2-sided conflict``.
_CONFLICT_HEADER = "unresolved conflicts at these paths"


@dataclass(frozen=True, slots=True)
class ConflictOutcome:
    """Outcome of the round-budgeted conflict-resolution loop for one answer.

    This shape is deliberately richer than a bare bool so the (later,
    separately-serialized) workflow wiring task can distinguish *why* a
    loop did not resolve, for a precise escalation-bead description,
    without re-deriving it:

    - Agent-declared ``unresolvable`` (contract: non-empty ``unresolvable``
      is budget-terminating — the loop stops immediately rather than
      spending remaining rounds re-asking the same impossible question).
    - Budget exhaustion (conflicts still existed after every round was
      spent, but the agent never explicitly declined a file).
    - An action failure mid-loop (``jj_new_child``/``jj_squash_into``
      returned ``success=False``) — reported via ``error`` rather than
      raised, matching this module's "don't raise" contract.

    Attributes:
        resolved: True iff the ``conflicts()`` revset under
            ``descendants(target)`` was empty when the loop ended —
            checked before entering the loop and again after every round,
            so a zero-conflict answer never "spends" a round.
        rounds_used: Number of rounds actually spent resolving conflicts.
            ``0`` when there were no conflicts to begin with.
        unresolvable: Non-empty when an agent round declared files it
            could not resolve (contract: budget-terminating). Empty for
            both the resolved case and the budget-exhaustion case — those
            two share ``unresolvable == ()`` and are told apart by
            ``resolved`` plus ``rounds_used == max_rounds``.
        error: Set (non-None) when a jj action failed mid-loop; the loop
            stops and reports the failure rather than raising.
    """

    resolved: bool
    rounds_used: int
    unresolvable: tuple[str, ...] = ()
    error: str | None = None


async def resolve_conflicts(
    reconciler: ReconcilerAgent,
    answer: ChangedAnswer,
    *,
    cwd: Path,
    max_rounds: int,
) -> ConflictOutcome:
    """Resolve rebase conflicts under ``answer.target_change_id`` within a round budget.

    Sequence (research R5), run for up to ``max_rounds`` rounds:

    1. List conflicted descendants via
       ``jj_list_conflicts(revset_scope=f"descendants({target})")``. The
       underlying ``JjClient.log()`` call returns changes newest-first
       (confirmed against jj 0.43 locally, same finding
       ``detection.py``'s stack-ordering established) — this function
       reverses the tuple so conflicted changes are processed
       earliest-first. Resolving the earliest conflicted change first
       often clears descendants automatically via jj's conflict
       propagation, minimizing agent calls.
    2. This list is checked *before* the round loop even starts (a
       genuinely conflict-free answer returns immediately with
       ``rounds_used=0`` and zero agent calls) and again at the top of
       every subsequent round — never reusing a stale list from a prior
       round.
    3. For each conflicted change (earliest first): ``jj_new_child``
       positions ``@`` as an empty child of it, materializing conflict
       markers directly in the working-copy files (jj's real behavior —
       an empty child's working-copy content equals its parent's, markers
       included). This function reads which files are conflicted from
       ``JjClient.status()``'s raw output (the "unresolved conflicts at
       these paths" section — there is no dedicated conflicted-file-list
       client method) and then reads each file's on-disk content directly
       via :meth:`Path.read_text`, passing ``{path: content}`` to
       ``reconciler.resolve_conflicts(...)``.
    4. Non-empty ``payload.unresolvable`` stops the loop immediately
       (contract: budget-terminating; the round that produced it still
       counts against ``rounds_used``).
    5. Otherwise the resolution is folded via
       ``jj_squash_into(revision="@", into=conflicted_change_id)`` — jj
       propagates the resolution to downstream conflicts automatically.
    6. After ``max_rounds`` rounds, if conflicts still exist, the loop
       ends with ``resolved=False`` and no ``unresolvable`` (budget
       exhaustion, distinct from an agent-declared unresolvable set).

    Any ``jj_new_child``/``jj_squash_into`` failure returns immediately
    with ``error`` set rather than raising — callers own rollback via
    their own transaction snapshot (research R8), independent of what
    this function attempted.

    Args:
        reconciler: An opened ``ReconcilerAgent`` for this answer's
            session.
        answer: The changed answer whose target's descendants may carry
            rebase conflicts. Callers must have already resolved
            ``answer.target_change_id`` to a non-None value.
        cwd: Repository working directory.
        max_rounds: Round budget for this answer (typically
            ``config.reconcile.resolution_rounds``).

    Returns:
        :class:`ConflictOutcome`.

    Raises:
        AssertionError: If ``answer.target_change_id`` is ``None``.
    """
    assert answer.target_change_id is not None, (
        "resolve_conflicts requires a resolved target_change_id"
    )
    target = answer.target_change_id
    revset_scope = f"descendants({target})"

    conflicted = await _list_conflicts_earliest_first(revset_scope, cwd)
    if conflicted is None:
        return ConflictOutcome(
            resolved=False,
            rounds_used=0,
            error="jj_list_conflicts failed before the round loop started",
        )
    if not conflicted:
        return ConflictOutcome(resolved=True, rounds_used=0)

    for round_num in range(1, max_rounds + 1):
        for conflicted_change_id in conflicted:
            new_child_result = await jj_new_child(parent=conflicted_change_id, cwd=cwd)
            if not new_child_result["success"]:
                error = f"jj_new_child failed: {new_child_result['error']}"
                logger.debug(
                    "resolve_conflicts_new_child_failed",
                    entry_id=answer.entry_id,
                    conflicted_change_id=conflicted_change_id,
                    error=error,
                )
                return ConflictOutcome(
                    resolved=False,
                    rounds_used=round_num - 1,
                    error=error,
                )

            conflicted_files = await _read_conflicted_files(cwd)

            payload = await reconciler.resolve_conflicts(
                question=answer.question,
                adopted_answer=answer.adopted_answer,
                human_answer=answer.human_answer,
                conflicted_files=conflicted_files,
            )

            if payload.unresolvable:
                logger.debug(
                    "resolve_conflicts_unresolvable",
                    entry_id=answer.entry_id,
                    conflicted_change_id=conflicted_change_id,
                    unresolvable=payload.unresolvable,
                )
                return ConflictOutcome(
                    resolved=False,
                    rounds_used=round_num,
                    unresolvable=payload.unresolvable,
                )

            squash_result = await jj_squash_into(revision="@", into=conflicted_change_id, cwd=cwd)
            if not squash_result["success"]:
                error = f"jj_squash_into failed: {squash_result['error']}"
                logger.debug(
                    "resolve_conflicts_squash_failed",
                    entry_id=answer.entry_id,
                    conflicted_change_id=conflicted_change_id,
                    error=error,
                )
                return ConflictOutcome(
                    resolved=False,
                    rounds_used=round_num,
                    error=error,
                )

        conflicted = await _list_conflicts_earliest_first(revset_scope, cwd)
        if conflicted is None:
            return ConflictOutcome(
                resolved=False,
                rounds_used=round_num,
                error="jj_list_conflicts failed after resolving a round",
            )
        if not conflicted:
            return ConflictOutcome(resolved=True, rounds_used=round_num)

    # Budget exhausted: conflicts still exist, but the agent never
    # explicitly declared any file unresolvable.
    return ConflictOutcome(resolved=False, rounds_used=max_rounds)


async def _list_conflicts_earliest_first(
    revset_scope: str,
    cwd: Path,
) -> tuple[str, ...] | None:
    """Return conflicted change ids in earliest-first order, or ``None`` on failure."""
    result = await jj_list_conflicts(revset_scope=revset_scope, cwd=cwd)
    if not result["success"]:
        return None
    # jj_list_conflicts's underlying log() call returns newest-first
    # (same finding as detection.py's stack ordering); reverse for
    # earliest-first processing (research R5).
    return tuple(reversed(result["change_ids"]))


async def _read_conflicted_files(cwd: Path) -> dict[str, str]:
    """Read conflict-marker file contents for the working copy positioned at a conflict.

    ``jj_new_child`` has just positioned ``@`` as an empty child of a
    conflicted change, so the working-copy files on disk already contain
    literal conflict-marker text (jj's real materialization behavior —
    an empty child's content equals its parent's). There is no dedicated
    "list conflicted files" method on :class:`JjClient`, so this parses
    the conflicted paths out of ``jj status``'s raw output (the
    "unresolved conflicts at these paths" section) and reads each file
    directly from *cwd*.

    Args:
        cwd: Repository working directory, positioned at the conflicted
            child.

    Returns:
        ``{repo-relative path: file content}`` for every conflicted file
        jj reports. A file that disappears or fails to decode between
        the status call and the read is skipped rather than raising.
    """
    client = JjClient(cwd=cwd)
    status = await client.status()
    paths = _parse_conflicted_paths(status.output)

    conflicted_files: dict[str, str] = {}
    for path in paths:
        try:
            conflicted_files[path] = (cwd / path).read_text()
        except OSError as e:
            logger.debug("resolve_conflicts_read_failed", path=path, error=str(e))
    return conflicted_files


def _parse_conflicted_paths(status_output: str) -> tuple[str, ...]:
    """Extract conflicted file paths from ``jj status`` raw output.

    jj (0.43, confirmed locally) prints a block like::

        Warning: There are unresolved conflicts at these paths:
        f.txt    2-sided conflict
        other.py    2-sided conflict including 1 deletion
        Hint: To resolve the conflicts, ...

    This grabs every line after the header up to the first blank line or
    a line starting with ``Hint:``, taking the first whitespace-separated
    token on each as the repo-relative path.
    """
    lines = status_output.splitlines()
    header_index = next(
        (i for i, line in enumerate(lines) if _CONFLICT_HEADER in line),
        None,
    )
    if header_index is None:
        return ()

    paths: list[str] = []
    for line in lines[header_index + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("Hint:"):
            break
        path = stripped.split()[0]
        paths.append(path)
    return tuple(paths)
