"""Tests for the reconcile detection/mutator surfaces in ``ledger.py``.

Covers contracts/ledger-state.md's detection predicate (rules 1-5),
``answer()``'s FR-017 re-arm, and ``create_reconcile_escalation``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from maverick.assumptions.ledger import (
    answer,
    answered_unreconciled_entries,
    create_reconcile_escalation,
    mark_needs_interactive_review,
    mark_reconciled,
)
from maverick.assumptions.models import (
    ASSUMPTION_LABEL,
    ASSUMPTION_REVIEW_LABEL,
    KEY_ANSWER,
    KEY_RECONCILE_CHANGE_ID,
    KEY_RECONCILE_REASON,
    KEY_RECONCILE_STATUS,
    KEY_RECONCILED_ANSWER,
    KEY_RECONCILED_AT,
    KEY_SEVERITY,
    KEY_STATUS,
    RECONCILE_STATUS_NEEDS_REVIEW,
    RECONCILE_STATUS_RECONCILED,
    STATUS_ANSWERED,
    AssumptionRecord,
    Severity,
)
from maverick.beads.client import BeadClient
from maverick.beads.models import BeadDetails, BeadSummary, ClosedBead, CreatedBead


def _client() -> BeadClient:
    return BeadClient(cwd=Path("/tmp/repo"))


def _summary(bead_id: str, status: str = "closed") -> BeadSummary:
    return BeadSummary(id=bead_id, title=bead_id, status=status, bead_type="task")


def _entry(
    bead_id: str,
    *,
    answer_text: str,
    adopted_answer: str = "Original answer.",
    reconcile_status: str = "",
    reconciled_answer: str = "",
    status: str = STATUS_ANSWERED,
    labels: list[str] | None = None,
) -> BeadDetails:
    state = {
        KEY_STATUS: status,
        KEY_ANSWER: answer_text,
        KEY_SEVERITY: "medium",
    }
    if reconcile_status:
        state[KEY_RECONCILE_STATUS] = reconcile_status
    if reconciled_answer:
        state[KEY_RECONCILED_ANSWER] = reconciled_answer
    return BeadDetails(
        id=bead_id,
        title=f"Assumption: {bead_id}",
        description=f"## Question\n\nQ?\n\n## Adopted Answer\n\n{adopted_answer}\n\n",
        bead_type="task",
        status="closed",
        labels=labels if labels is not None else [ASSUMPTION_LABEL],
        state=state,
    )


def _record(bead_id: str = "dea-1", severity: Severity = Severity.MEDIUM) -> AssumptionRecord:
    return AssumptionRecord(
        bead_id=bead_id,
        question="Should we use X?",
        adopted_answer="Original answer.",
        alternatives=(),
        severity=severity,
        severity_defaulted=False,
        status=STATUS_ANSWERED,
        owner_spec="051-reconcile-changed-answers",
        source_bead="src-1",
        change_ids=("abc123",),
        is_legacy=False,
    )


class TestAnsweredUnreconciledEntries:
    @pytest.mark.asyncio
    async def test_detects_changed_answer(self) -> None:
        """Rule 4: normalized human answer differs from adopted answer -> detected."""
        client = _client()
        entries = {"dea-1": _entry("dea-1", answer_text="A brand new answer.")}

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            return [_summary(k) for k in entries]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return entries[bead_id]

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await answered_unreconciled_entries(client)

        assert {r.bead_id for r in result} == {"dea-1"}

    @pytest.mark.asyncio
    async def test_rule1_excludes_beads_without_assumption_label(self) -> None:
        """Rule 1: bead must carry ASSUMPTION_LABEL — legacy-only excluded here too."""
        client = _client()
        entries = {
            "dea-1": _entry("dea-1", answer_text="Changed.", labels=[ASSUMPTION_REVIEW_LABEL])
        }

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            return [_summary(k) for k in entries]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return entries[bead_id]

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await answered_unreconciled_entries(client)

        assert result == ()

    @pytest.mark.asyncio
    async def test_rule2_excludes_non_answered_status(self) -> None:
        """Rule 2: assumption_status must equal answered."""
        client = _client()
        entries = {
            "dea-1": _entry("dea-1", answer_text="Changed.", status="open"),
        }

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            return [_summary(k) for k in entries]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return entries[bead_id]

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await answered_unreconciled_entries(client)

        assert result == ()

    @pytest.mark.asyncio
    async def test_rule3_excludes_entries_with_reconcile_status_set(self) -> None:
        """Rule 3: a terminal assumption_reconcile_status excludes the entry."""
        client = _client()
        entries = {
            "dea-1": _entry(
                "dea-1",
                answer_text="Changed.",
                reconcile_status=RECONCILE_STATUS_NEEDS_REVIEW,
            ),
        }

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            return [_summary(k) for k in entries]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return entries[bead_id]

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await answered_unreconciled_entries(client)

        assert result == ()

    @pytest.mark.asyncio
    async def test_rule4_excludes_answer_matching_adopted_answer(self) -> None:
        """Rule 4: human answer normalizing equal to adopted answer -> not detected."""
        client = _client()
        entries = {
            "dea-1": _entry(
                "dea-1",
                answer_text="  Original   answer.  ",
                adopted_answer="Original answer.",
            ),
        }

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            return [_summary(k) for k in entries]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return entries[bead_id]

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await answered_unreconciled_entries(client)

        assert result == ()

    @pytest.mark.asyncio
    async def test_rule5_excludes_answer_matching_previously_reconciled(self) -> None:
        """Rule 5 (idempotence, SC-008): matches assumption_reconciled_answer -> excluded."""
        client = _client()
        entries = {
            "dea-1": _entry(
                "dea-1",
                answer_text="Already applied answer.",
                adopted_answer="Original answer.",
                reconciled_answer="already applied answer.",
            ),
        }

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            return [_summary(k) for k in entries]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return entries[bead_id]

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await answered_unreconciled_entries(client)

        assert result == ()

    @pytest.mark.asyncio
    async def test_queries_regardless_of_closed_status(self) -> None:
        """answer() closes beads — detection must not filter by open status."""
        client = _client()
        entries = {"dea-1": _entry("dea-1", answer_text="Changed.")}
        assert entries["dea-1"].status == "closed"

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            assert "status=open" not in filter_expr
            return [_summary(k, status="closed") for k in entries]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return entries[bead_id]

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await answered_unreconciled_entries(client)

        assert {r.bead_id for r in result} == {"dea-1"}

    @pytest.mark.asyncio
    async def test_ordered_by_bead_id(self) -> None:
        client = _client()
        entries = {
            "dea-2": _entry("dea-2", answer_text="Changed 2."),
            "dea-1": _entry("dea-1", answer_text="Changed 1."),
        }

        async def fake_query(self: BeadClient, filter_expr: str) -> list[BeadSummary]:
            return [_summary(k) for k in entries]

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return entries[bead_id]

        with (
            patch.object(BeadClient, "query", new=fake_query),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            result = await answered_unreconciled_entries(client)

        assert [r.bead_id for r in result] == ["dea-1", "dea-2"]


class TestMarkReconciled:
    @pytest.mark.asyncio
    async def test_sets_expected_state_and_returns_true(self) -> None:
        client = _client()
        with patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state:
            result = await mark_reconciled(
                client,
                entry_id="dea-1",
                applied_answer="  A New Answer.  ",
                change_id="xyz789",
            )

        assert result is True
        state_dict = mock_set_state.await_args.args[1]
        assert state_dict[KEY_RECONCILE_STATUS] == RECONCILE_STATUS_RECONCILED
        assert state_dict[KEY_RECONCILED_ANSWER] == "a new answer."
        assert state_dict[KEY_RECONCILE_CHANGE_ID] == "xyz789"
        assert KEY_RECONCILED_AT in state_dict

    @pytest.mark.asyncio
    async def test_never_raises_on_bd_failure(self) -> None:
        client = _client()
        with patch.object(
            BeadClient, "set_state", new=AsyncMock(side_effect=RuntimeError("bd failed"))
        ):
            result = await mark_reconciled(
                client, entry_id="dea-1", applied_answer="A.", change_id="xyz"
            )

        assert result is False


class TestMarkNeedsInteractiveReview:
    @pytest.mark.asyncio
    async def test_sets_expected_state_and_returns_true(self) -> None:
        client = _client()
        with patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state:
            result = await mark_needs_interactive_review(
                client, entry_id="dea-1", reason="conflict rounds exhausted"
            )

        assert result is True
        state_dict = mock_set_state.await_args.args[1]
        assert state_dict[KEY_RECONCILE_STATUS] == RECONCILE_STATUS_NEEDS_REVIEW
        assert state_dict[KEY_RECONCILE_REASON] == "conflict rounds exhausted"

    @pytest.mark.asyncio
    async def test_never_raises_on_bd_failure(self) -> None:
        client = _client()
        with patch.object(
            BeadClient, "set_state", new=AsyncMock(side_effect=RuntimeError("bd failed"))
        ):
            result = await mark_needs_interactive_review(client, entry_id="dea-1", reason="boom")

        assert result is False


class TestAnswerReArm:
    @pytest.mark.asyncio
    async def test_answer_clears_reconcile_status(self) -> None:
        client = _client()

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _entry(bead_id, answer_text="Yes.")

        with (
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
            patch.object(
                BeadClient,
                "close",
                new=AsyncMock(return_value=ClosedBead(id="dea-1", status="closed")),
            ),
            patch.object(BeadClient, "show", new=fake_show),
        ):
            await answer(client, bead_id="dea-1", answer_text="Yes.")

        state_dict = mock_set_state.await_args.args[1]
        assert state_dict[KEY_RECONCILE_STATUS] == ""


class TestCreateReconcileEscalation:
    @pytest.mark.asyncio
    async def test_conflicts_kind_builds_expected_bead(self) -> None:
        client = _client()
        entry = _record()

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _entry(bead_id, answer_text="A new human answer.")

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(
                BeadClient,
                "create_bead",
                new=AsyncMock(
                    side_effect=lambda definition, parent_id=None: CreatedBead(
                        bd_id="dea-esc-1", definition=definition
                    )
                ),
            ) as mock_create,
            patch.object(BeadClient, "set_state", new=AsyncMock()) as mock_set_state,
            patch.object(BeadClient, "add_dependency", new=AsyncMock()) as mock_add_dep,
        ):
            result = await create_reconcile_escalation(
                client, entry=entry, remaining=["change-a", "change-b"], kind="conflicts"
            )

        assert result == "dea-esc-1"
        definition = mock_create.await_args.args[0]
        assert definition.assignee == "human"
        assert set(definition.labels) == {"assumption-review", "needs-human-review"}
        assert "## Remaining Conflicts" in definition.description
        assert "change-a" in definition.description
        assert "A new human answer." in definition.description
        assert entry.adopted_answer in definition.description

        state_dict = mock_set_state.await_args.args[1]
        assert state_dict["source_bead"] == entry.bead_id
        assert state_dict["escalation_type"] == "reconcile_exhaustion"

        dep = mock_add_dep.await_args.args[0]
        assert dep.blocker_id == entry.bead_id
        assert dep.blocked_id == "dea-esc-1"
        assert dep.dep_type.value == "discovered-from"

    @pytest.mark.asyncio
    async def test_semantic_kind_uses_unresolved_dependents_heading(self) -> None:
        client = _client()
        entry = _record()

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _entry(bead_id, answer_text="A new human answer.")

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(
                BeadClient,
                "create_bead",
                new=AsyncMock(
                    side_effect=lambda definition, parent_id=None: CreatedBead(
                        bd_id="dea-esc-2", definition=definition
                    )
                ),
            ) as mock_create,
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch.object(BeadClient, "add_dependency", new=AsyncMock()),
        ):
            result = await create_reconcile_escalation(
                client, entry=entry, remaining=["dep-1"], kind="semantic"
            )

        assert result == "dea-esc-2"
        definition = mock_create.await_args.args[0]
        assert "## Unresolved Dependents" in definition.description
        assert "dep-1" in definition.description
        assert "## Remaining Conflicts" not in definition.description

    @pytest.mark.asyncio
    async def test_never_raises_on_create_bead_failure(self) -> None:
        client = _client()
        entry = _record()

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _entry(bead_id, answer_text="A new human answer.")

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(
                BeadClient,
                "create_bead",
                new=AsyncMock(side_effect=RuntimeError("bd create failed")),
            ),
        ):
            result = await create_reconcile_escalation(
                client, entry=entry, remaining=[], kind="conflicts"
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_never_raises_when_show_fails(self) -> None:
        """The initial lookup for the human answer must not surface bd failures."""
        client = _client()
        entry = _record()

        with (
            patch.object(
                BeadClient, "show", new=AsyncMock(side_effect=RuntimeError("bd show failed"))
            ),
            patch.object(
                BeadClient,
                "create_bead",
                new=AsyncMock(
                    side_effect=lambda definition, parent_id=None: CreatedBead(
                        bd_id="dea-esc-3", definition=definition
                    )
                ),
            ),
            patch.object(BeadClient, "set_state", new=AsyncMock()),
            patch.object(BeadClient, "add_dependency", new=AsyncMock()),
        ):
            result = await create_reconcile_escalation(
                client, entry=entry, remaining=[], kind="conflicts"
            )

        assert result == "dea-esc-3"

    @pytest.mark.asyncio
    async def test_never_raises_when_set_state_or_add_dependency_fail(self) -> None:
        client = _client()
        entry = _record()

        async def fake_show(self: BeadClient, bead_id: str) -> BeadDetails:
            return _entry(bead_id, answer_text="A new human answer.")

        with (
            patch.object(BeadClient, "show", new=fake_show),
            patch.object(
                BeadClient,
                "create_bead",
                new=AsyncMock(
                    side_effect=lambda definition, parent_id=None: CreatedBead(
                        bd_id="dea-esc-4", definition=definition
                    )
                ),
            ),
            patch.object(
                BeadClient, "set_state", new=AsyncMock(side_effect=RuntimeError("state failed"))
            ),
            patch.object(
                BeadClient,
                "add_dependency",
                new=AsyncMock(side_effect=RuntimeError("dep failed")),
            ),
        ):
            result = await create_reconcile_escalation(
                client, entry=entry, remaining=[], kind="semantic"
            )

        assert result == "dea-esc-4"
