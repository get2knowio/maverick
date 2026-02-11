"""Unit tests for the fly-beads workflow YAML definition."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.dsl.serialization.schema import LoopStepRecord, WorkflowFile


@pytest.fixture
def fly_beads_yaml() -> str:
    """Load the fly-beads.yaml workflow."""
    workflow_path = (
        Path(__file__).parents[4]
        / "src"
        / "maverick"
        / "library"
        / "workflows"
        / "fly-beads.yaml"
    )
    return workflow_path.read_text(encoding="utf-8")


class TestFlyBeadsWorkflowLoads:
    """Tests that fly-beads.yaml loads and validates correctly."""

    def test_loads_as_workflow_file(self, fly_beads_yaml: str) -> None:
        wf = WorkflowFile.from_yaml(fly_beads_yaml)
        assert wf.name == "fly-beads"
        assert wf.version == "1.0"

    def test_epic_id_is_optional(self, fly_beads_yaml: str) -> None:
        wf = WorkflowFile.from_yaml(fly_beads_yaml)
        assert "epic_id" in wf.inputs
        assert wf.inputs["epic_id"].required is False
        assert wf.inputs["epic_id"].default == ""

    def test_no_branch_name_input(self, fly_beads_yaml: str) -> None:
        wf = WorkflowFile.from_yaml(fly_beads_yaml)
        assert "branch_name" not in wf.inputs

    def test_optional_inputs_have_defaults(self, fly_beads_yaml: str) -> None:
        wf = WorkflowFile.from_yaml(fly_beads_yaml)
        assert wf.inputs["max_beads"].required is False
        assert wf.inputs["max_beads"].default == 30
        assert wf.inputs["dry_run"].required is False
        assert wf.inputs["dry_run"].default is False
        assert wf.inputs["skip_review"].required is False
        assert wf.inputs["skip_review"].default is False

    def test_has_bead_loop_with_until(self, fly_beads_yaml: str) -> None:
        wf = WorkflowFile.from_yaml(fly_beads_yaml)
        loop_steps = [s for s in wf.steps if isinstance(s, LoopStepRecord)]
        assert len(loop_steps) == 1

        loop = loop_steps[0]
        assert loop.name == "bead_loop"
        assert loop.until is not None
        assert "check_done" in loop.until
        assert loop.for_each is None

    def test_bead_loop_has_correct_substeps(self, fly_beads_yaml: str) -> None:
        wf = WorkflowFile.from_yaml(fly_beads_yaml)
        loop = next(s for s in wf.steps if isinstance(s, LoopStepRecord))

        step_names = [s.name for s in loop.steps]
        assert "select_bead" in step_names
        assert "implement" in step_names
        assert "validate" in step_names
        assert "create_fix_beads" in step_names
        assert "commit_bead" in step_names
        assert "close_bead" in step_names
        assert "check_done" in step_names

    def test_has_final_push(self, fly_beads_yaml: str) -> None:
        wf = WorkflowFile.from_yaml(fly_beads_yaml)
        step_names = [s.name for s in wf.steps]
        assert "final_push" in step_names

    def test_no_init_step(self, fly_beads_yaml: str) -> None:
        """Workflow should not have an init step (no branch creation)."""
        wf = WorkflowFile.from_yaml(fly_beads_yaml)
        step_names = [s.name for s in wf.steps]
        assert "init" not in step_names

    def test_yaml_roundtrip(self, fly_beads_yaml: str) -> None:
        wf1 = WorkflowFile.from_yaml(fly_beads_yaml)
        yaml_out = wf1.to_yaml()
        wf2 = WorkflowFile.from_yaml(yaml_out)

        assert wf2.name == wf1.name
        assert len(wf2.steps) == len(wf1.steps)
        assert len(wf2.inputs) == len(wf1.inputs)
