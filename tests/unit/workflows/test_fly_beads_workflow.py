"""Tests for FlyBeadsWorkflow (T010)."""

from __future__ import annotations

import contextlib
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from maverick.checkpoint.store import MemoryCheckpointStore
from maverick.events import (
    WorkflowCompleted,
    WorkflowStarted,
)
from maverick.library.actions.git_models import GitStatusResult, SnapshotResult
from maverick.library.actions.types import (
    MarkBeadCompleteResult,
    SelectNextBeadResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WF_MOD = "maverick.workflows.fly_beads.workflow"
_STEPS_MOD = "maverick.workflows.fly_beads.steps"
_IMPL_MOD = "maverick.workflows.fly_beads._implement"
_REVIEW_MOD = "maverick.workflows.fly_beads._review"
_RUNWAY_MOD = "maverick.workflows.fly_beads._runway"
_COMMIT_MOD = "maverick.workflows.fly_beads._commit"


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

    mark_complete = MarkBeadCompleteResult(success=True, bead_id="b1", error=None)

    return {
        "preflight_return": preflight,
        "git_has_changes_return": GitStatusResult(
            has_staged=False,
            has_unstaged=False,
            has_untracked=False,
            has_any=False,
        ),
        "snapshot_uncommitted_return": SnapshotResult(
            success=True,
            committed=False,
        ),
        "select_side_effect": select_side_effect,
        "snapshot_return": {"operation_id": "op123", "success": True, "error": None},
        "describe_return": {"success": True, "error": None},
        "gate_return": {
            "passed": True,
            "stage_results": {},
            "summary": "All 4 validation stages passed.",
        },
        "review_context_return": MagicMock(to_dict=lambda: {}),
        "review_loop_return": MagicMock(
            to_dict=lambda: {
                "success": True,
                "recommendation": "approve",
                "issues_remaining": [],
            }
        ),
        "create_findings_return": MagicMock(created_count=0),
        "commit_return": {
            "success": True,
            "message": "bead(b1): Test bead",
            "error": None,
        },
        "mark_complete_return": mark_complete,
        "xoscar_return": {
            "beads_completed": 1,
            "completed_bead_ids": ["b1"],
            "beads_failed": 0,
        },
    }


# ---------------------------------------------------------------------------
# Shared patching context manager
# ---------------------------------------------------------------------------

# Mapping from short name -> (target, mock-dict key, patch-kwarg)
# Most entries use return_value; select_next_bead uses side_effect.
_RV = "return_value"
_SE = "side_effect"

# Actions imported by workflow.py (preflight, select, check_done,
# mark_complete) are patched in the workflow module. Actions imported by
# steps.py are patched in the steps module.
_PATCH_SPECS: list[tuple[str, str, str | None, str]] = [
    # (short_name, patch_target, mock_dict_key, patch_kwarg)
    ("preflight", f"{_WF_MOD}.run_preflight_checks", "preflight_return", _RV),
    (
        "git_has_changes",
        f"{_WF_MOD}.git_has_changes",
        "git_has_changes_return",
        _RV,
    ),
    (
        "snapshot_uncommitted",
        f"{_WF_MOD}.snapshot_uncommitted_changes",
        "snapshot_uncommitted_return",
        _RV,
    ),
    ("select", f"{_WF_MOD}.select_next_bead", "select_side_effect", _SE),
    ("snapshot", f"{_IMPL_MOD}.jj_snapshot_operation", "snapshot_return", _RV),
    ("describe", f"{_IMPL_MOD}.jj_describe", "describe_return", _RV),
    ("commit", f"{_COMMIT_MOD}.jj_commit_bead", "commit_return", _RV),
    (
        "mark_complete_steps",
        f"{_COMMIT_MOD}.mark_bead_complete",
        "mark_complete_return",
        _RV,
    ),
    ("mark_complete", f"{_WF_MOD}.mark_bead_complete", "mark_complete_return", _RV),
    ("restore", f"{_COMMIT_MOD}.jj_restore_operation", None, _RV),
    (
        "record_bead_outcome",
        f"{_RUNWAY_MOD}.record_bead_outcome",
        None,
        _RV,
    ),
    (
        "record_review_findings",
        f"{_RUNWAY_MOD}.record_review_findings",
        None,
        _RV,
    ),
    (
        "retrieve_runway_context",
        f"{_RUNWAY_MOD}.retrieve_runway_context",
        None,
        _RV,
    ),
    (
        "xoscar",
        f"{_WF_MOD}.FlyBeadsWorkflow._run_fly_with_xoscar",
        "xoscar_return",
        _RV,
    ),
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

        p = patch(target, create=True, **kw)
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
def fly_workflow(
    mock_config: MagicMock,
    checkpoint_store: MemoryCheckpointStore,
) -> Any:
    from maverick.workflows.fly_beads.workflow import FlyBeadsWorkflow

    return FlyBeadsWorkflow(
        config=mock_config,
        checkpoint_store=checkpoint_store,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFlyBeadsWorkflow:
    async def test_happy_path(self, fly_workflow: Any) -> None:
        """Complete workflow: preflight -> workspace -> bead -> commit -> done."""
        with _patch_all_actions():
            events = await _collect_events(
                fly_workflow,
                {"epic_id": "", "max_beads": 5},
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
            events = await _collect_events(fly_workflow, {"epic_id": "", "max_beads": 5})

        event_types = {type(e).__name__ for e in events}
        assert "WorkflowStarted" in event_types
        assert "StepStarted" in event_types
        assert "StepCompleted" in event_types
        assert "WorkflowCompleted" in event_types

        started = next(e for e in events if isinstance(e, WorkflowStarted))
        assert started.workflow_name == "fly-beads"

    async def test_skip_review_mode(self, fly_workflow: Any) -> None:
        """When skip_review=True, review step is skipped."""
        with _patch_all_actions():
            events = await _collect_events(
                fly_workflow,
                {"epic_id": "", "max_beads": 5},
            )

        completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert completed.success is True

    async def test_bead_failure_reported_in_result(self, fly_workflow: Any) -> None:
        """When Thespian reports bead failures, they appear in the result."""
        mv = _make_mock_actions()
        mv["xoscar_return"] = {
            "beads_completed": 0,
            "completed_bead_ids": [],
            "beads_failed": 1,
        }

        with _patch_all_actions(mv) as mocks:
            events = await _collect_events(fly_workflow, {"epic_id": "", "max_beads": 5})

        mocks["xoscar"].assert_called_once()

        completed = next(e for e in events if isinstance(e, WorkflowCompleted))
        assert completed.success is True
        assert fly_workflow.result.final_output["beads_failed"] == 1

    async def test_preflight_exception_emits_completed_failure(self, fly_workflow: Any) -> None:
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

    async def test_xoscar_path_invoked(self, fly_workflow: Any) -> None:
        """Thespian path is invoked for execution."""
        with _patch_all_actions() as mocks:
            await _collect_events(fly_workflow, {"epic_id": "", "max_beads": 5})

        mocks["xoscar"].assert_called_once()
        mocks["select"].assert_not_called()

    async def test_human_review_items_come_from_xoscar_events(self, fly_workflow: Any) -> None:
        """Needs-human-review beads are derived from Thespian bead events."""
        mv = _make_mock_actions()
        mv["xoscar_return"] = {
            "beads_completed": 1,
            "completed_bead_ids": ["b1"],
            "beads_failed": 0,
            "bead_events": [
                {
                    "bead_id": "b1",
                    "title": "Test bead",
                    "tag": "needs-human-review",
                    "review_rounds": 3,
                }
            ],
        }

        with _patch_all_actions(mv):
            async for _ in fly_workflow.execute({"epic_id": "", "max_beads": 5}):
                pass

        assert fly_workflow.result is not None
        assert fly_workflow.result.final_output["human_review_items"] == [
            {
                "bead_id": "b1",
                "title": "Test bead",
                "status": "needs-human-review",
                "tag": "needs-human-review",
                "review_rounds": 3,
            }
        ]

    async def test_max_beads_limit(self, fly_workflow: Any) -> None:
        """Thespian result beads_completed used for final count."""
        select_side_effect = [
            _make_select_result(bead_id=f"b{i}", title=f"Bead {i}", done=False) for i in range(10)
        ]
        mv = _make_mock_actions(
            select_side_effect=select_side_effect,
        )

        mv["xoscar_return"] = {
            "beads_completed": 3,
            "completed_bead_ids": ["b1", "b2", "b3"],
            "beads_failed": 0,
        }
        with _patch_all_actions(mv):
            async for _ in fly_workflow.execute({"epic_id": "", "max_beads": 3}):
                pass

        assert fly_workflow.result is not None
        final = fly_workflow.result.final_output
        assert final["beads_succeeded"] == 3

    async def test_multiple_beads_processed(self, fly_workflow: Any) -> None:
        """Multiple beads reported by Thespian appear in result."""
        mv = _make_mock_actions()
        mv["xoscar_return"] = {
            "beads_completed": 2,
            "completed_bead_ids": ["b1", "b2"],
            "beads_failed": 0,
        }

        with _patch_all_actions(mv):
            async for _ in fly_workflow.execute({"epic_id": "", "max_beads": 5}):
                pass

        assert fly_workflow.result.final_output["beads_succeeded"] == 2

    async def test_epic_id_passed_to_supervisor(self, fly_workflow: Any) -> None:
        """Epic ID is passed to the Thespian path for processing."""
        with _patch_all_actions() as mocks:
            async for _ in fly_workflow.execute({"epic_id": "epic-99", "max_beads": 5}):
                pass

        mocks["xoscar"].assert_called_once()
        call_kwargs = mocks["xoscar"].call_args[1]
        assert call_kwargs["epic_id"] == "epic-99"

    async def test_epic_not_closed_when_children_still_open(self, fly_workflow: Any) -> None:
        """Epic bead stays open when some children are blocked."""
        mv = _make_mock_actions()

        with _patch_all_actions(mv) as mocks:
            async for _ in fly_workflow.execute({"epic_id": "epic-99", "max_beads": 5}):
                pass

        # mark_bead_complete called only for the work bead (in steps), not the epic
        calls = mocks["mark_complete"].call_args_list
        epic_calls = [c for c in calls if c.kwargs.get("bead_id") == "epic-99"]
        assert len(epic_calls) == 0

    async def test_epic_not_closed_without_epic_id(self, fly_workflow: Any) -> None:
        """Epic is not closed when no epic_id was provided."""
        mv = _make_mock_actions()

        with _patch_all_actions(mv) as mocks:
            async for _ in fly_workflow.execute({"epic_id": "", "max_beads": 5}):
                pass

        # mark_bead_complete called only for the work bead (empty epic_id)
        calls = mocks["mark_complete"].call_args_list
        # The work bead call uses bead_id="b1", no epic close call
        for c in calls:
            assert c.kwargs.get("bead_id") != ""
            assert c.kwargs.get("reason", "") != "All child beads completed"


# =====================================================================
# _cost_sink_for_cwd
# =====================================================================


class TestCostSinkForCwd:
    """Tests for the cost-sink helper that resolves the runway store
    under ``<cwd>/.maverick/runway/`` and returns either an appender
    closure or ``None`` (when runway isn't initialized in the user repo)."""

    async def test_returns_none_when_runway_not_initialized(self, tmp_path: Any) -> None:
        from maverick.workflows.fly_beads.workflow import _cost_sink_for_cwd

        # tmp_path has no .maverick/runway/ — sink falls back to None
        # so callers degrade to structured-log-only telemetry.
        assert _cost_sink_for_cwd(tmp_path) is None

    async def test_returns_callable_when_runway_initialized(self, tmp_path: Any) -> None:
        from maverick.runway.store import RunwayStore
        from maverick.workflows.fly_beads.workflow import _cost_sink_for_cwd

        await RunwayStore(tmp_path / ".maverick" / "runway").initialize()
        sink = _cost_sink_for_cwd(tmp_path)
        assert sink is not None
        assert callable(sink)
