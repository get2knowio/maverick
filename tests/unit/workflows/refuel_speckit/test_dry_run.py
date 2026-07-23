"""Tests for --dry-run mechanics (SC-005 parity, zero writes)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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
        "dry_run": True,
        "enrich": False,
        "auto_commit": False,
    }
    inputs.update(overrides)
    return inputs


def _output_messages(events: list[object]) -> list[str]:
    return [getattr(e, "message", "") for e in events if hasattr(e, "message")]


class TestZeroWrites:
    @pytest.mark.asyncio
    async def test_dry_run_makes_zero_bd_write_calls(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path)
        mock_client = make_mock_bead_client()

        with patch(_PATCH_CLIENT, return_value=mock_client):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            _events, result = await collect_events(workflow, make_inputs(feature_dir, tmp_path))

        assert result is not None and result.success
        mock_client.create_bead.assert_not_called()
        mock_client.add_dependency.assert_not_called()
        mock_client.set_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_writes_no_run_metadata(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path)
        mock_client = make_mock_bead_client()

        with patch(_PATCH_CLIENT, return_value=mock_client):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            await collect_events(workflow, make_inputs(feature_dir, tmp_path))

        assert not (tmp_path / ".maverick" / "runs").exists()


class TestPreviewRendering:
    @pytest.mark.asyncio
    async def test_renders_per_task_preview_and_summary(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path)
        mock_client = make_mock_bead_client()

        with patch(_PATCH_CLIENT, return_value=mock_client):
            workflow = SpeckitRefuelWorkflow(config=mock_config)
            events, result = await collect_events(workflow, make_inputs(feature_dir, tmp_path))

        assert result is not None and result.success
        messages = _output_messages(events)
        joined = "\n".join(messages)
        assert "T001:" in joined
        assert "T002:" in joined
        assert "phase 1" in joined
        assert "[P]" in joined  # T002 is parallel
        assert "Dry run — no beads created." in messages

    @pytest.mark.asyncio
    async def test_parse_errors_surface_identically_to_real_runs(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = tmp_path / "specs" / "050-broken"
        feature_dir.mkdir(parents=True)
        (feature_dir / "tasks.md").write_text(
            "## Phase 1: Setup\n\n- [ ] not a valid task line\n", encoding="utf-8"
        )
        (feature_dir / "spec.md").write_text("# Feature Specification: Broken\n", encoding="utf-8")
        mock_client = make_mock_bead_client()

        with patch(_PATCH_CLIENT, return_value=mock_client):
            workflow_dry = SpeckitRefuelWorkflow(config=mock_config)
            _events_dry, result_dry = await collect_events(
                workflow_dry, make_inputs(feature_dir, tmp_path), ignore_exception=True
            )
            workflow_real = SpeckitRefuelWorkflow(config=mock_config)
            _events_real, result_real = await collect_events(
                workflow_real,
                make_inputs(feature_dir, tmp_path, dry_run=False),
                ignore_exception=True,
            )

        assert result_dry is not None and not result_dry.success
        assert result_real is not None and not result_real.success


class TestDryRunRealRunParity:
    @pytest.mark.asyncio
    async def test_dry_run_and_real_run_plan_same_content(
        self, mock_config: MagicMock, tmp_path: Path
    ) -> None:
        feature_dir = make_feature_dir(tmp_path)

        dry_client = make_mock_bead_client()
        with patch(_PATCH_CLIENT, return_value=dry_client):
            dry_workflow = SpeckitRefuelWorkflow(config=mock_config)
            _events, dry_result = await collect_events(
                dry_workflow, make_inputs(feature_dir, tmp_path)
            )

        real_client = make_mock_bead_client()
        with patch(_PATCH_CLIENT, return_value=real_client):
            real_workflow = SpeckitRefuelWorkflow(config=mock_config)
            _events, real_result = await collect_events(
                real_workflow, make_inputs(feature_dir, tmp_path, dry_run=False)
            )

        assert dry_result is not None and real_result is not None
        dry_output = dry_result.final_output
        real_output = real_result.final_output
        assert dry_output["dry_run"] is True
        assert real_output["dry_run"] is False
        assert len(dry_output["created_bead_ids"]) == len(real_output["created_bead_ids"])
        assert dry_output["skipped_completed"] == real_output["skipped_completed"]
        assert dry_output["skipped_existing"] == real_output["skipped_existing"]
        assert dry_output["edge_count"] == real_output["edge_count"]


class TestDryRunDelta:
    @pytest.mark.asyncio
    async def test_dry_run_over_delta_previews_only_new_tasks_and_writes_nothing(
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
            id="bead-existing-t001",
            title="T001: ...",
            status="open",
            priority=2,
            bead_type="task",
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
            events, result = await collect_events(workflow, make_inputs(feature_dir, tmp_path))

        assert result is not None and result.success
        output = result.final_output
        assert output["delta_run"] is True
        assert set(output["skipped_existing"]) == {"T001"}
        assert len(output["created_bead_ids"]) == 2  # T002, T003 only

        messages = _output_messages(events)
        joined = "\n".join(messages)
        assert "T001:" not in joined  # not previewed — already ingested
        assert "T002:" in joined
        assert "T003:" in joined

        mock_client.create_bead.assert_not_called()
        mock_client.add_dependency.assert_not_called()
        mock_client.set_state.assert_not_called()
