"""Unit tests for the round-budgeted conflict-resolution loop (research R5).

Covers T024's required cases:
- round loop over ``jj_list_conflicts`` ground truth in topological
  (earliest-first) order
- resolution folded via child->squash into the conflicted change, exact
  sequence per conflicted change
- re-list between rounds (fresh results honored each round)
- budget exhaustion after N rounds
- non-empty ``unresolvable`` short-circuits remaining rounds
- zero conflicts at the very start -> resolved=True, rounds_used=0, no
  agent call at all
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from maverick.assumptions.models import Severity
from maverick.payloads import SubmitConflictResolutionPayload
from maverick.workflows.reconcile.conflicts import ConflictOutcome, resolve_conflicts
from maverick.workflows.reconcile.models import ChangedAnswer

CONFLICTS_MODULE = "maverick.workflows.reconcile.conflicts"


def _make_answer(*, target_change_id: str = "ktarget") -> ChangedAnswer:
    return ChangedAnswer(
        entry_id="bd-1",
        question="Should retries be capped at 3?",
        adopted_answer="No cap, retry forever.",
        human_answer="Cap retries at 3.",
        severity=Severity.MEDIUM,
        owner_spec="051-reconcile-changed-answers",
        stamped_change_ids=("ktarget",),
        target_change_id=target_change_id,
        stack_index=0,
    )


def _resolution_payload(
    *,
    resolved_files: tuple[str, ...] = ("f.txt",),
    unresolvable: tuple[str, ...] = (),
    notes: str = "",
) -> SubmitConflictResolutionPayload:
    return SubmitConflictResolutionPayload(
        resolved_files=resolved_files,
        unresolvable=unresolvable,
        notes=notes,
    )


def _make_reconciler(*payloads: SubmitConflictResolutionPayload) -> AsyncMock:
    reconciler = AsyncMock()
    if len(payloads) == 1:
        reconciler.resolve_conflicts = AsyncMock(return_value=payloads[0])
    else:
        reconciler.resolve_conflicts = AsyncMock(side_effect=list(payloads))
    return reconciler


class _StatusResult:
    def __init__(self, output: str) -> None:
        self.output = output


_STATUS_WITH_CONFLICT = _StatusResult(
    "The working copy has no changes.\n"
    "Working copy  (@) : yuvynypk 39b3eb47 (conflict) (empty)\n"
    "Parent commit (@-): nrlswmql 9e0d64ac (conflict) branchB\n"
    "Warning: There are unresolved conflicts at these paths:\n"
    "f.txt    2-sided conflict\n"
    "Hint: To resolve the conflicts, start by creating a commit on top of\n"
    "the conflicted commit:\n"
)


class _Patches:
    """Bundles the jj-action mocks + JjClient.status patch used below."""

    def __init__(
        self,
        *,
        list_conflicts_sequence: list[tuple[str, ...]],
        new_child_success: bool = True,
        new_child_error: str | None = None,
        squash_success: bool = True,
        squash_error: str | None = None,
        status_output: str = _STATUS_WITH_CONFLICT.output,
        file_contents: dict[str, str] | None = None,
    ) -> None:
        # jj_list_conflicts is called once before the loop, then once
        # more per round. Each call returns the next entry in the
        # sequence (topological/newest-first order, matching the real
        # client.log() behavior the module reverses).
        results = [
            {"success": True, "change_ids": ids, "error": None} for ids in list_conflicts_sequence
        ]
        self.jj_list_conflicts = AsyncMock(side_effect=results)

        self.jj_new_child = AsyncMock(
            return_value={
                "success": new_child_success,
                "change_id": "kchild" if new_child_success else None,
                "error": new_child_error,
            }
        )
        self.jj_squash_into = AsyncMock(
            return_value={"success": squash_success, "error": squash_error}
        )

        self.status_output = status_output
        self.file_contents = file_contents or {"f.txt": "<<<<<<<\nmarker\n>>>>>>>\n"}

    def make_client(self) -> AsyncMock:
        client = AsyncMock()
        client.status = AsyncMock(return_value=_StatusResult(self.status_output))
        return client


def _patch_all(p: _Patches, file_contents: dict[str, str]):
    mock_client = p.make_client()

    def _fake_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        # self is a Path like Path(cwd) / "f.txt"; use its name to look
        # up file content (tests use flat filenames).
        return file_contents[self.name]

    return (
        patch(f"{CONFLICTS_MODULE}.jj_list_conflicts", p.jj_list_conflicts),
        patch(f"{CONFLICTS_MODULE}.jj_new_child", p.jj_new_child),
        patch(f"{CONFLICTS_MODULE}.jj_squash_into", p.jj_squash_into),
        patch(f"{CONFLICTS_MODULE}.JjClient", return_value=mock_client),
        patch.object(Path, "read_text", _fake_read_text),
    )


async def _run_with_patches(
    p: _Patches,
    reconciler: AsyncMock,
    answer: ChangedAnswer,
    *,
    max_rounds: int,
):
    ctxs = _patch_all(p, p.file_contents)
    for ctx in ctxs:
        ctx.__enter__()
    try:
        return await resolve_conflicts(
            reconciler, answer, cwd=Path("/repo"), max_rounds=max_rounds
        )
    finally:
        for ctx in reversed(ctxs):
            ctx.__exit__(None, None, None)


@pytest.mark.asyncio
async def test_zero_conflicts_at_start_resolves_immediately_without_agent_call() -> None:
    """Empty conflict list before the loop starts -> resolved=True, rounds_used=0."""
    p = _Patches(list_conflicts_sequence=[()])
    reconciler = _make_reconciler(_resolution_payload())
    answer = _make_answer()

    result = await _run_with_patches(p, reconciler, answer, max_rounds=3)

    assert result == ConflictOutcome(resolved=True, rounds_used=0)
    p.jj_list_conflicts.assert_awaited_once_with(
        revset_scope="descendants(ktarget)", cwd=Path("/repo")
    )
    p.jj_new_child.assert_not_awaited()
    reconciler.resolve_conflicts.assert_not_awaited()
    p.jj_squash_into.assert_not_awaited()


@pytest.mark.asyncio
async def test_round_loop_processes_conflicts_earliest_first() -> None:
    """jj_list_conflicts returns newest-first (real client.log() order);
    the loop must process earliest-first (reversed) within the round."""
    # newest-first ground truth: "child" (deepest descendant) then "branchB"
    p = _Patches(
        list_conflicts_sequence=[("child", "branchB"), ()],
    )
    reconciler = _make_reconciler(_resolution_payload(), _resolution_payload())
    answer = _make_answer(target_change_id="base")

    result = await _run_with_patches(p, reconciler, answer, max_rounds=3)

    assert result == ConflictOutcome(resolved=True, rounds_used=1)
    # Both conflicted changes get processed within round 1 (the round
    # loop doesn't re-check mid-round), but in earliest-first order:
    # "branchB" before "child", the reverse of jj_list_conflicts's raw
    # (newest-first) ordering.
    new_child_calls = p.jj_new_child.await_args_list
    assert [c.kwargs["parent"] for c in new_child_calls] == ["branchB", "child"]
    squash_calls = p.jj_squash_into.await_args_list
    assert [c.kwargs["into"] for c in squash_calls] == ["branchB", "child"]
    assert reconciler.resolve_conflicts.await_count == 2


@pytest.mark.asyncio
async def test_relist_between_rounds_honors_fresh_results() -> None:
    """jj_list_conflicts is called once per round with fresh results."""
    p = _Patches(
        list_conflicts_sequence=[("branchB",), ("branchB",), ()],
    )
    reconciler = _make_reconciler(_resolution_payload(), _resolution_payload())
    answer = _make_answer(target_change_id="base")

    result = await _run_with_patches(p, reconciler, answer, max_rounds=5)

    assert result == ConflictOutcome(resolved=True, rounds_used=2)
    assert p.jj_list_conflicts.await_count == 3  # initial + 2 re-lists
    assert reconciler.resolve_conflicts.await_count == 2


@pytest.mark.asyncio
async def test_budget_exhaustion_after_n_rounds() -> None:
    """Conflicts never clear -> resolved=False, rounds_used=max_rounds, no unresolvable."""
    p = _Patches(
        list_conflicts_sequence=[("branchB",), ("branchB",), ("branchB",)],
    )
    reconciler = _make_reconciler(
        _resolution_payload(), _resolution_payload(), _resolution_payload()
    )
    answer = _make_answer(target_change_id="base")

    result = await _run_with_patches(p, reconciler, answer, max_rounds=2)

    assert result == ConflictOutcome(resolved=False, rounds_used=2, unresolvable=())
    assert p.jj_list_conflicts.await_count == 3  # initial + 2 rounds
    assert reconciler.resolve_conflicts.await_count == 2  # exactly 2 rounds spent


@pytest.mark.asyncio
async def test_unresolvable_short_circuits_remaining_rounds() -> None:
    """Non-empty unresolvable stops the loop immediately, does not spend further rounds."""
    p = _Patches(
        list_conflicts_sequence=[("branchB",)],
    )
    reconciler = _make_reconciler(
        _resolution_payload(unresolvable=("f.txt",)),
    )
    answer = _make_answer(target_change_id="base")

    result = await _run_with_patches(p, reconciler, answer, max_rounds=5)

    assert result == ConflictOutcome(resolved=False, rounds_used=1, unresolvable=("f.txt",))
    # Only the initial list + one round's worth of agent calls — no
    # re-list, no further rounds.
    assert p.jj_list_conflicts.await_count == 1
    assert reconciler.resolve_conflicts.await_count == 1
    p.jj_squash_into.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_child_failure_short_circuits() -> None:
    """A failed jj_new_child returns an error result without calling the agent."""
    p = _Patches(
        list_conflicts_sequence=[("branchB",)],
        new_child_success=False,
        new_child_error="no such revision",
    )
    reconciler = _make_reconciler(_resolution_payload())
    answer = _make_answer(target_change_id="base")

    result = await _run_with_patches(p, reconciler, answer, max_rounds=3)

    assert result.resolved is False
    assert result.rounds_used == 0
    assert result.error is not None
    assert "no such revision" in result.error
    reconciler.resolve_conflicts.assert_not_awaited()
    p.jj_squash_into.assert_not_awaited()


@pytest.mark.asyncio
async def test_squash_failure_returns_error() -> None:
    """A failed jj_squash_into stops the loop and reports the error."""
    p = _Patches(
        list_conflicts_sequence=[("branchB",)],
        squash_success=False,
        squash_error="conflict",
    )
    reconciler = _make_reconciler(_resolution_payload())
    answer = _make_answer(target_change_id="base")

    result = await _run_with_patches(p, reconciler, answer, max_rounds=3)

    assert result.resolved is False
    assert result.rounds_used == 1
    assert result.error is not None
    assert "conflict" in result.error


@pytest.mark.asyncio
async def test_conflicted_files_passed_to_agent() -> None:
    """The parsed conflicted file path + on-disk content reach the agent call."""
    p = _Patches(
        list_conflicts_sequence=[("branchB",), ()],
        status_output=_STATUS_WITH_CONFLICT.output,
        file_contents={"f.txt": "<<<<<<<\nmine\n=======\ntheirs\n>>>>>>>\n"},
    )
    reconciler = _make_reconciler(_resolution_payload())
    answer = _make_answer(target_change_id="base")

    await _run_with_patches(p, reconciler, answer, max_rounds=3)

    reconciler.resolve_conflicts.assert_awaited_once_with(
        question=answer.question,
        adopted_answer=answer.adopted_answer,
        human_answer=answer.human_answer,
        conflicted_files={"f.txt": "<<<<<<<\nmine\n=======\ntheirs\n>>>>>>>\n"},
    )


@pytest.mark.asyncio
async def test_list_conflicts_failure_before_loop() -> None:
    """jj_list_conflicts failing before the loop starts returns an error result."""
    reconciler = _make_reconciler(_resolution_payload())
    answer = _make_answer(target_change_id="base")

    with patch(
        f"{CONFLICTS_MODULE}.jj_list_conflicts",
        AsyncMock(return_value={"success": False, "change_ids": (), "error": "boom"}),
    ):
        result = await resolve_conflicts(reconciler, answer, cwd=Path("/repo"), max_rounds=3)

    assert result.resolved is False
    assert result.rounds_used == 0
    assert result.error is not None
    reconciler.resolve_conflicts.assert_not_awaited()
