"""Tests for changed-answer detection and stack ordering (research R1/R2)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.assumptions.models import KEY_ANSWER, AssumptionRecord, Severity
from maverick.beads.client import BeadClient
from maverick.beads.models import BeadDetails
from maverick.jj.client import JjClient
from maverick.jj.models import JjChangeInfo, JjLogResult
from maverick.workflows.reconcile.detection import (
    _UNLOCATABLE_STACK_INDEX,
    build_changed_answers,
    resolve_target_against_current_stack,
)


def _client() -> BeadClient:
    return BeadClient(cwd=Path("/tmp/repo"))


def _record(
    bead_id: str = "dea-1",
    *,
    change_ids: tuple[str, ...] = ("c1",),
    severity: Severity = Severity.MEDIUM,
    owner_spec: str = "051-reconcile-changed-answers",
    question: str = "Should we use X?",
    adopted_answer: str = "Original answer.",
) -> AssumptionRecord:
    return AssumptionRecord(
        bead_id=bead_id,
        question=question,
        adopted_answer=adopted_answer,
        alternatives=(),
        severity=severity,
        severity_defaulted=False,
        status="answered",
        owner_spec=owner_spec,
        source_bead="src-1",
        change_ids=change_ids,
        is_legacy=False,
    )


def _details(bead_id: str, *, answer_text: str = "A brand new answer.") -> BeadDetails:
    return BeadDetails(
        id=bead_id,
        title=f"Assumption: {bead_id}",
        description="## Question\n\nQ?\n\n## Adopted Answer\n\nOriginal answer.\n\n",
        bead_type="task",
        status="closed",
        labels=["assumption"],
        state={KEY_ANSWER: answer_text},
    )


def _change(change_id: str) -> JjChangeInfo:
    return JjChangeInfo(change_id=change_id, commit_id=f"{change_id}full", description=change_id)


#: Stack newest-first as JjClient.log actually returns it (c3 = @, c1 =
#: oldest/earliest). Reversed by detection.py to index c1=0, c2=1, c3=2.
_NEWEST_FIRST_STACK = JjLogResult(
    success=True,
    output="",
    changes=(_change("c3"), _change("c2"), _change("c1")),
)


def _patch_ledger(records: tuple[AssumptionRecord, ...]) -> AsyncMock:
    return patch(
        "maverick.workflows.reconcile.detection.answered_unreconciled_entries",
        new=AsyncMock(return_value=records),
    )


class TestBuildChangedAnswers:
    @pytest.mark.asyncio
    async def test_empty_candidates_skips_jj_log(self) -> None:
        """Zero-model-call fast path: no candidates -> no jj log call at all."""
        log_mock = AsyncMock(side_effect=AssertionError("jj log should not be called"))
        with (
            _patch_ledger(()),
            patch.object(JjClient, "log", new=log_mock),
        ):
            result = await build_changed_answers(_client(), cwd=Path("/tmp/repo"))

        assert result == ()
        log_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_trusts_ledger_changed_vs_unchanged_filtering(self) -> None:
        """detection.py doesn't re-filter; it trusts answered_unreconciled_entries."""
        record = _record("dea-1", change_ids=("c1",))

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _details(bead_id, answer_text="A brand new answer.")

        with (
            _patch_ledger((record,)),
            patch.object(JjClient, "log", new=AsyncMock(return_value=_NEWEST_FIRST_STACK)),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await build_changed_answers(_client(), cwd=Path("/tmp/repo"))

        assert len(result) == 1
        assert result[0].entry_id == "dea-1"
        assert result[0].human_answer == "A brand new answer."
        assert result[0].adopted_answer == "Original answer."

    @pytest.mark.asyncio
    async def test_multiple_stamped_ids_earliest_existing_is_target(self) -> None:
        """Among multiple resolvable stamps, the earliest-in-stack wins."""
        record = _record("dea-1", change_ids=("c3", "c1", "c2"))

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _details(bead_id)

        with (
            _patch_ledger((record,)),
            patch.object(JjClient, "log", new=AsyncMock(return_value=_NEWEST_FIRST_STACK)),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await build_changed_answers(_client(), cwd=Path("/tmp/repo"))

        assert result[0].target_change_id == "c1"
        assert result[0].stack_index == 0

    @pytest.mark.asyncio
    async def test_stamped_id_no_longer_in_stack_is_skipped_for_targeting(self) -> None:
        """A stamp that no longer resolves in the repo is ignored in favor of one that does."""
        # "c0" was abandoned/rewritten out of the stack entirely; "c2" still
        # exists and must be chosen even though c0 would have been earlier.
        record = _record("dea-1", change_ids=("c0", "c2"))

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _details(bead_id)

        with (
            _patch_ledger((record,)),
            patch.object(JjClient, "log", new=AsyncMock(return_value=_NEWEST_FIRST_STACK)),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await build_changed_answers(_client(), cwd=Path("/tmp/repo"))

        assert result[0].target_change_id == "c2"
        assert result[0].stack_index == 1

    @pytest.mark.asyncio
    async def test_unlocatable_target_when_no_stamp_resolves(self) -> None:
        """None of the stamped ids exist in the repo -> target_change_id is None."""
        record = _record("dea-1", change_ids=("cZ", "cY"))

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _details(bead_id)

        with (
            _patch_ledger((record,)),
            patch.object(JjClient, "log", new=AsyncMock(return_value=_NEWEST_FIRST_STACK)),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await build_changed_answers(_client(), cwd=Path("/tmp/repo"))

        assert result[0].target_change_id is None
        assert result[0].stack_index > len(_NEWEST_FIRST_STACK.changes)

    @pytest.mark.asyncio
    async def test_unlocatable_target_when_change_ids_empty(self) -> None:
        """Empty stamped_change_ids -> target_change_id is None, same as unresolvable."""
        record = _record("dea-1", change_ids=())

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _details(bead_id)

        with (
            _patch_ledger((record,)),
            patch.object(JjClient, "log", new=AsyncMock(return_value=_NEWEST_FIRST_STACK)),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await build_changed_answers(_client(), cwd=Path("/tmp/repo"))

        assert result[0].stamped_change_ids == ()
        assert result[0].target_change_id is None

    @pytest.mark.asyncio
    async def test_human_answer_fetched_from_bead_state(self) -> None:
        """human_answer comes from client.show(entry_id)'s assumption_answer state."""
        record = _record("dea-1", change_ids=("c1",))

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            assert bead_id == "dea-1"
            return _details(bead_id, answer_text="The specific human-provided answer.")

        with (
            _patch_ledger((record,)),
            patch.object(JjClient, "log", new=AsyncMock(return_value=_NEWEST_FIRST_STACK)),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await build_changed_answers(_client(), cwd=Path("/tmp/repo"))

        assert result[0].human_answer == "The specific human-provided answer."

    @pytest.mark.asyncio
    async def test_severity_and_owner_spec_and_stamped_ids_carried_through(self) -> None:
        record = _record(
            "dea-1",
            change_ids=("c1", "c2"),
            severity=Severity.HIGH,
            owner_spec="052-some-other-spec",
            question="Which auth provider?",
            adopted_answer="OAuth",
        )

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _details(bead_id)

        with (
            _patch_ledger((record,)),
            patch.object(JjClient, "log", new=AsyncMock(return_value=_NEWEST_FIRST_STACK)),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await build_changed_answers(_client(), cwd=Path("/tmp/repo"))

        answer = result[0]
        assert answer.severity is Severity.HIGH
        assert answer.owner_spec == "052-some-other-spec"
        assert answer.question == "Which auth provider?"
        assert answer.adopted_answer == "OAuth"
        assert answer.stamped_change_ids == ("c1", "c2")

    @pytest.mark.asyncio
    async def test_full_stamped_id_resolves_against_short_log_id(self) -> None:
        """Regression: stamp_change_id stores the FULL change id (JjClient.commit()/
        .new() resolve unabbreviated), but JjClient.log() always renders the
        SHORT form (change_id.short()) — a real short id is a literal prefix
        of its full form, never an exact string match. Detection must resolve
        this via prefix matching or every real stamped id would be reported
        unlocatable (target_change_id=None) despite genuinely existing.
        """
        full_id = "tyktvonpqyppqtlwnxxmxvvrnlsqzwlt"
        short_id = "tyktvonpqypp"
        assert full_id.startswith(short_id)  # sanity: mirrors real jj behavior

        record = _record("dea-1", change_ids=(full_id,))
        stack = JjLogResult(
            success=True,
            output="",
            changes=(_change("c3"), _change(short_id)),
        )

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _details(bead_id)

        with (
            _patch_ledger((record,)),
            patch.object(JjClient, "log", new=AsyncMock(return_value=stack)),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await build_changed_answers(_client(), cwd=Path("/tmp/repo"))

        # The stamped (full) id is echoed back as target_change_id, resolved
        # against the short-id stack position — not left unlocatable.
        assert result[0].target_change_id == full_id
        assert result[0].stack_index == 0

    @pytest.mark.asyncio
    async def test_calls_jj_log_exactly_once_for_multiple_candidates(self) -> None:
        """One jj log call serves all candidates in a run, not one per entry."""
        records = (
            _record("dea-1", change_ids=("c1",)),
            _record("dea-2", change_ids=("c2",)),
        )
        log_mock = AsyncMock(return_value=_NEWEST_FIRST_STACK)

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _details(bead_id)

        with (
            _patch_ledger(records),
            patch.object(JjClient, "log", new=log_mock),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await build_changed_answers(_client(), cwd=Path("/tmp/repo"))

        assert len(result) == 2
        # ``all()`` not ``::@``: a stamped target need not be an ancestor of
        # the working copy (e.g. after a mid-stack ``jj edit``), so detection
        # indexes the whole repo — consistent with the mid-run re-resolver.
        log_mock.assert_called_once_with(revset="all()", limit=1000)


class TestResolveTargetAgainstCurrentStack:
    """T032/T033 (US5, research R2/R13): the standalone re-resolution entry
    point ``workflow.py``'s per-answer loop calls between processing
    subsequent answers in a batch, mid-run. It reuses the exact same
    ``_resolve_target``/``_find_stack_match`` matching logic as
    ``build_changed_answers`` — these tests mirror that existing coverage
    but drive it through the new public function, against a FRESH mocked
    ``JjClient.log`` call rather than one shared across a whole run.
    """

    @pytest.mark.asyncio
    async def test_resolves_stamped_id_against_a_fresh_jj_log_call(self) -> None:
        log_mock = AsyncMock(return_value=_NEWEST_FIRST_STACK)
        with patch.object(JjClient, "log", new=log_mock):
            target_change_id, stack_index = await resolve_target_against_current_stack(
                ("c2",), cwd=Path("/tmp/repo")
            )

        assert target_change_id == "c2"
        assert stack_index == 1
        log_mock.assert_called_once_with(revset="all()", limit=1000)

    @pytest.mark.asyncio
    async def test_earliest_existing_stamp_wins_same_as_initial_resolution(self) -> None:
        with patch.object(JjClient, "log", new=AsyncMock(return_value=_NEWEST_FIRST_STACK)):
            target_change_id, stack_index = await resolve_target_against_current_stack(
                ("c3", "c1", "c2"), cwd=Path("/tmp/repo")
            )

        assert target_change_id == "c1"
        assert stack_index == 0

    @pytest.mark.asyncio
    async def test_returns_none_and_sentinel_when_nothing_resolves(self) -> None:
        with patch.object(JjClient, "log", new=AsyncMock(return_value=_NEWEST_FIRST_STACK)):
            target_change_id, stack_index = await resolve_target_against_current_stack(
                ("cZ", "cY"), cwd=Path("/tmp/repo")
            )

        assert target_change_id is None
        assert stack_index == _UNLOCATABLE_STACK_INDEX

    @pytest.mark.asyncio
    async def test_empty_stamped_ids_returns_none_and_sentinel(self) -> None:
        with patch.object(JjClient, "log", new=AsyncMock(return_value=_NEWEST_FIRST_STACK)):
            target_change_id, stack_index = await resolve_target_against_current_stack(
                (), cwd=Path("/tmp/repo")
            )

        assert target_change_id is None
        assert stack_index == _UNLOCATABLE_STACK_INDEX

    @pytest.mark.asyncio
    async def test_each_call_issues_its_own_fresh_jj_log_call(self) -> None:
        """Two calls -> two independent jj log calls (no caching/sharing) —
        this is what makes it safe to call again mid-run after a prior
        answer's fold has just rebased the stack.
        """
        log_mock = AsyncMock(return_value=_NEWEST_FIRST_STACK)
        with patch.object(JjClient, "log", new=log_mock):
            await resolve_target_against_current_stack(("c1",), cwd=Path("/tmp/repo"))
            await resolve_target_against_current_stack(("c2",), cwd=Path("/tmp/repo"))

        assert log_mock.await_count == 2
