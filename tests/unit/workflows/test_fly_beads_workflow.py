"""Tests for FlyBeadsWorkflow (T010)."""

from __future__ import annotations

import contextlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.checkpoint.store import MemoryCheckpointStore
from maverick.events import (
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

_WF_MOD = "maverick.workflows.fly_beads.workflow"
_STEPS_MOD = "maverick.workflows.fly_beads.steps"


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
        select_side_effect = [
            _make_select_result(),
            _done_select_result(),
        ]

    if verify_result is None:
        verify_result = _make_verify_result(passed=True)

    if check_done_result is None:
        check_done_result = CheckEpicDoneResult(
            done=True,
            remaining_count=0,
            all_children_closed=True,
            total_children=1,
            closed_children=1,
        )

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
# Shared patching context manager
# ---------------------------------------------------------------------------

# Mapping from short name -> (target, mock-dict key, patch-kwarg)
# Most entries use return_value; select_next_bead uses side_effect.
_RV = "return_value"
_SE = "side_effect"

# Actions imported by workflow.py (preflight, workspace, select, check_done,
# mark_complete) are patched in the workflow module. Actions imported by
# steps.py are patched in the steps module.
_PATCH_SPECS: list[tuple[str, str, str | None, str]] = [
    # (short_name, patch_target, mock_dict_key, patch_kwarg)
    ("preflight", f"{_WF_MOD}.run_preflight_checks", "preflight_return", _RV),
    ("workspace", f"{_WF_MOD}.create_fly_workspace", "workspace_return", _RV),
    ("select", f"{_WF_MOD}.select_next_bead", "select_side_effect", _SE),
    ("snapshot", f"{_STEPS_MOD}.jj_snapshot_operation", "snapshot_return", _RV),
    ("describe", f"{_STEPS_MOD}.jj_describe", "describe_return", _RV),
    ("sync_deps", f"{_STEPS_MOD}.sync_dependencies", "sync_return", _RV),
    ("validation", f"{_STEPS_MOD}.run_fix_retry_loop", "validation_return", _RV),
    (
        "gather_ctx",
        f"{_STEPS_MOD}.gather_local_review_context",
        "review_context_return",
        _RV,
    ),
    ("review_loop", f"{_STEPS_MOD}.run_review_fix_loop", "review_loop_return", _RV),
    (
        "create_failures",
        f"{_STEPS_MOD}.create_beads_from_failures",
        "create_failures_return",
        _RV,
    ),
    (
        "create_findings",
        f"{_STEPS_MOD}.create_beads_from_findings",
        "create_findings_return",
        _RV,
    ),
    ("verify", f"{_STEPS_MOD}.verify_bead_completion", "verify_return", _RV),
    ("commit", f"{_STEPS_MOD}.jj_commit_bead", "commit_return", _RV),
    (
        "mark_complete_steps",
        f"{_STEPS_MOD}.mark_bead_complete",
        "mark_complete_return",
        _RV,
    ),
    ("mark_complete", f"{_WF_MOD}.mark_bead_complete", "mark_complete_return", _RV),
    ("check_done", f"{_WF_MOD}.check_epic_done", "check_done_return", _RV),
    ("restore", f"{_STEPS_MOD}.jj_restore_operation", None, _RV),
    ("ws_manager", "maverick.workspace.manager.WorkspaceManager", None, _RV),
]


@contextlib.contextmanager
def _patch_all_actions(
    mock_values: dict[str, Any] | None = None,
    **overrides: Any,
) -> Any:
    """Apply all standard fly-beads action mocks, yielding a dict of mock objects.

    Args:
        mock_values: Dict from ``_make_mock_actions()`` providing default return
            values. If *None*, ``_make_mock_actions()`` is called with no args.
        **overrides: Per-action overrides keyed by the short name from
            ``_PATCH_SPECS``.  Each value may be:
            - A plain value used as *return_value* (or *side_effect* for
              ``select``).
            - A dict ``{"side_effect": ...}`` or ``{"return_value": ...}``
              to override the patch kwarg explicitly.

    Yields:
        A ``dict[str, MagicMock]`` keyed by short name so tests can assert on
        individual mocks (e.g. ``mocks["commit"].assert_not_called()``).
    """
    if mock_values is None:
        mock_values = _make_mock_actions()

    patchers: list[Any] = []
    mock_objs: dict[str, Any] = {}

    for short_name, target, default_key, default_kwarg in _PATCH_SPECS:
        # Determine the kwargs to pass to patch()
        if short_name in overrides:
            ov = overrides[short_name]
            if isinstance(ov, dict) and ("side_effect" in ov or "return_value" in ov):
                kw = ov
            else:
                kw = {default_kwarg: ov}
        elif default_key is not None and default_key in mock_values:
            kw = {default_kwarg: mock_values[default_key]}
        else:
            # No default value configured (e.g. restore, ws_manager) — just patch
            kw = {}

        p = patch(target, **kw)
        patchers.append((short_name, p))

    # Enter all patchers and build the mock-objects dict
    entered: list[Any] = []
    try:
        for short_name, p in patchers:
            mock_obj = p.start()
            entered.append(p)
            mock_objs[short_name] = mock_obj
        yield mock_objs
    finally:
        for p in reversed(entered):
            p.stop()


async def _collect_events(workflow: Any, inputs: dict[str, Any]) -> list[Any]:
    """Execute a workflow and return all emitted events."""
    events: list[Any] = []
    async for event in workflow.execute(inputs):
        events.append(event)
    return events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def checkpoint_store() -> MemoryCheckpointStore:
    return MemoryCheckpointStore()


@pytest.fixture
def mock_step_executor() -> AsyncMock:
    from maverick.executor.protocol import StepExecutor
    from maverick.executor.result import ExecutorResult

    executor = AsyncMock(spec=StepExecutor)
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFlyBeadsWorkflow:
    async def test_happy_path(
        self, fly_workflow: Any, mock_step_executor: AsyncMock
    ) -> None:
        """Complete workflow: preflight -> workspace -> bead -> commit -> done."""
        with _patch_all_actions():
            events = await _collect_events(
                fly_workflow,
                {"epic_id": "", "max_beads": 5, "dry_run": False, "skip_review": False},
            )

        completed = [e for e in events if isinstance(e, WorkflowCompleted)]
        assert len(completed) == 1
        assert completed[0].success is True

        assert fly_workflow.result is not None
        assert fly_workflow.result.success is True
        final = fly_workflow.result.final_output
        assert isinstance(final, dict)
        assert final["beads_succeeded"] == 1
        assert final["beads_processed"] == 1

    async def test_events_emitted(self, fly_workflow: Any) -> None:
        """WorkflowStarted, StepStarted/StepCompleted, WorkflowCompleted are emitted."""
        with _patch_all_actions():
            events = await _collect_events(
                fly_workflow, {"epic_id": "", "max_beads": 5}
            )

        event_types = {type(e).__name__ for e in events}
        assert "WorkflowStarted" in event_types
        assert "StepStarted" in event_types
        assert "StepCompleted" in event_types
        assert "WorkflowCompleted" in event_types

        started = next(e for e in events if isinstance(e, WorkflowStarted))
        assert started.workflow_name == "fly-beads"

    async def test_dry_run_mode(self, fly_workflow: Any) -> None:
        """When dry_run=True, create_fly_workspace is NOT called."""
        mv = _make_mock_actions(select_side_effect=[_done_select_result()])

        with _patch_all_actions(mv) as mocks:
            events = await _collect_events(
                fly_workflow,
                {"epic_id": "", "max_beads": 5, "dry_run": True},
            )

        mocks["workspace"].assert_not_called()
        completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert completed.success is True

    async def test_skip_review_mode(self, fly_workflow: Any) -> None:
        """When skip_review=True, review step is skipped."""
        with _patch_all_actions() as mocks:
            events = await _collect_events(
                fly_workflow,
                {"epic_id": "", "max_beads": 5, "skip_review": True},
            )

        mocks["gather_ctx"].assert_not_called()
        mocks["review_loop"].assert_not_called()
        completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert completed.success is True

    async def test_bead_failure_triggers_jj_restore(self, fly_workflow: Any) -> None:
        """When verify_completion.passed=False, jj_restore_operation is called."""
        mv = _make_mock_actions(verify_result=_make_verify_result(passed=False))

        with _patch_all_actions(
            mv,
            restore={"return_value": {"success": True}},
        ) as mocks:
            events = await _collect_events(
                fly_workflow, {"epic_id": "", "max_beads": 5}
            )

        mocks["restore"].assert_called_once()
        mocks["commit"].assert_not_called()
        mocks["mark_complete_steps"].assert_not_called()

        completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert completed.success is True
        assert fly_workflow.result.final_output["beads_failed"] == 1

    async def test_workspace_rollback_on_exception(self, fly_workflow: Any) -> None:
        """If preflight raises, WorkflowCompleted(success=False) is emitted and
        the exception is re-raised after (R-012)."""
        events: list[Any] = []

        with (
            _patch_all_actions(
                preflight={"side_effect": RuntimeError("API key missing")},
            ),
            pytest.raises(RuntimeError, match="API key missing"),
        ):
            async for event in fly_workflow.execute({"epic_id": "", "max_beads": 5}):
                events.append(event)

        completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert completed.success is False

    async def test_workspace_rollback_on_workspace_creation_exception(
        self, fly_workflow: Any
    ) -> None:
        """If create_fly_workspace raises, WorkflowCompleted(success=False) is emitted
        and the exception is re-raised after (R-012)."""
        events: list[Any] = []

        with (
            _patch_all_actions(
                workspace={"side_effect": RuntimeError("clone failed")},
            ),
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
        with _patch_all_actions():
            async for _ in fly_workflow.execute({"epic_id": "", "max_beads": 5}):
                pass

        cp = await checkpoint_store.load_latest("fly-beads")
        assert cp is not None

    async def test_resume_skips_completed_beads(
        self, fly_workflow: Any, checkpoint_store: MemoryCheckpointStore
    ) -> None:
        """If checkpoint contains completed bead IDs, they are skipped."""
        select_side_effect = [
            _make_select_result(bead_id="b1"),
            _done_select_result(),
        ]
        mv = _make_mock_actions(select_side_effect=select_side_effect)

        checkpoint_data = {
            "completed_bead_ids": ["b1"],
            "workspace_path": None,
            "epic_id": "",
        }

        with (
            _patch_all_actions(mv) as mocks,
            patch.object(
                fly_workflow, "load_checkpoint", AsyncMock(return_value=checkpoint_data)
            ),
        ):
            async for _ in fly_workflow.execute({"epic_id": "", "max_beads": 5}):
                pass

        # bead b1 was skipped so snapshot was never taken for it
        mocks["snapshot"].assert_not_called()

        assert fly_workflow.result is not None
        final = fly_workflow.result.final_output
        assert final["beads_succeeded"] == 0
        assert final["beads_processed"] == 1  # 0 succeeded + 0 failed + 1 skipped

    async def test_max_beads_limit(self, fly_workflow: Any) -> None:
        """Stops after max_beads even if epic not done."""
        select_side_effect = [
            _make_select_result(bead_id=f"b{i}", title=f"Bead {i}", done=False)
            for i in range(10)
        ]
        mv = _make_mock_actions(
            select_side_effect=select_side_effect,
            check_done_result=CheckEpicDoneResult(
                done=False,
                remaining_count=5,
                all_children_closed=False,
                total_children=10,
                closed_children=5,
            ),
        )

        with _patch_all_actions(mv):
            async for _ in fly_workflow.execute(
                {"epic_id": "", "max_beads": 3, "skip_review": True}
            ):
                pass

        assert fly_workflow.result is not None
        final = fly_workflow.result.final_output
        assert final["beads_succeeded"] == 3
        assert final["beads_processed"] == 3

    async def test_no_executor_skips_implement(
        self, fly_workflow_no_executor: Any
    ) -> None:
        """When step_executor is None, the implement step is skipped with a warning."""
        with _patch_all_actions():
            events = await _collect_events(
                fly_workflow_no_executor, {"epic_id": "", "max_beads": 5}
            )

        completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert completed.success is True

    async def test_multiple_beads_processed(self, fly_workflow: Any) -> None:
        """Multiple beads are processed in order."""
        select_side_effect = [
            _make_select_result(bead_id="b1", title="First"),
            _make_select_result(bead_id="b2", title="Second"),
            _done_select_result(),
        ]
        mv = _make_mock_actions(select_side_effect=select_side_effect)

        committed_messages: list[str] = []

        async def capture_commit(**kwargs: Any) -> dict[str, Any]:
            committed_messages.append(kwargs.get("message", ""))
            return {"success": True, "message": kwargs.get("message"), "error": None}

        with _patch_all_actions(
            mv,
            commit={"side_effect": capture_commit},
            check_done={
                "side_effect": [
                    CheckEpicDoneResult(
                        done=False,
                        remaining_count=1,
                        all_children_closed=False,
                        total_children=2,
                        closed_children=1,
                    ),
                    CheckEpicDoneResult(
                        done=True,
                        remaining_count=0,
                        all_children_closed=True,
                        total_children=2,
                        closed_children=2,
                    ),
                ]
            },
        ):
            async for _ in fly_workflow.execute({"epic_id": "", "max_beads": 5}):
                pass

        assert fly_workflow.result.final_output["beads_succeeded"] == 2
        assert fly_workflow.result.final_output["beads_processed"] == 2
        assert len(committed_messages) == 2
        assert "b1" in committed_messages[0]
        assert "b2" in committed_messages[1]

    async def test_epic_id_passed_to_select_next_bead(self, fly_workflow: Any) -> None:
        """When epic_id is passed as input, select_next_bead is called with it."""
        mv = _make_mock_actions(select_side_effect=[_done_select_result()])

        with _patch_all_actions(mv) as mocks:
            async for _ in fly_workflow.execute(
                {"epic_id": "epic-42", "max_beads": 5, "dry_run": True}
            ):
                pass

        mocks["select"].assert_called_once_with(epic_id="epic-42")

    async def test_epic_closed_when_all_children_done(self, fly_workflow: Any) -> None:
        """Epic bead is closed when all child beads are closed."""
        mv = _make_mock_actions(
            check_done_result=CheckEpicDoneResult(
                done=True,
                remaining_count=0,
                all_children_closed=True,
                total_children=1,
                closed_children=1,
            ),
        )

        with _patch_all_actions(mv) as mocks:
            async for _ in fly_workflow.execute({"epic_id": "epic-99", "max_beads": 5}):
                pass

        # mark_bead_complete called twice: once for the work bead (steps),
        # once for epic (workflow)
        # Check the workflow-level mock for epic close
        calls = mocks["mark_complete"].call_args_list
        epic_calls = [c for c in calls if c.kwargs.get("bead_id") == "epic-99"]
        assert len(epic_calls) == 1
        assert "All child beads completed" in epic_calls[0].kwargs.get("reason", "")

    async def test_epic_not_closed_when_children_still_open(
        self, fly_workflow: Any
    ) -> None:
        """Epic bead stays open when some children are blocked."""
        mv = _make_mock_actions(
            check_done_result=CheckEpicDoneResult(
                done=True,
                remaining_count=0,
                all_children_closed=False,
                total_children=2,
                closed_children=1,
            ),
        )

        with _patch_all_actions(mv) as mocks:
            async for _ in fly_workflow.execute({"epic_id": "epic-99", "max_beads": 5}):
                pass

        # mark_bead_complete called only for the work bead (in steps), not the epic
        calls = mocks["mark_complete"].call_args_list
        epic_calls = [c for c in calls if c.kwargs.get("bead_id") == "epic-99"]
        assert len(epic_calls) == 0

    async def test_epic_not_closed_without_epic_id(self, fly_workflow: Any) -> None:
        """Epic is not closed when no epic_id was provided."""
        mv = _make_mock_actions(
            check_done_result=CheckEpicDoneResult(
                done=True,
                remaining_count=0,
                all_children_closed=True,
                total_children=1,
                closed_children=1,
            ),
        )

        with _patch_all_actions(mv) as mocks:
            async for _ in fly_workflow.execute({"epic_id": "", "max_beads": 5}):
                pass

        # mark_bead_complete called only for the work bead (empty epic_id)
        calls = mocks["mark_complete"].call_args_list
        # The work bead call uses bead_id="b1", no epic close call
        for c in calls:
            assert c.kwargs.get("bead_id") != ""
            assert c.kwargs.get("reason", "") != "All child beads completed"
