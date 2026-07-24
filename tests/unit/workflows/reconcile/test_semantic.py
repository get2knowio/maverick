"""Unit tests for the semantic-dependents pass (research R6, T028).

Covers T028's required cases:
- descendant enumeration revset (exact string)
- per-descendant analyze fan-out with correction diff
- dependent=false -> untouched (no fix applied)
- fixes applied via the correction mechanism into the flagged descendant
- follow-up round re-analyzes only previously flagged descendants
- semantic_rounds exhaustion semantics
- zero descendants -> completed, no agent call
- extra/unexpected change_id in a finding is ignored (ids-subset rule)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from maverick.assumptions.models import Severity
from maverick.jj.client import JjClient
from maverick.jj.models import JjChangeInfo, JjLogResult
from maverick.payloads import SemanticFinding, SubmitSemanticDependentsPayload
from maverick.workflows.reconcile.correction import CorrectionResult
from maverick.workflows.reconcile.models import ChangedAnswer
from maverick.workflows.reconcile.semantic import SemanticOutcome, run_semantic_pass

SEMANTIC_MODULE = "maverick.workflows.reconcile.semantic"


def _answer(
    *,
    target_change_id: str | None = "ktarget",
    stamped_change_ids: tuple[str, ...] = ("ktarget",),
) -> ChangedAnswer:
    return ChangedAnswer(
        entry_id="bd-1",
        question="Should retries be capped at 3?",
        adopted_answer="No cap, retry forever.",
        human_answer="Cap retries at 3.",
        severity=Severity.MEDIUM,
        owner_spec="051-reconcile-changed-answers",
        stamped_change_ids=stamped_change_ids,
        target_change_id=target_change_id,
        stack_index=0,
    )


def _change(change_id: str) -> JjChangeInfo:
    return JjChangeInfo(change_id=change_id, commit_id=f"{change_id}full", description=change_id)


def _log_result(*change_ids: str) -> JjLogResult:
    return JjLogResult(
        success=True,
        output="",
        changes=tuple(_change(cid) for cid in change_ids),
    )


def _finding(change_id: str, *, dependent: bool, fix_instructions: str = "") -> SemanticFinding:
    return SemanticFinding(
        change_id=change_id,
        dependent=dependent,
        reason="because" if dependent else "unrelated",
        fix_instructions=fix_instructions or ("do the fix" if dependent else ""),
    )


def _payload(*findings: SemanticFinding) -> SubmitSemanticDependentsPayload:
    return SubmitSemanticDependentsPayload(findings=tuple(findings))


def _make_semantic_agent(*payloads: SubmitSemanticDependentsPayload) -> AsyncMock:
    """An agent whose .analyze() returns successive payloads, one per call."""
    agent = AsyncMock()
    agent.analyze = AsyncMock(side_effect=list(payloads))
    return agent


def _diff_side_effect(*, default: str = "diff --git a/x b/x\n+content") -> Any:
    async def _jj_diff(*, revision: str, cwd: Path | None = None) -> dict[str, Any]:
        return {"success": True, "output": f"{default} ({revision})", "error": None}

    return AsyncMock(side_effect=_jj_diff)


@pytest.mark.asyncio
async def test_zero_descendants_short_circuits_no_agent_call() -> None:
    """No descendants -> completed=True, rounds_used=0, no analyze() call."""
    reconciler = AsyncMock()
    semantic = AsyncMock()
    semantic.analyze = AsyncMock(side_effect=AssertionError("analyze should not be called"))

    with patch.object(JjClient, "log", new=AsyncMock(return_value=_log_result())):
        result = await run_semantic_pass(
            reconciler,
            semantic,
            _answer(),
            "diff --git a/target b/target\n+fix",
            cwd=Path("/repo"),
            max_rounds=3,
        )

    assert result == SemanticOutcome(completed=True, rounds_used=0)
    semantic.analyze.assert_not_called()


@pytest.mark.asyncio
async def test_descendant_enumeration_revset_is_exact() -> None:
    """The revset passed to JjClient.log matches research R6 exactly."""
    log_mock = AsyncMock(return_value=_log_result())
    reconciler = AsyncMock()
    semantic = AsyncMock()
    semantic.analyze = AsyncMock(side_effect=AssertionError("no descendants to analyze"))

    with patch.object(JjClient, "log", new=log_mock):
        await run_semantic_pass(
            reconciler,
            semantic,
            _answer(target_change_id="ktarget"),
            "correction diff",
            cwd=Path("/repo"),
            max_rounds=3,
        )

    log_mock.assert_awaited_once_with(
        revset="descendants(ktarget) & mutable() & ~ktarget",
        limit=1000,
    )


@pytest.mark.asyncio
async def test_per_descendant_analyze_fanout_with_correction_diff() -> None:
    """analyze() receives correction_diff plus every descendant's captured diff."""
    reconciler = AsyncMock()
    payload = _payload(
        _finding("d1", dependent=False),
        _finding("d2", dependent=False),
    )
    semantic = _make_semantic_agent(payload)
    answer = _answer()
    correction_diff = "diff --git a/target b/target\n+the fix"

    with (
        patch.object(JjClient, "log", new=AsyncMock(return_value=_log_result("d1", "d2"))),
        patch(f"{SEMANTIC_MODULE}.jj_diff", new=_diff_side_effect()),
    ):
        result = await run_semantic_pass(
            reconciler, semantic, answer, correction_diff, cwd=Path("/repo"), max_rounds=3
        )

    assert result.completed is True
    assert result.rounds_used == 1
    assert result.fixed_descendants == ()

    semantic.analyze.assert_awaited_once()
    call_kwargs = semantic.analyze.await_args.kwargs
    assert call_kwargs["question"] == answer.question
    assert call_kwargs["adopted_answer"] == answer.adopted_answer
    assert call_kwargs["human_answer"] == answer.human_answer
    assert call_kwargs["correction_diff"] == correction_diff
    descendants = dict(call_kwargs["descendants"])
    assert set(descendants) == {"d1", "d2"}
    assert descendants["d1"] == "diff --git a/x b/x\n+content (d1)"
    assert descendants["d2"] == "diff --git a/x b/x\n+content (d2)"


@pytest.mark.asyncio
async def test_dependent_false_leaves_descendant_untouched() -> None:
    """dependent=False findings never trigger apply_correction."""
    reconciler = AsyncMock()
    payload = _payload(_finding("d1", dependent=False))
    semantic = _make_semantic_agent(payload)
    apply_correction_mock = AsyncMock()

    with (
        patch.object(JjClient, "log", new=AsyncMock(return_value=_log_result("d1"))),
        patch(f"{SEMANTIC_MODULE}.jj_diff", new=_diff_side_effect()),
        patch(f"{SEMANTIC_MODULE}.apply_correction", new=apply_correction_mock),
    ):
        result = await run_semantic_pass(
            reconciler, semantic, _answer(), "diff", cwd=Path("/repo"), max_rounds=3
        )

    assert result.completed is True
    assert result.fixed_descendants == ()
    apply_correction_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_fix_applied_via_correction_mechanism_targets_flagged_descendant() -> None:
    """dependent=True -> apply_correction called with a ChangedAnswer retargeted
    at the descendant."""
    reconciler = AsyncMock()
    payload_round1 = _payload(_finding("d1", dependent=True, fix_instructions="fix it"))
    payload_round2 = _payload(_finding("d1", dependent=False))
    semantic = _make_semantic_agent(payload_round1, payload_round2)
    original_answer = _answer(target_change_id="ktarget", stamped_change_ids=("ktarget", "klater"))
    apply_correction_mock = AsyncMock(
        return_value=CorrectionResult(applied=True, no_change_required=False, correction_diff="d")
    )

    with (
        patch.object(JjClient, "log", new=AsyncMock(return_value=_log_result("d1"))),
        patch(f"{SEMANTIC_MODULE}.jj_diff", new=_diff_side_effect()),
        patch(f"{SEMANTIC_MODULE}.apply_correction", new=apply_correction_mock),
    ):
        result = await run_semantic_pass(
            reconciler, semantic, original_answer, "diff", cwd=Path("/repo"), max_rounds=3
        )

    assert result.completed is True
    assert result.rounds_used == 2
    assert result.fixed_descendants == ("d1",)

    apply_correction_mock.assert_awaited_once()
    call_args = apply_correction_mock.await_args
    passed_answer: ChangedAnswer = call_args.args[1]
    assert passed_answer.target_change_id == "d1"
    assert passed_answer.stamped_change_ids == ("d1",)
    # Everything else about the answer carries through unchanged.
    assert passed_answer.entry_id == original_answer.entry_id
    assert passed_answer.question == original_answer.question
    assert call_args.kwargs["cwd"] == Path("/repo")


@pytest.mark.asyncio
async def test_followup_round_reanalyzes_only_previously_flagged() -> None:
    """Round 2's `descendants` param contains only what round 1 flagged."""
    reconciler = AsyncMock()
    payload_round1 = _payload(
        _finding("d1", dependent=False),
        _finding("d2", dependent=True, fix_instructions="fix d2"),
        _finding("d3", dependent=False),
    )
    payload_round2 = _payload(_finding("d2", dependent=False))
    semantic = _make_semantic_agent(payload_round1, payload_round2)
    apply_correction_mock = AsyncMock(
        return_value=CorrectionResult(applied=True, no_change_required=False, correction_diff="d")
    )

    with (
        patch.object(JjClient, "log", new=AsyncMock(return_value=_log_result("d1", "d2", "d3"))),
        patch(f"{SEMANTIC_MODULE}.jj_diff", new=_diff_side_effect()),
        patch(f"{SEMANTIC_MODULE}.apply_correction", new=apply_correction_mock),
    ):
        result = await run_semantic_pass(
            reconciler, semantic, _answer(), "diff", cwd=Path("/repo"), max_rounds=3
        )

    assert result.completed is True
    assert result.rounds_used == 2
    assert result.fixed_descendants == ("d2",)

    assert semantic.analyze.await_count == 2
    round1_call, round2_call = semantic.analyze.await_args_list
    round1_descendants = {cid for cid, _ in round1_call.kwargs["descendants"]}
    round2_descendants = {cid for cid, _ in round2_call.kwargs["descendants"]}
    assert round1_descendants == {"d1", "d2", "d3"}
    assert round2_descendants == {"d2"}


@pytest.mark.asyncio
async def test_semantic_rounds_exhaustion_returns_completed_false() -> None:
    """Still-flagged after max_rounds -> completed=False, partial fixes reported."""
    reconciler = AsyncMock()
    # Every round re-flags d1 as dependent — the fix never resolves it
    # within the budget.
    payload = _payload(_finding("d1", dependent=True, fix_instructions="fix it"))
    semantic = _make_semantic_agent(payload, payload)
    apply_correction_mock = AsyncMock(
        return_value=CorrectionResult(applied=True, no_change_required=False, correction_diff="d")
    )

    with (
        patch.object(JjClient, "log", new=AsyncMock(return_value=_log_result("d1"))),
        patch(f"{SEMANTIC_MODULE}.jj_diff", new=_diff_side_effect()),
        patch(f"{SEMANTIC_MODULE}.apply_correction", new=apply_correction_mock),
    ):
        result = await run_semantic_pass(
            reconciler, semantic, _answer(), "diff", cwd=Path("/repo"), max_rounds=2
        )

    assert result.completed is False
    assert result.error is None
    assert result.rounds_used == 2
    assert result.fixed_descendants == ("d1",)
    assert semantic.analyze.await_count == 2
    assert apply_correction_mock.await_count == 2


@pytest.mark.asyncio
async def test_apply_correction_failure_halts_pass_with_error() -> None:
    """An apply_correction failure surfaces as completed=False with its error."""
    reconciler = AsyncMock()
    payload = _payload(_finding("d1", dependent=True, fix_instructions="fix it"))
    semantic = _make_semantic_agent(payload)
    apply_correction_mock = AsyncMock(
        return_value=CorrectionResult(
            applied=False, no_change_required=False, correction_diff="", error="squash failed"
        )
    )

    with (
        patch.object(JjClient, "log", new=AsyncMock(return_value=_log_result("d1"))),
        patch(f"{SEMANTIC_MODULE}.jj_diff", new=_diff_side_effect()),
        patch(f"{SEMANTIC_MODULE}.apply_correction", new=apply_correction_mock),
    ):
        result = await run_semantic_pass(
            reconciler, semantic, _answer(), "diff", cwd=Path("/repo"), max_rounds=3
        )

    assert result.completed is False
    assert result.error == "squash failed"
    assert result.fixed_descendants == ()


@pytest.mark.asyncio
async def test_extra_unexpected_change_id_in_finding_is_ignored() -> None:
    """A finding for an id outside the supplied set is dropped, not acted on."""
    reconciler = AsyncMock()
    payload = _payload(
        _finding("d1", dependent=False),
        _finding("unexpected-id", dependent=True, fix_instructions="do something"),
    )
    semantic = _make_semantic_agent(payload)
    apply_correction_mock = AsyncMock()

    with (
        patch.object(JjClient, "log", new=AsyncMock(return_value=_log_result("d1"))),
        patch(f"{SEMANTIC_MODULE}.jj_diff", new=_diff_side_effect()),
        patch(f"{SEMANTIC_MODULE}.apply_correction", new=apply_correction_mock),
    ):
        result = await run_semantic_pass(
            reconciler, semantic, _answer(), "diff", cwd=Path("/repo"), max_rounds=3
        )

    assert result.completed is True
    assert result.fixed_descendants == ()
    apply_correction_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_supplied_id_in_response_treated_as_dependent_false() -> None:
    """A supplied descendant with no finding at all is treated as dependent=False."""
    reconciler = AsyncMock()
    # Only d2 gets a finding; d1 is silently omitted by the (misbehaving) agent.
    payload = _payload(_finding("d2", dependent=False))
    semantic = _make_semantic_agent(payload)
    apply_correction_mock = AsyncMock()

    with (
        patch.object(JjClient, "log", new=AsyncMock(return_value=_log_result("d1", "d2"))),
        patch(f"{SEMANTIC_MODULE}.jj_diff", new=_diff_side_effect()),
        patch(f"{SEMANTIC_MODULE}.apply_correction", new=apply_correction_mock),
    ):
        result = await run_semantic_pass(
            reconciler, semantic, _answer(), "diff", cwd=Path("/repo"), max_rounds=3
        )

    assert result.completed is True
    assert result.fixed_descendants == ()
    apply_correction_mock.assert_not_awaited()
