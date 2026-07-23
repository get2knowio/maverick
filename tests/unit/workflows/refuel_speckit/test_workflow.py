"""Tests for SpeckitRefuelWorkflow using a stubbed BeadClient."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.beads.models import BeadDetails, BeadSummary
from maverick.workflows.refuel_speckit.workflow import SpeckitRefuelWorkflow
from tests.unit.workflows.refuel_speckit.conftest import (
    WORKFLOW_SPEC_MD,
    WORKFLOW_TASKS_MD,
    collect_events,
    make_mock_bead_client,
)

_PATCH_CLIENT = "maverick.beads.client.BeadClient"


def make_feature_dir(tmp_path: Path, name: str = "048-workflow-sample") -> Path:
    feature_dir = tmp_path / "specs" / name
    feature_dir.mkdir(parents=True)
    (feature_dir / "tasks.md").write_text(WORKFLOW_TASKS_MD, encoding="utf-8")
    (feature_dir / "spec.md").write_text(WORKFLOW_SPEC_MD, encoding="utf-8")
    return feature_dir


def make_inputs(feature_dir: Path, cwd: Path, **overrides: object) -> dict[str, object]:
    inputs: dict[str, object] = {
        "feature_dir": str(feature_dir),
        "cwd": str(cwd),
        "dry_run": False,
        "enrich": False,
        "auto_commit": False,
    }
    inputs.update(overrides)
    return inputs


class TestFreshRun:
    @pytest.mark.asyncio
    async def test_creates_epic_tasks_deps_and_chains(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path)
        other_epic = BeadSummary(
            id="epic-other", title="Other feature", status="open", priority=1, bead_type="epic"
        )
        mock_client = make_mock_bead_client(
            existing_epics=[other_epic],
            epic_details_by_id={
                "epic-other": BeadDetails(
                    id="epic-other", title="Other feature", bead_type="epic", state={}
                )
            },
        )

        with patch(_PATCH_CLIENT, return_value=mock_client):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            _events, result = await collect_events(workflow, make_inputs(feature_dir, tmp_path))

        assert result is not None
        assert result.success
        output = result.final_output
        assert output["feature_name"] == "048-workflow-sample"
        assert output["delta_run"] is False
        assert output["dry_run"] is False
        assert len(output["created_bead_ids"]) == 3  # T001, T002, T003
        assert output["edge_count"] > 0

        # Epic created first, then 3 task beads; set_state for epic + all tasks.
        first_call_definition = mock_client.create_bead.call_args_list[0].args[0]
        assert first_call_definition.bead_type.value == "epic"
        assert mock_client.create_bead.call_count == 4  # epic + 3 tasks
        assert mock_client.set_state.call_count == 4  # epic + 3 tasks
        # Epic chained behind the pre-existing open epic.
        chain_calls = [
            c
            for c in mock_client.add_dependency.call_args_list
            if c.args[0].blocker_id == "epic-other"
        ]
        assert len(chain_calls) == 1

        # Run metadata written with status "refueled".
        runs_dir = tmp_path / ".maverick" / "runs"
        assert runs_dir.is_dir()
        run_dirs = list(runs_dir.iterdir())
        assert len(run_dirs) == 1
        import json

        meta = json.loads((run_dirs[0] / "metadata.json").read_text())
        assert meta["status"] == "refueled"
        assert meta["plan_name"] == "048-workflow-sample"


class TestDeltaRun:
    @pytest.mark.asyncio
    async def test_adopts_existing_epic_and_only_creates_new_tasks(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path)
        existing_epic = BeadSummary(
            id="epic-existing",
            title="Workflow Sample",
            status="open",
            priority=1,
            bead_type="epic",
        )
        existing_epic_details = BeadDetails(
            id="epic-existing",
            title="Workflow Sample",
            bead_type="epic",
            state={"speckit_feature": "048-workflow-sample"},
        )
        existing_child = BeadSummary(
            id="bead-existing-t001", title="T001: ...", status="open", priority=2, bead_type="task"
        )
        mock_client = make_mock_bead_client(
            existing_epics=[existing_epic],
            epic_details_by_id={
                "epic-existing": existing_epic_details,
                "bead-existing-t001": BeadDetails(
                    id="bead-existing-t001",
                    title="T001",
                    bead_type="task",
                    state={"speckit_task_id": "T001"},
                ),
            },
            children_by_epic={"epic-existing": [existing_child]},
        )

        with patch(_PATCH_CLIENT, return_value=mock_client):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            _events, result = await collect_events(workflow, make_inputs(feature_dir, tmp_path))

        assert result is not None and result.success
        output = result.final_output
        assert output["delta_run"] is True
        assert output["epic_id"] == "epic-existing"
        assert set(output["skipped_existing"]) == {"T001"}
        # Only T002 and T003 created (T001 already ingested).
        assert len(output["created_bead_ids"]) == 2

        # No new epic created — create_bead never called with an epic definition.
        for call in mock_client.create_bead.call_args_list:
            assert call.args[0].bead_type.value == "task"

        # No re-chaining: epic wasn't (re-)created, so no chain-epic call
        # should target "epic-existing" as the blocked side.
        for call in mock_client.add_dependency.call_args_list:
            assert call.args[0].blocked_id != "epic-existing"

    @pytest.mark.asyncio
    async def test_no_op_when_all_open_tasks_already_ingested(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path)
        existing_epic = BeadSummary(
            id="epic-existing",
            title="Workflow Sample",
            status="open",
            priority=1,
            bead_type="epic",
        )
        existing_epic_details = BeadDetails(
            id="epic-existing",
            title="Workflow Sample",
            bead_type="epic",
            state={"speckit_feature": "048-workflow-sample"},
        )
        children = [
            BeadSummary(id=f"bead-{tid}", title=tid, status="open", priority=2, bead_type="task")
            for tid in ("T001", "T002", "T003")
        ]
        mock_client = make_mock_bead_client(
            existing_epics=[existing_epic],
            epic_details_by_id={
                "epic-existing": existing_epic_details,
                **{
                    f"bead-{tid}": BeadDetails(
                        id=f"bead-{tid}",
                        title=tid,
                        bead_type="task",
                        state={"speckit_task_id": tid},
                    )
                    for tid in ("T001", "T002", "T003")
                },
            },
            children_by_epic={"epic-existing": children},
        )

        with patch(_PATCH_CLIENT, return_value=mock_client):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            _events, result = await collect_events(workflow, make_inputs(feature_dir, tmp_path))

        assert result is not None and result.success
        output = result.final_output
        assert output["created_bead_ids"] == []
        mock_client.create_bead.assert_not_called()

        # The no-op summary is emitted under a properly started+completed
        # RECORD_RUN step (not attributed to a step the renderer never saw
        # start).
        from maverick.events import StepCompleted, StepStarted
        from maverick.workflows.refuel_speckit.constants import RECORD_RUN

        started = {e.step_name for e in _events if isinstance(e, StepStarted)}
        completed = {e.step_name for e in _events if isinstance(e, StepCompleted)}
        assert RECORD_RUN in started
        assert RECORD_RUN in completed


class TestMultipleMatchingEpics:
    @pytest.mark.asyncio
    async def test_raises_on_multiple_open_epics_for_same_feature(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path)
        epic_a = BeadSummary(id="epic-a", title="A", status="open", priority=1, bead_type="epic")
        epic_b = BeadSummary(id="epic-b", title="B", status="open", priority=1, bead_type="epic")
        mock_client = make_mock_bead_client(
            existing_epics=[epic_a, epic_b],
            epic_details_by_id={
                "epic-a": BeadDetails(
                    id="epic-a",
                    title="A",
                    bead_type="epic",
                    state={"speckit_feature": "048-workflow-sample"},
                ),
                "epic-b": BeadDetails(
                    id="epic-b",
                    title="B",
                    bead_type="epic",
                    state={"speckit_feature": "048-workflow-sample"},
                ),
            },
        )

        with patch(_PATCH_CLIENT, return_value=mock_client):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            _events, result = await collect_events(
                workflow, make_inputs(feature_dir, tmp_path), ignore_exception=True
            )

        assert result is not None
        assert not result.success
        mock_client.create_bead.assert_not_called()


class TestMidCreationFailure:
    @pytest.mark.asyncio
    async def test_reports_created_ids_on_partial_failure(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path)
        call_count = {"n": 0}

        async def _flaky_create_bead(definition: object, parent_id: str | None = None) -> object:
            from types import SimpleNamespace

            call_count["n"] += 1
            if call_count["n"] == 3:  # epic (1) + first task (2) succeed, second task fails
                raise RuntimeError("bd create timed out")
            return SimpleNamespace(bd_id=f"bead-{call_count['n']}", definition=definition)

        mock_client = make_mock_bead_client(create_bead_side_effect=_flaky_create_bead)

        with patch(_PATCH_CLIENT, return_value=mock_client):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            _events, result = await collect_events(
                workflow, make_inputs(feature_dir, tmp_path), ignore_exception=True
            )

        assert result is not None
        assert not result.success
        failed_steps = [r for r in result.step_results if not r.success]
        assert any(
            "bead-1" in (r.error or "") or "bead-2" in (r.error or "") for r in failed_steps
        )


class TestValidationBeforeWrite:
    @pytest.mark.asyncio
    async def test_all_completed_raises_before_any_bd_write(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = tmp_path / "specs" / "049-all-done"
        feature_dir.mkdir(parents=True)
        (feature_dir / "tasks.md").write_text(
            "## Phase 1: Setup\n\n- [x] T001 Already done\n", encoding="utf-8"
        )
        (feature_dir / "spec.md").write_text(
            "# Feature Specification: All Done\n", encoding="utf-8"
        )
        mock_client = make_mock_bead_client()

        with patch(_PATCH_CLIENT, return_value=mock_client):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            _events, result = await collect_events(
                workflow, make_inputs(feature_dir, tmp_path), ignore_exception=True
            )

        assert result is not None
        assert not result.success
        mock_client.create_bead.assert_not_called()
        # The underlying exception is a NothingToIngestError (E07).
        assert workflow.result is not None


class TestSelectNextBeadCompatibility:
    """T019: select_next_bead's flight_plan_name epic-state read must
    tolerate a speckit epic that never sets that key (research D12)."""

    @pytest.mark.asyncio
    async def test_select_next_bead_tolerates_missing_flight_plan_name(
        self, tmp_path: Path
    ) -> None:
        from maverick.beads.models import ReadyBead
        from maverick.library.actions.beads import select_next_bead

        mock_client = make_mock_bead_client(
            epic_details_by_id={
                "epic-speckit": BeadDetails(
                    id="epic-speckit",
                    title="Speckit Feature",
                    bead_type="epic",
                    state={"speckit_feature": "048-workflow-sample"},
                )
            },
        )
        mock_client.ready = AsyncMock(
            return_value=[
                ReadyBead(id="bead-1", title="T001: do a thing", priority=2, bead_type="task")
            ]
        )

        with patch(_PATCH_CLIENT, return_value=mock_client):
            result = await select_next_bead(epic_id="epic-speckit", cwd=tmp_path)

        assert result.found is True
        assert result.flight_plan_name == ""


class TestDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_makes_zero_write_calls(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path)
        mock_client = make_mock_bead_client()

        with patch(_PATCH_CLIENT, return_value=mock_client):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            _events, result = await collect_events(
                workflow, make_inputs(feature_dir, tmp_path, dry_run=True)
            )

        assert result is not None and result.success
        output = result.final_output
        assert output["dry_run"] is True
        assert len(output["created_bead_ids"]) == 3
        mock_client.create_bead.assert_not_called()
        mock_client.add_dependency.assert_not_called()
        mock_client.set_state.assert_not_called()
        assert not (tmp_path / ".maverick" / "runs").exists()
