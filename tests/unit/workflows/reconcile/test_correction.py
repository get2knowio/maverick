"""Unit tests for the correction mechanism (research R3).

Covers T015's required cases:
- full sequence: new_child -> agent.correct -> diff_stat verify ->
  capture correction diff -> squash_into (single-stamp entry)
- empty-delta agreement (no_change_required=True, files_changed=0)
- mismatch failure: no_change_required=True but files_changed>0
- mismatch failure: no_change_required=False but files_changed=0
- absorb path selected only for multi-stamp entries
- correction diff captured BEFORE squash
- jj_new_child failure short-circuits before any agent call
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from maverick.assumptions.models import Severity
from maverick.jj.models import JjDiffStatResult
from maverick.payloads import SubmitCorrectionPayload
from maverick.workflows.reconcile.correction import CorrectionResult, apply_correction
from maverick.workflows.reconcile.models import ChangedAnswer

CORRECTION_MODULE = "maverick.workflows.reconcile.correction"


def _make_answer(
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


def _correction_payload(
    *,
    no_change_required: bool = False,
    files_touched: tuple[str, ...] = ("src/thing.py",),
    summary: str = "updated the retry limit",
) -> SubmitCorrectionPayload:
    return SubmitCorrectionPayload(
        summary=summary,
        files_touched=files_touched,
        no_change_required=no_change_required,
    )


def _make_reconciler(payload: SubmitCorrectionPayload) -> AsyncMock:
    reconciler = AsyncMock()
    reconciler.correct = AsyncMock(return_value=payload)
    return reconciler


def _diff_stat_result(files_changed: int) -> JjDiffStatResult:
    return JjDiffStatResult(
        success=True,
        output="",
        files_changed=files_changed,
        insertions=0,
        deletions=0,
    )


class _Patches:
    """Bundles the four jj-action mocks + JjClient.diff_stat patch used below."""

    def __init__(
        self,
        *,
        new_child_success: bool = True,
        new_child_error: str | None = None,
        target_diff_output: str = "diff --git a/target b/target\n+old",
        correction_diff_output: str = "diff --git a/src/thing.py b/src/thing.py\n+cap = 3",
        files_changed: int = 1,
        squash_success: bool = True,
        squash_error: str | None = None,
        absorb_success: bool = True,
        absorb_error: str | None = None,
    ) -> None:
        self.jj_new_child = AsyncMock(
            return_value={
                "success": new_child_success,
                "change_id": "kchild" if new_child_success else None,
                "error": new_child_error,
            }
        )

        # jj_diff is called twice in the normal path: once for the target
        # diff (before the agent call) and once for the correction diff
        # (post-verify, pre-fold). Route by revision.
        async def _jj_diff(*, revision: str, cwd: Path | None = None) -> dict[str, Any]:
            if revision == "ktarget":
                return {"success": True, "output": target_diff_output, "error": None}
            return {"success": True, "output": correction_diff_output, "error": None}

        self.jj_diff = AsyncMock(side_effect=_jj_diff)

        self.jj_squash_into = AsyncMock(
            return_value={"success": squash_success, "error": squash_error}
        )
        self.jj_absorb = AsyncMock(return_value={"success": absorb_success, "error": absorb_error})

        self.diff_stat_result = _diff_stat_result(files_changed)


@pytest.fixture
def patches():
    def _build(**kwargs: Any) -> _Patches:
        return _Patches(**kwargs)

    return _build


def _patch_all(p: _Patches):
    """Return a stack of patch() context managers for the four jj actions + JjClient."""
    mock_client = AsyncMock()
    mock_client.diff_stat = AsyncMock(return_value=p.diff_stat_result)
    return (
        patch(f"{CORRECTION_MODULE}.jj_new_child", p.jj_new_child),
        patch(f"{CORRECTION_MODULE}.jj_diff", p.jj_diff),
        patch(f"{CORRECTION_MODULE}.jj_squash_into", p.jj_squash_into),
        patch(f"{CORRECTION_MODULE}.jj_absorb", p.jj_absorb),
        patch(f"{CORRECTION_MODULE}.JjClient", return_value=mock_client),
    )


async def _run_with_patches(p: _Patches, reconciler: AsyncMock, answer: ChangedAnswer):
    ctxs = _patch_all(p)
    for ctx in ctxs:
        ctx.__enter__()
    try:
        return await apply_correction(reconciler, answer, cwd=Path("/repo"))
    finally:
        for ctx in reversed(ctxs):
            ctx.__exit__(None, None, None)


@pytest.mark.asyncio
async def test_full_sequence_single_stamp_squashes(patches) -> None:
    """new_child -> agent.correct -> diff_stat verify -> capture diff -> squash_into."""
    p = patches(files_changed=1)
    payload = _correction_payload(no_change_required=False)
    reconciler = _make_reconciler(payload)
    answer = _make_answer(stamped_change_ids=("ktarget",))

    result = await _run_with_patches(p, reconciler, answer)

    assert isinstance(result, CorrectionResult)
    assert result.applied is True
    assert result.error is None
    assert result.no_change_required is False
    assert result.payload is payload

    # Order + arguments.
    p.jj_new_child.assert_awaited_once_with(parent="ktarget", cwd=Path("/repo"))
    reconciler.correct.assert_awaited_once_with(
        question=answer.question,
        adopted_answer=answer.adopted_answer,
        human_answer=answer.human_answer,
        target_diff="diff --git a/target b/target\n+old",
    )
    p.jj_squash_into.assert_awaited_once_with(revision="@", into="ktarget", cwd=Path("/repo"))
    p.jj_absorb.assert_not_awaited()

    assert result.correction_diff == "diff --git a/src/thing.py b/src/thing.py\n+cap = 3"


@pytest.mark.asyncio
async def test_empty_delta_agreement_no_squash(patches) -> None:
    """no_change_required=True and files_changed=0 -> applied, no fold, no error."""
    p = patches(files_changed=0)
    payload = _correction_payload(no_change_required=True, files_touched=())
    reconciler = _make_reconciler(payload)
    answer = _make_answer()

    result = await _run_with_patches(p, reconciler, answer)

    assert result.applied is True
    assert result.no_change_required is True
    assert result.error is None
    assert result.correction_diff == ""
    p.jj_squash_into.assert_not_awaited()
    p.jj_absorb.assert_not_awaited()


@pytest.mark.asyncio
async def test_mismatch_claims_no_change_but_files_changed(patches) -> None:
    """no_change_required=True but files_changed>0 -> error, no fold."""
    p = patches(files_changed=2)
    payload = _correction_payload(no_change_required=True, files_touched=())
    reconciler = _make_reconciler(payload)
    answer = _make_answer()

    result = await _run_with_patches(p, reconciler, answer)

    assert result.applied is False
    assert result.error is not None
    assert "mismatch" in result.error
    p.jj_squash_into.assert_not_awaited()
    p.jj_absorb.assert_not_awaited()


@pytest.mark.asyncio
async def test_mismatch_claims_change_but_files_empty(patches) -> None:
    """no_change_required=False but files_changed=0 -> error, no fold."""
    p = patches(files_changed=0)
    payload = _correction_payload(no_change_required=False)
    reconciler = _make_reconciler(payload)
    answer = _make_answer()

    result = await _run_with_patches(p, reconciler, answer)

    assert result.applied is False
    assert result.error is not None
    assert "mismatch" in result.error
    p.jj_squash_into.assert_not_awaited()
    p.jj_absorb.assert_not_awaited()


@pytest.mark.asyncio
async def test_absorb_used_for_multi_stamp_entries(patches) -> None:
    """len(stamped_change_ids) > 1 -> jj_absorb, not jj_squash_into."""
    p = patches(files_changed=1)
    payload = _correction_payload(no_change_required=False)
    reconciler = _make_reconciler(payload)
    answer = _make_answer(stamped_change_ids=("ktarget", "klater"))

    result = await _run_with_patches(p, reconciler, answer)

    assert result.applied is True
    assert result.error is None
    p.jj_absorb.assert_awaited_once_with(cwd=Path("/repo"))
    p.jj_squash_into.assert_not_awaited()


@pytest.mark.asyncio
async def test_squash_into_used_for_single_stamp_entries(patches) -> None:
    """len(stamped_change_ids) == 1 -> jj_squash_into, not jj_absorb."""
    p = patches(files_changed=1)
    payload = _correction_payload(no_change_required=False)
    reconciler = _make_reconciler(payload)
    answer = _make_answer(stamped_change_ids=("ktarget",))

    result = await _run_with_patches(p, reconciler, answer)

    assert result.applied is True
    p.jj_squash_into.assert_awaited_once_with(revision="@", into="ktarget", cwd=Path("/repo"))
    p.jj_absorb.assert_not_awaited()


@pytest.mark.asyncio
async def test_correction_diff_captured_before_squash(patches) -> None:
    """The correction diff is read from the child ('@') pre-fold and returned verbatim."""
    p = patches(files_changed=1, correction_diff_output="diff --git a/x b/x\n+specific-marker")
    payload = _correction_payload(no_change_required=False)
    reconciler = _make_reconciler(payload)
    answer = _make_answer()

    result = await _run_with_patches(p, reconciler, answer)

    assert result.correction_diff == "diff --git a/x b/x\n+specific-marker"
    # jj_diff called for target ("ktarget") then for the child ("@") — in
    # that order, and the "@" call happens before the fold call.
    diff_calls = p.jj_diff.await_args_list
    assert diff_calls[0].kwargs["revision"] == "ktarget"
    assert diff_calls[1].kwargs["revision"] == "@"
    assert p.jj_squash_into.await_count == 1


@pytest.mark.asyncio
async def test_new_child_failure_short_circuits(patches) -> None:
    """jj_new_child failure returns an error result without calling the agent."""
    p = patches(new_child_success=False, new_child_error="no such revision")
    payload = _correction_payload()
    reconciler = _make_reconciler(payload)
    answer = _make_answer()

    result = await _run_with_patches(p, reconciler, answer)

    assert result.applied is False
    assert result.payload is None
    assert result.error is not None
    assert "no such revision" in result.error
    reconciler.correct.assert_not_awaited()
    p.jj_diff.assert_not_awaited()
    p.jj_squash_into.assert_not_awaited()
    p.jj_absorb.assert_not_awaited()


@pytest.mark.asyncio
async def test_squash_failure_returns_error_with_diff_captured(patches) -> None:
    """A failed jj_squash_into still reports the correction diff that was captured."""
    p = patches(files_changed=1, squash_success=False, squash_error="conflict")
    payload = _correction_payload(no_change_required=False)
    reconciler = _make_reconciler(payload)
    answer = _make_answer()

    result = await _run_with_patches(p, reconciler, answer)

    assert result.applied is False
    assert result.error is not None
    assert "conflict" in result.error
    assert result.correction_diff != ""
