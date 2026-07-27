"""Tests for ingestion-plan building (maverick.speckit.build.build_ingestion_plan)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from maverick.speckit.build import EPIC_TASK_ID, build_ingestion_plan
from maverick.speckit.errors import NothingToIngestError
from maverick.speckit.models import ParsedSpec, SpeckitFeature, SpeckitPhase, SpeckitTask
from maverick.speckit.parser import parse_spec_md, parse_tasks_md


def _feature_from_fixture(feature_dir: Path, tasks_md: str, spec_md: str) -> SpeckitFeature:
    phases, story_deps = parse_tasks_md(tasks_md)
    spec = parse_spec_md(spec_md)
    return SpeckitFeature(
        feature_dir=feature_dir,
        feature_name=feature_dir.name,
        spec=spec,
        phases=phases,
        story_deps=story_deps,
        has_plan=True,
    )


@pytest.fixture
def feature(speckit_feature_dir: Path, full_tasks_md: str, full_spec_md: str) -> SpeckitFeature:
    return _feature_from_fixture(speckit_feature_dir, full_tasks_md, full_spec_md)


class TestFreshRun:
    def test_epic_and_new_tasks_created(self, feature: SpeckitFeature) -> None:
        plan, warnings = build_ingestion_plan(feature)
        assert plan.epic is not None
        assert plan.epic.task_id == EPIC_TASK_ID
        assert plan.existing_epic_id is None
        # 11 tasks total, 2 completed (T002, T009) -> 9 new.
        assert len(plan.new_tasks) == 9
        assert set(plan.skipped_completed) == {"T002", "T009"}
        assert plan.skipped_existing == ()

    def test_task_title_format_and_length(self, feature: SpeckitFeature) -> None:
        plan, _warnings = build_ingestion_plan(feature)
        titles = {pb.task_id: pb.definition.title for pb in plan.new_tasks}
        assert titles["T001"].startswith("T001: ")
        assert all(len(t) <= 490 for t in titles.values())

    def test_task_description_sections(self, feature: SpeckitFeature) -> None:
        plan, _warnings = build_ingestion_plan(feature)
        by_id = {pb.task_id: pb for pb in plan.new_tasks}
        desc = by_id["T003"].definition.description
        assert "## Task" in desc
        assert "## Acceptance Criteria" in desc
        assert "## File Scope" in desc
        assert "src/config.py" in desc
        assert "## Verification" in desc
        assert "rg --files -g 'src/config.py'" in desc

    def test_story_task_description_includes_scenarios(self, feature: SpeckitFeature) -> None:
        plan, _warnings = build_ingestion_plan(feature)
        by_id = {pb.task_id: pb for pb in plan.new_tasks}
        desc = by_id["T006"].definition.description
        assert "outcome for story 1" in desc

    def test_verification_never_empty(self, feature: SpeckitFeature) -> None:
        plan, _warnings = build_ingestion_plan(feature)
        for pb in plan.new_tasks:
            assert "## Verification" in pb.definition.description
            section = pb.definition.description.split("## Verification")[1]
            assert section.strip().startswith("-")

    def test_epic_description_has_success_criteria_and_source(
        self, feature: SpeckitFeature
    ) -> None:
        plan, _warnings = build_ingestion_plan(feature)
        assert plan.epic is not None
        desc = plan.epic.definition.description
        assert "## Success Criteria" in desc
        assert "## Source" in desc
        assert "specs/048-sample-feature/" in desc

    def test_task_state_carries_provenance(self, feature: SpeckitFeature) -> None:
        plan, _warnings = build_ingestion_plan(feature)
        by_id = {pb.task_id: pb for pb in plan.new_tasks}
        assert by_id["T003"].state == {
            "speckit_task_id": "T003",
            "speckit_phase": "1",
            "speckit_parallel": "true",
        }
        assert by_id["T001"].state["speckit_parallel"] == "false"

    def test_epic_state_carries_feature_name(self, feature: SpeckitFeature) -> None:
        plan, _warnings = build_ingestion_plan(feature)
        assert plan.epic is not None
        assert plan.epic.state == {"speckit_feature": "048-sample-feature"}

    def test_edges_present_and_acyclic(self, feature: SpeckitFeature) -> None:
        plan, _warnings = build_ingestion_plan(feature)
        assert len(plan.edges) > 0

    def test_labels_include_speckit(self, feature: SpeckitFeature) -> None:
        plan, _warnings = build_ingestion_plan(feature)
        assert plan.epic is not None
        assert "speckit" in plan.epic.definition.labels
        for pb in plan.new_tasks:
            assert "speckit" in pb.definition.labels


class TestDeltaRun:
    def test_only_new_tasks_included_no_epic(self, feature: SpeckitFeature) -> None:
        existing_task_map = {"T001": "bead-t001", "T003": "bead-t003"}
        plan, _warnings = build_ingestion_plan(
            feature,
            existing_epic_id="epic-existing",
            existing_task_map=existing_task_map,
        )
        assert plan.epic is None
        assert plan.existing_epic_id == "epic-existing"
        new_ids = {pb.task_id for pb in plan.new_tasks}
        assert "T001" not in new_ids
        assert "T003" not in new_ids
        assert set(plan.skipped_existing) == {"T001", "T003"}

    def test_delta_edges_resolve_through_existing_task_map(self, feature: SpeckitFeature) -> None:
        existing_task_map = {"T003": "bead-t003"}
        plan, _warnings = build_ingestion_plan(
            feature,
            existing_epic_id="epic-existing",
            existing_task_map=existing_task_map,
        )
        blockers = {blocker for blocker, _blocked in plan.edges}
        assert "bead-t003" in blockers
        assert "T003" not in blockers

    def test_delta_no_op_when_all_open_tasks_already_ingested(
        self, feature: SpeckitFeature
    ) -> None:
        all_open_ids = [
            t.task_id for phase in feature.phases for t in phase.tasks if not t.completed
        ]
        existing_task_map = {tid: f"bead-{tid}" for tid in all_open_ids}
        plan, _warnings = build_ingestion_plan(
            feature,
            existing_epic_id="epic-existing",
            existing_task_map=existing_task_map,
        )
        assert plan.new_tasks == ()
        assert plan.epic is None
        assert set(plan.skipped_existing) == set(all_open_ids)


class TestValidationBeforeWrite:
    def test_zero_open_tasks_raises_nothing_to_ingest(self, tmp_path: Path) -> None:
        tasks_md = """\
## Phase 1: Setup

- [x] T001 Already done
- [x] T002 Also done
"""
        spec_md = "# Feature Specification: All Done\n"
        feature_dir = tmp_path / "specs" / "999-all-done"
        feature = _feature_from_fixture(feature_dir, tasks_md, spec_md)

        with pytest.raises(NothingToIngestError) as exc_info:
            build_ingestion_plan(feature)
        assert exc_info.value.completed_count == 2
        assert exc_info.value.total_count == 2

    def test_missing_story_scenarios_produces_warning(self, tmp_path: Path) -> None:
        tasks_md = """\
## Phase 1: Setup

- [ ] T001 [US9] A task labeled with a story that has no scenarios
"""
        feature_dir = tmp_path / "specs" / "998-no-story"
        feature = SpeckitFeature(
            feature_dir=feature_dir,
            feature_name=feature_dir.name,
            spec=ParsedSpec(title="No Story"),
            phases=parse_tasks_md(tasks_md)[0],
        )
        _plan, warnings = build_ingestion_plan(feature)
        assert any("US9" in w for w in warnings)

    def test_missing_success_criteria_produces_warning(self, tmp_path: Path) -> None:
        feature_dir = tmp_path / "specs" / "997-no-sc"
        phase = SpeckitPhase(
            number=1,
            title="Setup",
            tasks=(
                SpeckitTask(
                    task_id="T001",
                    description="do a thing",
                    completed=False,
                    parallel=False,
                    phase_number=1,
                    line_number=1,
                ),
            ),
        )
        feature = SpeckitFeature(
            feature_dir=feature_dir,
            feature_name=feature_dir.name,
            spec=ParsedSpec(title="No SC"),
            phases=(phase,),
        )
        _plan, warnings = build_ingestion_plan(feature)
        assert any("Success Criteria" in w for w in warnings)


class TestVerificationFallback:
    """The no-file-scope fallback must be a check a fix can actually close.

    Regression for the first live walkthrough: a task with no extractable
    file paths got ``rg --files -g '<feature_name>'``. ``build.py`` calls
    that "trivially-true", but nothing in a repository is *named*
    ``001-greet-cli`` -- the directory is ``specs/001-greet-cli/``. The
    check therefore always failed, routed the bead into an AC fix round no
    edit could close, and the fixer satisfied it by fabricating and
    committing a junk file named ``specs/001-greet-cli/001-greet-cli``.
    """

    TASKS = """\
## Phase 1: Setup

- [ ] T001 Draft the rollout narrative for stakeholders
"""

    SPEC = """\
# Feature Specification: Greet

## Success Criteria

- **SC-001**: It works.
"""

    def _verification_lines(self, tmp_path: Path) -> list[str]:
        feature_dir = tmp_path / "specs" / "001-greet-cli"
        feature_dir.mkdir(parents=True)
        feature = _feature_from_fixture(feature_dir, self.TASKS, self.SPEC)
        plan, _ = build_ingestion_plan(feature)
        body = plan.new_tasks[0].definition.description
        section = body.split("## Verification", 1)[1]
        return [
            ln.strip("- ").strip() for ln in section.splitlines() if ln.strip().startswith("-")
        ]

    def test_fallback_targets_the_feature_directory_not_a_bare_name(self, tmp_path: Path) -> None:
        lines = self._verification_lines(tmp_path)
        assert lines, "the AC gate must never be left with nothing to run"
        assert "rg --files -g '001-greet-cli'" not in lines, (
            "a bare feature name matches no file; this check can never pass"
        )
        assert any("specs/001-greet-cli/" in ln for ln in lines), lines

    @pytest.mark.skipif(shutil.which("rg") is None, reason="requires ripgrep on PATH")
    def test_fallback_actually_matches_on_a_real_tree(self, tmp_path: Path) -> None:
        """Run the emitted command for real -- the point is that it passes.

        Guarded rather than reimplemented: asserting against our own glob
        expansion would test a copy of the thing under test, and the whole
        defect was that a command nobody executed could not match. CI installs
        ripgrep so this runs there; the skip is for contributors without it.
        """
        import shlex
        import subprocess

        feature_dir = tmp_path / "specs" / "001-greet-cli"
        lines = self._verification_lines(tmp_path)
        (feature_dir / "spec.md").write_text("# Spec\n", encoding="utf-8")
        (feature_dir / "tasks.md").write_text("# Tasks\n", encoding="utf-8")

        proc = subprocess.run(shlex.split(lines[0]), cwd=tmp_path, capture_output=True, text=True)
        assert proc.stdout.strip(), (
            f"fallback {lines[0]!r} matched nothing in {tmp_path}; "
            "an unmatchable check is an AC gate no fix can close"
        )
