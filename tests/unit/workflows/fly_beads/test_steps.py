"""Unit tests for fly_beads step functions (invariant-based orchestration)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from maverick.library.actions.types import VerifyBeadCompletionResult
from maverick.workflows.fly_beads.models import BeadContext
from maverick.workflows.fly_beads.steps import (
    commit_bead,
    load_briefing_context,
    rollback_bead,
    run_gate_check,
    run_gate_remediation,
    run_implement_and_validate,
    run_review_and_remediate,
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
# run_implement_and_validate
# ---------------------------------------------------------------------------


class TestRunImplementAndValidate:
    async def test_calls_executor_with_correct_timeout(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx()

        await run_implement_and_validate(wf, ctx)

        wf._step_executor.execute.assert_called_once()
        call_kwargs = wf._step_executor.execute.call_args.kwargs
        assert call_kwargs["step_name"] == "implement_and_validate"
        assert call_kwargs["agent_name"] == "implementer"
        assert call_kwargs["config"].timeout == 900
        wf.emit_step_completed.assert_called_once()
        wf.emit_step_failed.assert_not_called()

    async def test_failure_emits_step_failed(self) -> None:
        """Implement failure must emit step_failed, not step_completed."""
        wf = _make_wf()
        wf._step_executor.execute.side_effect = RuntimeError("agent crash")
        ctx = _make_ctx()

        await run_implement_and_validate(wf, ctx)

        wf.emit_step_failed.assert_called_once()
        wf.emit_step_completed.assert_not_called()

    async def test_prior_failures_included_in_prompt(self) -> None:
        """Prior failure context must be passed to implementer."""
        wf = _make_wf()
        ctx = _make_ctx(prior_failures=["lint failed", "test failed"])

        await run_implement_and_validate(wf, ctx)

        prompt_arg = wf._step_executor.execute.call_args.kwargs["prompt"]
        assert "previous_failures" in prompt_arg
        assert "lint failed" in prompt_arg["previous_failures"]
        assert "test failed" in prompt_arg["previous_failures"]

    async def test_briefing_context_included_in_prompt(self) -> None:
        """Briefing context must be passed to implementer when available."""
        wf = _make_wf()
        ctx = _make_ctx(briefing_context="## Context\nSome briefing text")

        await run_implement_and_validate(wf, ctx)

        prompt_arg = wf._step_executor.execute.call_args.kwargs["prompt"]
        assert "briefing_context" in prompt_arg
        assert "Some briefing text" in prompt_arg["briefing_context"]

    async def test_runway_context_included_in_prompt(self) -> None:
        """Runway context must be passed to implementer when available."""
        wf = _make_wf()
        ctx = _make_ctx(runway_context="### Recent Outcomes\n- bead-1: passed")

        await run_implement_and_validate(wf, ctx)

        prompt_arg = wf._step_executor.execute.call_args.kwargs["prompt"]
        assert "runway_context" in prompt_arg
        assert "Recent Outcomes" in prompt_arg["runway_context"]

    async def test_no_executor_emits_warning(self) -> None:
        wf = _make_wf(has_executor=False)
        ctx = _make_ctx()

        await run_implement_and_validate(wf, ctx)

        wf.emit_output.assert_called_once()
        assert "skipping" in wf.emit_output.call_args.args[1].lower()
        wf.emit_step_completed.assert_called_once()


# ---------------------------------------------------------------------------
# run_gate_check
# ---------------------------------------------------------------------------


class TestRunGateCheck:
    async def test_runs_independent_validation(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx()
        gate_result = {
            "passed": True,
            "stage_results": {"format": {"passed": True}},
            "summary": "All 4 validation stages passed.",
        }

        with patch(
            f"{_STEPS_MOD}.run_independent_gate",
            new_callable=AsyncMock,
            return_value=gate_result,
        ):
            await run_gate_check(wf, ctx)

        assert ctx.gate_result is gate_result
        assert ctx.validation_result is gate_result
        wf.emit_step_completed.assert_called_once()

    async def test_stores_failure_in_ctx(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx()
        gate_result = {
            "passed": False,
            "stage_results": {"lint": {"passed": False, "output": "error"}},
            "summary": "1 of 4 failed: lint",
        }

        with patch(
            f"{_STEPS_MOD}.run_independent_gate",
            new_callable=AsyncMock,
            return_value=gate_result,
        ):
            await run_gate_check(wf, ctx)

        assert ctx.gate_result is not None
        assert ctx.gate_result["passed"] is False

    async def test_handles_exception_gracefully(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx()

        with patch(
            f"{_STEPS_MOD}.run_independent_gate",
            new_callable=AsyncMock,
            side_effect=RuntimeError("validation runner crashed"),
        ):
            await run_gate_check(wf, ctx)

        assert ctx.gate_result is not None
        assert ctx.gate_result["passed"] is False
        wf.emit_step_failed.assert_called_once()


# ---------------------------------------------------------------------------
# run_gate_remediation
# ---------------------------------------------------------------------------


class TestRunGateRemediation:
    async def test_sets_remediation_attempted(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx()
        ctx.gate_result = {
            "passed": False,
            "stage_results": {"lint": {"passed": False, "output": "error"}},
            "summary": "1 of 4 failed: lint",
        }

        await run_gate_remediation(wf, ctx)

        assert ctx.remediation_attempted is True
        wf._step_executor.execute.assert_called_once()
        call_kwargs = wf._step_executor.execute.call_args.kwargs
        assert call_kwargs["agent_name"] == "gate_remediator"
        assert call_kwargs["config"].timeout == 600

    async def test_no_executor_skips_gracefully(self) -> None:
        wf = _make_wf(has_executor=False)
        ctx = _make_ctx()
        ctx.gate_result = {"passed": False, "stage_results": {}, "summary": "failed"}

        await run_gate_remediation(wf, ctx)

        assert ctx.remediation_attempted is True
        wf.emit_output.assert_called_once()

    async def test_failure_emits_step_failed(self) -> None:
        wf = _make_wf()
        wf._step_executor.execute.side_effect = RuntimeError("agent crash")
        ctx = _make_ctx()
        ctx.gate_result = {"passed": False, "stage_results": {}, "summary": "failed"}

        await run_gate_remediation(wf, ctx)

        assert ctx.remediation_attempted is True
        wf.emit_step_failed.assert_called_once()

    async def test_prompt_includes_gate_failure_details(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx()
        ctx.gate_result = {
            "passed": False,
            "stage_results": {
                "lint": {
                    "passed": False,
                    "errors": [{"message": "undefined variable x"}],
                },
            },
            "summary": "1 of 4 failed: lint",
        }

        await run_gate_remediation(wf, ctx)

        prompt_arg = wf._step_executor.execute.call_args.kwargs["prompt"]
        assert "undefined variable x" in prompt_arg["prompt"]


# ---------------------------------------------------------------------------
# run_review_and_remediate
# ---------------------------------------------------------------------------


class TestRunReviewAndRemediate:
    async def test_skip_review_returns_immediately(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx()

        await run_review_and_remediate(wf, ctx, skip_review=True)

        wf.emit_step_started.assert_not_called()

    async def test_runs_review_and_stores_result(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx()

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
                f"{_STEPS_MOD}.record_review_findings",
                new_callable=AsyncMock,
            ),
            patch(
                f"{_STEPS_MOD}.create_beads_from_findings",
                new_callable=AsyncMock,
            ),
        ):
            await run_review_and_remediate(wf, ctx, skip_review=False)

        assert ctx.review_result is not None
        wf.emit_step_completed.assert_called_once()

    async def test_creates_beads_from_findings(self) -> None:
        wf = _make_wf()
        ctx = _make_ctx()

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
                    to_dict=lambda: {"success": True, "issues_remaining": ["F001"]}
                ),
            ),
            patch(
                f"{_STEPS_MOD}.record_review_findings",
                new_callable=AsyncMock,
            ),
            patch(
                f"{_STEPS_MOD}.create_beads_from_findings",
                new_callable=AsyncMock,
            ) as mock_create,
        ):
            await run_review_and_remediate(wf, ctx, skip_review=False)

        mock_create.assert_called_once()

    async def test_review_failure_sets_none_review_result(self) -> None:
        """Review failure must propagate via ctx.review_result=None."""
        wf = _make_wf()
        ctx = _make_ctx()

        with patch(
            f"{_STEPS_MOD}.gather_local_review_context",
            new_callable=AsyncMock,
            side_effect=RuntimeError("review agent down"),
        ):
            await run_review_and_remediate(wf, ctx, skip_review=False)

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
        """Rollback must call jj_restore_operation with ctx.operation_id."""
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
