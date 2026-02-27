"""Tests for FlyBeadsWorkflow (T010)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.dsl.checkpoint.store import MemoryCheckpointStore
from maverick.dsl.events import (
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.library.actions.types import (
    CheckEpicDoneResult,
    DependencySyncResult,
    MarkBeadCompleteResult,
    SelectNextBeadResult,
    VerifyBeadCompletionResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_select_result(
    *,
    found: bool = True,
    bead_id: str = "b1",
    title: str = "Test bead",
    description: str = "Do work",
    priority: int = 1,
    epic_id: str = "e1",
    done: bool = False,
) -> SelectNextBeadResult:
    return SelectNextBeadResult(
        found=found,
        bead_id=bead_id,
        title=title,
        description=description,
        priority=priority,
        epic_id=epic_id,
        done=done,
    )


def _make_verify_result(*, passed: bool = True) -> VerifyBeadCompletionResult:
    reasons = () if passed else ("Validation failed: lint",)
    return VerifyBeadCompletionResult(passed=passed, reasons=reasons)


def _done_select_result() -> SelectNextBeadResult:
    return SelectNextBeadResult(
        found=False,
        bead_id="",
        title="",
        description="",
        priority=0,
        epic_id="e1",
        done=True,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def checkpoint_store() -> MemoryCheckpointStore:
    return MemoryCheckpointStore()


@pytest.fixture
def mock_step_executor() -> AsyncMock:
    from maverick.dsl.executor.protocol import StepExecutor
    from maverick.dsl.executor.result import ExecutorResult

    executor = AsyncMock(spec=StepExecutor)
    # Provide a realistic return value for execute()
    executor.execute.return_value = ExecutorResult(
        success=True,
        output="Implementation complete",
        usage=None,
        events=(),
    )
    return executor


@pytest.fixture
def fly_workflow(
    mock_config: MagicMock,
    mock_registry: MagicMock,
    checkpoint_store: MemoryCheckpointStore,
    mock_step_executor: AsyncMock,
) -> Any:
    from maverick.workflows.fly_beads.workflow import FlyBeadsWorkflow

    return FlyBeadsWorkflow(
        config=mock_config,
        registry=mock_registry,
        checkpoint_store=checkpoint_store,
        step_executor=mock_step_executor,
    )


@pytest.fixture
def fly_workflow_no_executor(
    mock_config: MagicMock,
    mock_registry: MagicMock,
    checkpoint_store: MemoryCheckpointStore,
) -> Any:
    from maverick.workflows.fly_beads.workflow import FlyBeadsWorkflow

    return FlyBeadsWorkflow(
        config=mock_config,
        registry=mock_registry,
        checkpoint_store=checkpoint_store,
        step_executor=None,
    )


# Shared patch context for all "with actions mocked" tests
_PATCH_BASE = "maverick.workflows.fly_beads.workflow"


def _make_mock_actions(
    *,
    select_side_effect: list[Any] | None = None,
    verify_result: VerifyBeadCompletionResult | None = None,
    check_done_result: CheckEpicDoneResult | None = None,
) -> dict[str, Any]:
    """Build a dict of mock return values/side_effects for all actions."""
    from maverick.library.actions.preflight import PreflightCheckResult

    preflight = MagicMock(spec=PreflightCheckResult)
    preflight.to_dict.return_value = {"success": True}

    if select_side_effect is None:
        # Default: one bead then done
        select_side_effect = [
            _make_select_result(),
            _done_select_result(),
        ]

    if verify_result is None:
        verify_result = _make_verify_result(passed=True)

    if check_done_result is None:
        check_done_result = CheckEpicDoneResult(done=True, remaining_count=0)

    sync = DependencySyncResult(
        success=True,
        command="uv sync",
        output="",
        skipped=False,
        reason=None,
        error=None,
    )

    mark_complete = MarkBeadCompleteResult(success=True, bead_id="b1", error=None)

    return {
        "preflight_return": preflight,
        "workspace_return": {
            "success": True,
            "workspace_path": "/tmp/test_ws",
            "user_repo_path": "/tmp/user",
            "created": True,
            "error": None,
        },
        "select_side_effect": select_side_effect,
        "snapshot_return": {"operation_id": "op123", "success": True, "error": None},
        "describe_return": {"success": True, "error": None},
        "sync_return": sync,
        "validation_return": {
            "passed": True,
            "stages": [],
            "attempts": 0,
            "fixes_applied": [],
            "remaining_errors": [],
            "suggestions": [],
        },
        "review_context_return": MagicMock(to_dict=lambda: {}),
        "review_loop_return": MagicMock(
            to_dict=lambda: {
                "success": True,
                "recommendation": "approve",
                "issues_remaining": [],
            }
        ),
        "create_failures_return": MagicMock(created_count=0),
        "create_findings_return": MagicMock(created_count=0),
        "verify_return": verify_result,
        "commit_return": {
            "success": True,
            "message": "bead(b1): Test bead",
            "error": None,
        },
        "mark_complete_return": mark_complete,
        "check_done_return": check_done_result,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFlyBeadsWorkflow:
    async def test_happy_path(
        self, fly_workflow: Any, mock_step_executor: AsyncMock
    ) -> None:
        """Complete workflow: preflight → workspace → bead → commit → done."""
        mocks = _make_mock_actions()

        with (
            patch(
                f"{_PATCH_BASE}.run_preflight_checks",
                return_value=mocks["preflight_return"],
            ) as _m_pre,
            patch(
                f"{_PATCH_BASE}.create_fly_workspace",
                return_value=mocks["workspace_return"],
            ) as _m_ws,
            patch(
                f"{_PATCH_BASE}.select_next_bead",
                side_effect=mocks["select_side_effect"],
            ) as _m_sel,
            patch(
                f"{_PATCH_BASE}.jj_snapshot_operation",
                return_value=mocks["snapshot_return"],
            ),
            patch(f"{_PATCH_BASE}.jj_describe", return_value=mocks["describe_return"]),
            patch(
                f"{_PATCH_BASE}.sync_dependencies", return_value=mocks["sync_return"]
            ),
            patch(
                f"{_PATCH_BASE}.run_fix_retry_loop",
                return_value=mocks["validation_return"],
            ),
            patch(
                f"{_PATCH_BASE}.gather_local_review_context",
                return_value=mocks["review_context_return"],
            ),
            patch(
                f"{_PATCH_BASE}.run_review_fix_loop",
                return_value=mocks["review_loop_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_failures",
                return_value=mocks["create_failures_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_findings",
                return_value=mocks["create_findings_return"],
            ),
            patch(
                f"{_PATCH_BASE}.verify_bead_completion",
                return_value=mocks["verify_return"],
            ),
            patch(f"{_PATCH_BASE}.jj_commit_bead", return_value=mocks["commit_return"]),
            patch(
                f"{_PATCH_BASE}.mark_bead_complete",
                return_value=mocks["mark_complete_return"],
            ),
            patch(
                f"{_PATCH_BASE}.check_epic_done",
                return_value=mocks["check_done_return"],
            ),
            patch("maverick.workspace.manager.WorkspaceManager"),
        ):
            events = []
            async for event in fly_workflow.execute(
                {"epic_id": "", "max_beads": 5, "dry_run": False, "skip_review": False}
            ):
                events.append(event)

        # Should complete successfully
        completed = [e for e in events if isinstance(e, WorkflowCompleted)]
        assert len(completed) == 1
        assert completed[0].success is True

        # Workflow result should indicate success
        assert fly_workflow.result is not None
        assert fly_workflow.result.success is True
        final = fly_workflow.result.final_output
        assert isinstance(final, dict)
        assert final["beads_succeeded"] == 1
        assert final["beads_processed"] == 1

    async def test_events_emitted(self, fly_workflow: Any) -> None:
        """WorkflowStarted, StepStarted/StepCompleted, WorkflowCompleted are emitted."""
        mocks = _make_mock_actions()

        with (
            patch(
                f"{_PATCH_BASE}.run_preflight_checks",
                return_value=mocks["preflight_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_fly_workspace",
                return_value=mocks["workspace_return"],
            ),
            patch(
                f"{_PATCH_BASE}.select_next_bead",
                side_effect=mocks["select_side_effect"],
            ),
            patch(
                f"{_PATCH_BASE}.jj_snapshot_operation",
                return_value=mocks["snapshot_return"],
            ),
            patch(f"{_PATCH_BASE}.jj_describe", return_value=mocks["describe_return"]),
            patch(
                f"{_PATCH_BASE}.sync_dependencies", return_value=mocks["sync_return"]
            ),
            patch(
                f"{_PATCH_BASE}.run_fix_retry_loop",
                return_value=mocks["validation_return"],
            ),
            patch(
                f"{_PATCH_BASE}.gather_local_review_context",
                return_value=mocks["review_context_return"],
            ),
            patch(
                f"{_PATCH_BASE}.run_review_fix_loop",
                return_value=mocks["review_loop_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_failures",
                return_value=mocks["create_failures_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_findings",
                return_value=mocks["create_findings_return"],
            ),
            patch(
                f"{_PATCH_BASE}.verify_bead_completion",
                return_value=mocks["verify_return"],
            ),
            patch(f"{_PATCH_BASE}.jj_commit_bead", return_value=mocks["commit_return"]),
            patch(
                f"{_PATCH_BASE}.mark_bead_complete",
                return_value=mocks["mark_complete_return"],
            ),
            patch(
                f"{_PATCH_BASE}.check_epic_done",
                return_value=mocks["check_done_return"],
            ),
            patch("maverick.workspace.manager.WorkspaceManager"),
        ):
            events = []
            async for event in fly_workflow.execute({"epic_id": "", "max_beads": 5}):
                events.append(event)

        event_types = {type(e).__name__ for e in events}
        assert "WorkflowStarted" in event_types
        assert "StepStarted" in event_types
        assert "StepCompleted" in event_types
        assert "WorkflowCompleted" in event_types

        # Check a WorkflowStarted has correct name
        started = next(e for e in events if isinstance(e, WorkflowStarted))
        assert started.workflow_name == "fly-beads"

    async def test_dry_run_mode(self, fly_workflow: Any) -> None:
        """When dry_run=True, create_fly_workspace is NOT called."""
        mocks = _make_mock_actions(
            select_side_effect=[_done_select_result()],
        )

        with (
            patch(
                f"{_PATCH_BASE}.run_preflight_checks",
                return_value=mocks["preflight_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_fly_workspace",
                return_value=mocks["workspace_return"],
            ) as mock_ws,
            patch(
                f"{_PATCH_BASE}.select_next_bead",
                side_effect=mocks["select_side_effect"],
            ),
            patch(
                f"{_PATCH_BASE}.check_epic_done",
                return_value=mocks["check_done_return"],
            ),
        ):
            events = []
            async for event in fly_workflow.execute(
                {"epic_id": "", "max_beads": 5, "dry_run": True}
            ):
                events.append(event)

        mock_ws.assert_not_called()
        completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert completed.success is True

    async def test_skip_review_mode(self, fly_workflow: Any) -> None:
        """When skip_review=True, review step is skipped."""
        mocks = _make_mock_actions()

        with (
            patch(
                f"{_PATCH_BASE}.run_preflight_checks",
                return_value=mocks["preflight_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_fly_workspace",
                return_value=mocks["workspace_return"],
            ),
            patch(
                f"{_PATCH_BASE}.select_next_bead",
                side_effect=mocks["select_side_effect"],
            ),
            patch(
                f"{_PATCH_BASE}.jj_snapshot_operation",
                return_value=mocks["snapshot_return"],
            ),
            patch(f"{_PATCH_BASE}.jj_describe", return_value=mocks["describe_return"]),
            patch(
                f"{_PATCH_BASE}.sync_dependencies", return_value=mocks["sync_return"]
            ),
            patch(
                f"{_PATCH_BASE}.run_fix_retry_loop",
                return_value=mocks["validation_return"],
            ),
            patch(
                f"{_PATCH_BASE}.gather_local_review_context",
                return_value=mocks["review_context_return"],
            ) as mock_gather,
            patch(
                f"{_PATCH_BASE}.run_review_fix_loop",
                return_value=mocks["review_loop_return"],
            ) as mock_review,
            patch(
                f"{_PATCH_BASE}.create_beads_from_failures",
                return_value=mocks["create_failures_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_findings",
                return_value=mocks["create_findings_return"],
            ),
            patch(
                f"{_PATCH_BASE}.verify_bead_completion",
                return_value=mocks["verify_return"],
            ),
            patch(f"{_PATCH_BASE}.jj_commit_bead", return_value=mocks["commit_return"]),
            patch(
                f"{_PATCH_BASE}.mark_bead_complete",
                return_value=mocks["mark_complete_return"],
            ),
            patch(
                f"{_PATCH_BASE}.check_epic_done",
                return_value=mocks["check_done_return"],
            ),
            patch("maverick.workspace.manager.WorkspaceManager"),
        ):
            events = []
            async for event in fly_workflow.execute(
                {"epic_id": "", "max_beads": 5, "skip_review": True}
            ):
                events.append(event)

        mock_gather.assert_not_called()
        mock_review.assert_not_called()
        completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert completed.success is True

    async def test_bead_failure_triggers_jj_restore(self, fly_workflow: Any) -> None:
        """When verify_completion.passed=False, jj_restore_operation is called."""
        mocks = _make_mock_actions(
            verify_result=_make_verify_result(passed=False),
        )

        with (
            patch(
                f"{_PATCH_BASE}.run_preflight_checks",
                return_value=mocks["preflight_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_fly_workspace",
                return_value=mocks["workspace_return"],
            ),
            patch(
                f"{_PATCH_BASE}.select_next_bead",
                side_effect=mocks["select_side_effect"],
            ),
            patch(
                f"{_PATCH_BASE}.jj_snapshot_operation",
                return_value=mocks["snapshot_return"],
            ),
            patch(f"{_PATCH_BASE}.jj_describe", return_value=mocks["describe_return"]),
            patch(
                f"{_PATCH_BASE}.sync_dependencies", return_value=mocks["sync_return"]
            ),
            patch(
                f"{_PATCH_BASE}.run_fix_retry_loop",
                return_value=mocks["validation_return"],
            ),
            patch(
                f"{_PATCH_BASE}.gather_local_review_context",
                return_value=mocks["review_context_return"],
            ),
            patch(
                f"{_PATCH_BASE}.run_review_fix_loop",
                return_value=mocks["review_loop_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_failures",
                return_value=mocks["create_failures_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_findings",
                return_value=mocks["create_findings_return"],
            ),
            patch(
                f"{_PATCH_BASE}.verify_bead_completion",
                return_value=mocks["verify_return"],
            ),
            patch(
                f"{_PATCH_BASE}.jj_restore_operation", return_value={"success": True}
            ) as mock_restore,
            patch(
                f"{_PATCH_BASE}.jj_commit_bead", return_value=mocks["commit_return"]
            ) as mock_commit,
            patch(
                f"{_PATCH_BASE}.mark_bead_complete",
                return_value=mocks["mark_complete_return"],
            ) as mock_mark,
            patch(
                f"{_PATCH_BASE}.check_epic_done",
                return_value=mocks["check_done_return"],
            ),
            patch("maverick.workspace.manager.WorkspaceManager"),
        ):
            events = []
            async for event in fly_workflow.execute({"epic_id": "", "max_beads": 5}):
                events.append(event)

        # jj_restore_operation must have been called
        mock_restore.assert_called_once()
        # commit and mark_bead_complete should NOT be called
        mock_commit.assert_not_called()
        mock_mark.assert_not_called()

        # Workflow itself still completes (bead failure is non-fatal)
        completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert completed.success is True
        assert fly_workflow.result.final_output["beads_failed"] == 1

    async def test_workspace_rollback_on_exception(self, fly_workflow: Any) -> None:
        """If preflight raises, WorkflowCompleted(success=False) is emitted and
        the exception is re-raised after (R-012)."""
        mock_teardown = AsyncMock()
        mock_ws_manager = MagicMock()
        mock_ws_manager.teardown = mock_teardown

        events: list[Any] = []

        with (
            patch(
                f"{_PATCH_BASE}.run_preflight_checks",
                side_effect=RuntimeError("API key missing"),
            ),
            patch(
                "maverick.workspace.manager.WorkspaceManager",
                return_value=mock_ws_manager,
            ),
            pytest.raises(RuntimeError, match="API key missing"),
        ):
            async for event in fly_workflow.execute({"epic_id": "", "max_beads": 5}):
                events.append(event)

        # WorkflowCompleted(success=False) must have been yielded before re-raise
        completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert completed.success is False

    async def test_workspace_rollback_on_workspace_creation_exception(
        self, fly_workflow: Any
    ) -> None:
        """If create_fly_workspace raises, WorkflowCompleted(success=False) is emitted
        and the exception is re-raised after (R-012)."""
        from maverick.library.actions.preflight import PreflightCheckResult

        preflight_mock = MagicMock(spec=PreflightCheckResult)
        preflight_mock.to_dict.return_value = {"success": True}

        events: list[Any] = []

        with (
            patch(f"{_PATCH_BASE}.run_preflight_checks", return_value=preflight_mock),
            patch(
                f"{_PATCH_BASE}.create_fly_workspace",
                side_effect=RuntimeError("clone failed"),
            ),
            patch("maverick.workspace.manager.WorkspaceManager"),
            pytest.raises(RuntimeError, match="clone failed"),
        ):
            async for event in fly_workflow.execute({"epic_id": "", "max_beads": 5}):
                events.append(event)

        completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert completed.success is False

    async def test_checkpoint_after_each_bead(
        self, fly_workflow: Any, checkpoint_store: MemoryCheckpointStore
    ) -> None:
        """save_checkpoint is called after each bead."""
        mocks = _make_mock_actions()

        with (
            patch(
                f"{_PATCH_BASE}.run_preflight_checks",
                return_value=mocks["preflight_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_fly_workspace",
                return_value=mocks["workspace_return"],
            ),
            patch(
                f"{_PATCH_BASE}.select_next_bead",
                side_effect=mocks["select_side_effect"],
            ),
            patch(
                f"{_PATCH_BASE}.jj_snapshot_operation",
                return_value=mocks["snapshot_return"],
            ),
            patch(f"{_PATCH_BASE}.jj_describe", return_value=mocks["describe_return"]),
            patch(
                f"{_PATCH_BASE}.sync_dependencies", return_value=mocks["sync_return"]
            ),
            patch(
                f"{_PATCH_BASE}.run_fix_retry_loop",
                return_value=mocks["validation_return"],
            ),
            patch(
                f"{_PATCH_BASE}.gather_local_review_context",
                return_value=mocks["review_context_return"],
            ),
            patch(
                f"{_PATCH_BASE}.run_review_fix_loop",
                return_value=mocks["review_loop_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_failures",
                return_value=mocks["create_failures_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_findings",
                return_value=mocks["create_findings_return"],
            ),
            patch(
                f"{_PATCH_BASE}.verify_bead_completion",
                return_value=mocks["verify_return"],
            ),
            patch(f"{_PATCH_BASE}.jj_commit_bead", return_value=mocks["commit_return"]),
            patch(
                f"{_PATCH_BASE}.mark_bead_complete",
                return_value=mocks["mark_complete_return"],
            ),
            patch(
                f"{_PATCH_BASE}.check_epic_done",
                return_value=mocks["check_done_return"],
            ),
            patch("maverick.workspace.manager.WorkspaceManager"),
        ):
            async for _ in fly_workflow.execute({"epic_id": "", "max_beads": 5}):
                pass

        # A checkpoint should have been saved
        cp = await checkpoint_store.load_latest("fly-beads")
        assert cp is not None

    async def test_resume_skips_completed_beads(
        self, fly_workflow: Any, checkpoint_store: MemoryCheckpointStore
    ) -> None:
        """If checkpoint contains completed bead IDs, they are skipped."""
        # select_next_bead returns bead b1 first, then done
        select_side_effect = [
            _make_select_result(bead_id="b1"),
            _done_select_result(),
        ]
        mocks = _make_mock_actions(select_side_effect=select_side_effect)

        # Mock load_checkpoint to return b1 as already completed
        checkpoint_data = {
            "completed_bead_ids": ["b1"],
            "workspace_path": None,
            "epic_id": "",
        }

        with (
            patch(
                f"{_PATCH_BASE}.run_preflight_checks",
                return_value=mocks["preflight_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_fly_workspace",
                return_value=mocks["workspace_return"],
            ),
            patch(f"{_PATCH_BASE}.select_next_bead", side_effect=select_side_effect),
            patch(
                f"{_PATCH_BASE}.jj_snapshot_operation",
                return_value=mocks["snapshot_return"],
            ) as mock_snap,
            patch(f"{_PATCH_BASE}.jj_describe", return_value=mocks["describe_return"]),
            patch(
                f"{_PATCH_BASE}.sync_dependencies", return_value=mocks["sync_return"]
            ),
            patch(
                f"{_PATCH_BASE}.run_fix_retry_loop",
                return_value=mocks["validation_return"],
            ),
            patch(
                f"{_PATCH_BASE}.gather_local_review_context",
                return_value=mocks["review_context_return"],
            ),
            patch(
                f"{_PATCH_BASE}.run_review_fix_loop",
                return_value=mocks["review_loop_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_failures",
                return_value=mocks["create_failures_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_findings",
                return_value=mocks["create_findings_return"],
            ),
            patch(
                f"{_PATCH_BASE}.verify_bead_completion",
                return_value=mocks["verify_return"],
            ),
            patch(f"{_PATCH_BASE}.jj_commit_bead", return_value=mocks["commit_return"]),
            patch(
                f"{_PATCH_BASE}.mark_bead_complete",
                return_value=mocks["mark_complete_return"],
            ),
            patch(
                f"{_PATCH_BASE}.check_epic_done",
                return_value=mocks["check_done_return"],
            ),
            patch("maverick.workspace.manager.WorkspaceManager"),
            patch.object(
                fly_workflow, "load_checkpoint", AsyncMock(return_value=checkpoint_data)
            ),
        ):
            async for _ in fly_workflow.execute({"epic_id": "", "max_beads": 5}):
                pass

        # bead b1 was skipped so snapshot was never taken for it
        mock_snap.assert_not_called()

        # No beads completed in this run (b1 was already done)
        assert fly_workflow.result is not None
        final = fly_workflow.result.final_output
        assert final["beads_succeeded"] == 0
        assert final["beads_processed"] == 1  # 0 succeeded + 0 failed + 1 skipped

    async def test_max_beads_limit(self, fly_workflow: Any) -> None:
        """Stops after max_beads even if epic not done."""
        # Return distinct beads (different IDs each time) so none get skipped
        select_side_effect = [
            _make_select_result(bead_id=f"b{i}", title=f"Bead {i}", done=False)
            for i in range(10)
        ]
        mocks = _make_mock_actions(
            select_side_effect=select_side_effect,
            check_done_result=CheckEpicDoneResult(done=False, remaining_count=5),
        )

        with (
            patch(
                f"{_PATCH_BASE}.run_preflight_checks",
                return_value=mocks["preflight_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_fly_workspace",
                return_value=mocks["workspace_return"],
            ),
            patch(
                f"{_PATCH_BASE}.select_next_bead",
                side_effect=mocks["select_side_effect"],
            ),
            patch(
                f"{_PATCH_BASE}.jj_snapshot_operation",
                return_value=mocks["snapshot_return"],
            ),
            patch(f"{_PATCH_BASE}.jj_describe", return_value=mocks["describe_return"]),
            patch(
                f"{_PATCH_BASE}.sync_dependencies", return_value=mocks["sync_return"]
            ),
            patch(
                f"{_PATCH_BASE}.run_fix_retry_loop",
                return_value=mocks["validation_return"],
            ),
            patch(
                f"{_PATCH_BASE}.gather_local_review_context",
                return_value=mocks["review_context_return"],
            ),
            patch(
                f"{_PATCH_BASE}.run_review_fix_loop",
                return_value=mocks["review_loop_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_failures",
                return_value=mocks["create_failures_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_findings",
                return_value=mocks["create_findings_return"],
            ),
            patch(
                f"{_PATCH_BASE}.verify_bead_completion",
                return_value=mocks["verify_return"],
            ),
            patch(f"{_PATCH_BASE}.jj_commit_bead", return_value=mocks["commit_return"]),
            patch(
                f"{_PATCH_BASE}.mark_bead_complete",
                return_value=mocks["mark_complete_return"],
            ),
            patch(
                f"{_PATCH_BASE}.check_epic_done",
                return_value=mocks["check_done_return"],
            ),
            patch("maverick.workspace.manager.WorkspaceManager"),
        ):
            async for _ in fly_workflow.execute(
                {"epic_id": "", "max_beads": 3, "skip_review": True}
            ):
                pass

        assert fly_workflow.result is not None
        final = fly_workflow.result.final_output
        # Should have processed exactly 3 beads (max_beads limit)
        assert final["beads_succeeded"] == 3
        assert final["beads_processed"] == 3

    async def test_no_executor_skips_implement(
        self, fly_workflow_no_executor: Any
    ) -> None:
        """When step_executor is None, the implement step is skipped with a warning."""
        mocks = _make_mock_actions()

        with (
            patch(
                f"{_PATCH_BASE}.run_preflight_checks",
                return_value=mocks["preflight_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_fly_workspace",
                return_value=mocks["workspace_return"],
            ),
            patch(
                f"{_PATCH_BASE}.select_next_bead",
                side_effect=mocks["select_side_effect"],
            ),
            patch(
                f"{_PATCH_BASE}.jj_snapshot_operation",
                return_value=mocks["snapshot_return"],
            ),
            patch(f"{_PATCH_BASE}.jj_describe", return_value=mocks["describe_return"]),
            patch(
                f"{_PATCH_BASE}.sync_dependencies", return_value=mocks["sync_return"]
            ),
            patch(
                f"{_PATCH_BASE}.run_fix_retry_loop",
                return_value=mocks["validation_return"],
            ),
            patch(
                f"{_PATCH_BASE}.gather_local_review_context",
                return_value=mocks["review_context_return"],
            ),
            patch(
                f"{_PATCH_BASE}.run_review_fix_loop",
                return_value=mocks["review_loop_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_failures",
                return_value=mocks["create_failures_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_findings",
                return_value=mocks["create_findings_return"],
            ),
            patch(
                f"{_PATCH_BASE}.verify_bead_completion",
                return_value=mocks["verify_return"],
            ),
            patch(f"{_PATCH_BASE}.jj_commit_bead", return_value=mocks["commit_return"]),
            patch(
                f"{_PATCH_BASE}.mark_bead_complete",
                return_value=mocks["mark_complete_return"],
            ),
            patch(
                f"{_PATCH_BASE}.check_epic_done",
                return_value=mocks["check_done_return"],
            ),
            patch("maverick.workspace.manager.WorkspaceManager"),
        ):
            events = []
            async for event in fly_workflow_no_executor.execute(
                {"epic_id": "", "max_beads": 5}
            ):
                events.append(event)

        completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert completed.success is True

    async def test_multiple_beads_processed(self, fly_workflow: Any) -> None:
        """Multiple beads are processed in order."""
        select_side_effect = [
            _make_select_result(bead_id="b1", title="First"),
            _make_select_result(bead_id="b2", title="Second"),
            _done_select_result(),
        ]
        mocks = _make_mock_actions(select_side_effect=select_side_effect)

        committed_messages: list[str] = []

        async def capture_commit(**kwargs: Any) -> dict[str, Any]:
            committed_messages.append(kwargs.get("message", ""))
            return {"success": True, "message": kwargs.get("message"), "error": None}

        with (
            patch(
                f"{_PATCH_BASE}.run_preflight_checks",
                return_value=mocks["preflight_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_fly_workspace",
                return_value=mocks["workspace_return"],
            ),
            patch(f"{_PATCH_BASE}.select_next_bead", side_effect=select_side_effect),
            patch(
                f"{_PATCH_BASE}.jj_snapshot_operation",
                return_value=mocks["snapshot_return"],
            ),
            patch(f"{_PATCH_BASE}.jj_describe", return_value=mocks["describe_return"]),
            patch(
                f"{_PATCH_BASE}.sync_dependencies", return_value=mocks["sync_return"]
            ),
            patch(
                f"{_PATCH_BASE}.run_fix_retry_loop",
                return_value=mocks["validation_return"],
            ),
            patch(
                f"{_PATCH_BASE}.gather_local_review_context",
                return_value=mocks["review_context_return"],
            ),
            patch(
                f"{_PATCH_BASE}.run_review_fix_loop",
                return_value=mocks["review_loop_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_failures",
                return_value=mocks["create_failures_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_beads_from_findings",
                return_value=mocks["create_findings_return"],
            ),
            patch(
                f"{_PATCH_BASE}.verify_bead_completion",
                return_value=mocks["verify_return"],
            ),
            patch(f"{_PATCH_BASE}.jj_commit_bead", side_effect=capture_commit),
            patch(
                f"{_PATCH_BASE}.mark_bead_complete",
                return_value=mocks["mark_complete_return"],
            ),
            patch(
                f"{_PATCH_BASE}.check_epic_done",
                side_effect=[
                    CheckEpicDoneResult(done=False, remaining_count=1),
                    CheckEpicDoneResult(done=True, remaining_count=0),
                ],
            ),
            patch("maverick.workspace.manager.WorkspaceManager"),
        ):
            async for _ in fly_workflow.execute({"epic_id": "", "max_beads": 5}):
                pass

        assert fly_workflow.result.final_output["beads_succeeded"] == 2
        assert fly_workflow.result.final_output["beads_processed"] == 2
        # Both beads should have been committed
        assert len(committed_messages) == 2
        assert "b1" in committed_messages[0]
        assert "b2" in committed_messages[1]

    async def test_epic_id_passed_to_select_next_bead(self, fly_workflow: Any) -> None:
        """When epic_id is passed as input, select_next_bead is called with it."""
        mocks = _make_mock_actions(
            select_side_effect=[_done_select_result()],
        )

        with (
            patch(
                f"{_PATCH_BASE}.run_preflight_checks",
                return_value=mocks["preflight_return"],
            ),
            patch(
                f"{_PATCH_BASE}.create_fly_workspace",
                return_value=mocks["workspace_return"],
            ),
            patch(
                f"{_PATCH_BASE}.select_next_bead",
                side_effect=mocks["select_side_effect"],
            ) as mock_select,
            patch(
                f"{_PATCH_BASE}.check_epic_done",
                return_value=mocks["check_done_return"],
            ),
            patch("maverick.workspace.manager.WorkspaceManager"),
        ):
            async for _ in fly_workflow.execute(
                {"epic_id": "epic-42", "max_beads": 5, "dry_run": True}
            ):
                pass

        # select_next_bead must have been called with the provided epic_id
        mock_select.assert_called_once_with(epic_id="epic-42")
