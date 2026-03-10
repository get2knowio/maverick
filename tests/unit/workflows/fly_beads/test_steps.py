"""Unit tests for fly_beads step functions."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.library.actions.types import VerifyBeadCompletionResult
from maverick.workflows.fly_beads.models import BeadContext
from maverick.workflows.fly_beads.steps import (
    commit_bead,
    load_briefing_context,
    rollback_bead,
    run_implement,
    run_sync_deps,
    run_validate_and_fix,
    run_verify_cycle,
    snapshot_and_describe,
)

_STEPS_MOD = "maverick.workflows.fly_beads.steps"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(**overrides: Any) -> BeadContext:
    defaults: dict[str, Any] = {
        "bead_id": "b1",
        "title": "Test bead",
        "description": "Do work",
        "epic_id": "e1",
        "cwd": Path("/tmp/ws"),
    }
    defaults.update(overrides)
    return BeadContext(**defaults)


def _make_wf(
    *,
    has_executor: bool = True,
) -> MagicMock:
    """Build a mock workflow with emit_* helpers and optional step executor."""
    wf = MagicMock()
    wf.emit_step_started = AsyncMock()
    wf.emit_step_completed = AsyncMock()
    wf.emit_step_failed = AsyncMock()
    wf.emit_output = AsyncMock()

    if has_executor:
        from maverick.executor.result import ExecutorResult

        executor = AsyncMock()
        executor.execute.return_value = ExecutorResult(
            success=True, output="done", usage=None, events=()
        )
        wf._step_executor = executor
    else:
        wf._step_executor = None

    return wf


# ---------------------------------------------------------------------------
# load_briefing_context
# ---------------------------------------------------------------------------


class TestLoadBriefingContext:
    def test_returns_none_for_no_plan_name(self) -> None:
        assert load_briefing_context(None) is None

    def test_returns_none_for_missing_dir(self, tmp_path: Path) -> None:
        with patch(f"{_STEPS_MOD}.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            result = load_briefing_context("nonexistent-plan")
        assert result is None

    def test_reads_briefing_file(self, tmp_path: Path) -> None:
        plan_dir = tmp_path / ".maverick" / "plans" / "my-plan"
        plan_dir.mkdir(parents=True)
        (plan_dir / "briefing.md").write_text("# Briefing", encoding="utf-8")

        with patch(f"{_STEPS_MOD}.Path") as mock_path:
            mock_path.cwd.return_value = tmp_path
            # Allow Path() division to work normally
            mock_path.__truediv__ = Path.__truediv__
            mock_path.return_value = tmp_path
            # Need the real Path for file operations
            result = (
                load_briefing_context.__wrapped__(  # type: ignore[attr-defined]
                    "my-plan"
                )
                if hasattr(load_briefing_context, "__wrapped__")
                else None
            )

        # Simpler approach: just call it with the real cwd set
        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = load_briefing_context("my-plan")
        finally:
            os.chdir(old_cwd)

        assert result == "# Briefing"

    def test_prefers_refuel_briefing(self, tmp_path: Path) -> None:
        plan_dir = tmp_path / ".maverick" / "plans" / "my-plan"
        plan_dir.mkdir(parents=True)
        (plan_dir / "briefing.md").write_text("old", encoding="utf-8")
        (plan_dir / "refuel-briefing.md").write_text("new", encoding="utf-8")

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            result = load_briefing_context("my-plan")
        finally:
            os.chdir(old_cwd)

        assert result == "new"


# ---------------------------------------------------------------------------
# snapshot_and_describe
# ---------------------------------------------------------------------------


class TestSnapshotAndDescribe:
    async def test_sets_operation_id(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx()

        with (
            patch(
                f"{_STEPS_MOD}.jj_snapshot_operation",
                new_callable=AsyncMock,
                return_value={"operation_id": "op42"},
            ),
            patch(f"{_STEPS_MOD}.jj_describe", new_callable=AsyncMock),
        ):
            await snapshot_and_describe(wf, ctx)

        assert ctx.operation_id == "op42"


# ---------------------------------------------------------------------------
# run_implement
# ---------------------------------------------------------------------------


class TestRunImplement:
    async def test_calls_executor(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx()

        await run_implement(wf, ctx)

        wf._step_executor.execute.assert_called_once()
        wf.emit_step_completed.assert_called_once()
        wf.emit_step_failed.assert_not_called()

    async def test_failure_emits_step_failed(self) -> None:
        """Bug class: implement failure must emit step_failed, not step_completed."""
        wf = _make_wf()
        wf._step_executor.execute.side_effect = RuntimeError("agent crash")
        ctx = _make_ctx()

        await run_implement(wf, ctx)

        wf.emit_step_failed.assert_called_once()
        wf.emit_step_completed.assert_not_called()

    async def test_prior_failures_included_in_prompt(self) -> None:
        """Bug class: prior failure context must be passed to implementer."""
        wf = _make_wf()
        ctx = _make_ctx(prior_failures=["lint failed", "test failed"])

        await run_implement(wf, ctx)

        prompt_arg = wf._step_executor.execute.call_args.kwargs["prompt"]
        assert "previous_failures" in prompt_arg
        assert "lint failed" in prompt_arg["previous_failures"]
        assert "test failed" in prompt_arg["previous_failures"]

    async def test_no_executor_emits_warning(self) -> None:
        wf = _make_wf(has_executor=False)
        ctx = _make_ctx()

        await run_implement(wf, ctx)

        wf.emit_output.assert_called_once()
        assert "skipping" in wf.emit_output.call_args.args[1].lower()
        wf.emit_step_completed.assert_called_once()


# ---------------------------------------------------------------------------
# run_sync_deps
# ---------------------------------------------------------------------------


class TestRunSyncDeps:
    async def test_raises_on_failure(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx()

        with patch(
            f"{_STEPS_MOD}.sync_dependencies",
            new_callable=AsyncMock,
            side_effect=RuntimeError("uv sync failed"),
        ):
            with pytest.raises(RuntimeError, match="uv sync failed"):
                await run_sync_deps(wf, ctx)

        wf.emit_step_failed.assert_called_once()


# ---------------------------------------------------------------------------
# run_validate_and_fix
# ---------------------------------------------------------------------------


class TestRunValidateAndFix:
    async def test_stores_result_in_ctx(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx()
        validation_result = {"passed": True, "stages": []}

        with patch(
            f"{_STEPS_MOD}.run_fix_retry_loop",
            new_callable=AsyncMock,
            return_value=validation_result,
        ):
            await run_validate_and_fix(wf, ctx)

        assert ctx.validation_result is validation_result

    async def test_creates_fix_beads_on_failure(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx()
        validation_result = {"passed": False, "stages": ["lint"]}

        with (
            patch(
                f"{_STEPS_MOD}.run_fix_retry_loop",
                new_callable=AsyncMock,
                return_value=validation_result,
            ),
            patch(
                f"{_STEPS_MOD}.create_beads_from_failures",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            await run_validate_and_fix(wf, ctx)

        mock_create.assert_called_once()


# ---------------------------------------------------------------------------
# run_verify_cycle
# ---------------------------------------------------------------------------


class TestRunVerifyCycle:
    async def test_revalidates_after_review(self) -> None:
        """Bug class: validation must re-run AFTER review fixer changes."""
        wf = _make_wf()
        ctx = _make_ctx()

        call_order: list[str] = []

        async def mock_review_fix_loop(**kwargs: Any) -> MagicMock:
            call_order.append("review")
            return MagicMock(to_dict=lambda: {"success": True, "issues_remaining": []})

        async def mock_fix_retry_loop(**kwargs: Any) -> dict[str, Any]:
            call_order.append("validate")
            return {"passed": True, "stages": []}

        with (
            patch(
                f"{_STEPS_MOD}.gather_local_review_context",
                new_callable=AsyncMock,
                return_value=MagicMock(to_dict=lambda: {}),
            ),
            patch(
                f"{_STEPS_MOD}.run_review_fix_loop",
                new_callable=AsyncMock,
                side_effect=mock_review_fix_loop,
            ),
            patch(
                f"{_STEPS_MOD}.run_fix_retry_loop",
                new_callable=AsyncMock,
                side_effect=mock_fix_retry_loop,
            ),
            patch(
                f"{_STEPS_MOD}.verify_bead_completion",
                new_callable=AsyncMock,
                return_value=VerifyBeadCompletionResult(passed=True, reasons=()),
            ),
            patch(
                f"{_STEPS_MOD}.create_beads_from_findings",
                new_callable=AsyncMock,
            ),
        ):
            await run_verify_cycle(wf, ctx, skip_review=False)

        # review must come before validate in the cycle
        assert call_order == ["review", "validate"]
        assert ctx.verify_result is not None
        assert ctx.verify_result.passed is True

    async def test_retries_from_validate_on_failure(self) -> None:
        """Bug class: on verify failure, retry from review+validate, NOT implement."""
        wf = _make_wf()
        ctx = _make_ctx()

        verify_results = iter(
            [
                VerifyBeadCompletionResult(passed=False, reasons=("lint failed",)),
                VerifyBeadCompletionResult(passed=True, reasons=()),
            ]
        )

        validate_count = 0

        async def mock_fix_retry_loop(**kwargs: Any) -> dict[str, Any]:
            nonlocal validate_count
            validate_count += 1
            return {"passed": True, "stages": []}

        with (
            patch(
                f"{_STEPS_MOD}.gather_local_review_context",
                new_callable=AsyncMock,
                return_value=MagicMock(to_dict=lambda: {}),
            ),
            patch(
                f"{_STEPS_MOD}.run_review_fix_loop",
                new_callable=AsyncMock,
                return_value=MagicMock(
                    to_dict=lambda: {"success": True, "issues_remaining": []}
                ),
            ),
            patch(
                f"{_STEPS_MOD}.run_fix_retry_loop",
                new_callable=AsyncMock,
                side_effect=mock_fix_retry_loop,
            ),
            patch(
                f"{_STEPS_MOD}.verify_bead_completion",
                new_callable=AsyncMock,
                side_effect=verify_results,
            ),
            patch(
                f"{_STEPS_MOD}.create_beads_from_findings",
                new_callable=AsyncMock,
            ),
        ):
            await run_verify_cycle(wf, ctx, skip_review=False)

        # validate called twice (once per cycle)
        assert validate_count == 2
        assert ctx.verify_result is not None
        assert ctx.verify_result.passed is True

    async def test_skip_review(self) -> None:
        """Review step not called when skip_review=True."""
        wf = _make_wf()
        ctx = _make_ctx()

        with (
            patch(
                f"{_STEPS_MOD}.gather_local_review_context",
                new_callable=AsyncMock,
            ) as mock_gather,
            patch(
                f"{_STEPS_MOD}.run_review_fix_loop",
                new_callable=AsyncMock,
            ) as mock_review,
            patch(
                f"{_STEPS_MOD}.run_fix_retry_loop",
                new_callable=AsyncMock,
                return_value={"passed": True, "stages": []},
            ),
            patch(
                f"{_STEPS_MOD}.verify_bead_completion",
                new_callable=AsyncMock,
                return_value=VerifyBeadCompletionResult(passed=True, reasons=()),
            ),
        ):
            await run_verify_cycle(wf, ctx, skip_review=True)

        mock_gather.assert_not_called()
        mock_review.assert_not_called()

    async def test_review_failure_sets_none_review_result(self) -> None:
        """Bug class: review failure must propagate via ctx.review_result=None."""
        wf = _make_wf()
        ctx = _make_ctx()

        with (
            patch(
                f"{_STEPS_MOD}.gather_local_review_context",
                new_callable=AsyncMock,
                side_effect=RuntimeError("review agent down"),
            ),
            patch(
                f"{_STEPS_MOD}.run_fix_retry_loop",
                new_callable=AsyncMock,
                return_value={"passed": True, "stages": []},
            ),
            patch(
                f"{_STEPS_MOD}.verify_bead_completion",
                new_callable=AsyncMock,
                return_value=VerifyBeadCompletionResult(passed=True, reasons=()),
            ),
        ):
            await run_verify_cycle(wf, ctx, skip_review=False)

        assert ctx.review_result is None


# ---------------------------------------------------------------------------
# commit_bead
# ---------------------------------------------------------------------------


class TestCommitBead:
    async def test_commits_and_marks_complete(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx()

        with (
            patch(
                f"{_STEPS_MOD}.jj_commit_bead",
                new_callable=AsyncMock,
                return_value={"success": True},
            ) as mock_commit,
            patch(
                f"{_STEPS_MOD}.mark_bead_complete",
                new_callable=AsyncMock,
            ) as mock_mark,
        ):
            await commit_bead(wf, ctx)

        mock_commit.assert_called_once_with(message="bead(b1): Test bead", cwd=ctx.cwd)
        mock_mark.assert_called_once_with(bead_id="b1")
        wf.emit_step_completed.assert_called_once()
        wf.emit_output.assert_called_once()


# ---------------------------------------------------------------------------
# rollback_bead
# ---------------------------------------------------------------------------


class TestRollbackBead:
    async def test_restores_jj_operation(self) -> None:
        """Bug class: rollback must call jj_restore_operation with ctx.operation_id."""
        wf = _make_wf()
        ctx = _make_ctx(operation_id="op99")

        with patch(
            f"{_STEPS_MOD}.jj_restore_operation",
            new_callable=AsyncMock,
        ) as mock_restore:
            await rollback_bead(wf, ctx)

        mock_restore.assert_called_once_with(operation_id="op99", cwd=ctx.cwd)
        wf.emit_output.assert_called_once()

    async def test_skips_restore_when_no_operation_id(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx(operation_id=None)

        with patch(
            f"{_STEPS_MOD}.jj_restore_operation",
            new_callable=AsyncMock,
        ) as mock_restore:
            await rollback_bead(wf, ctx)

        mock_restore.assert_not_called()

    async def test_emits_failure_reasons(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx(operation_id=None)
        ctx.verify_result = VerifyBeadCompletionResult(
            passed=False, reasons=("lint failed", "test failed")
        )

        with patch(f"{_STEPS_MOD}.jj_restore_operation", new_callable=AsyncMock):
            await rollback_bead(wf, ctx)

        output_msg = wf.emit_output.call_args.args[1]
        assert "lint failed" in output_msg
        assert "test failed" in output_msg
