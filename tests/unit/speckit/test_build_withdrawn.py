"""Unit tests for speckit/build.py's compute_withdrawn_tasks (059-spec-delta-layer)."""

from __future__ import annotations

from maverick.speckit.build import compute_withdrawn_tasks
from maverick.speckit.models import ParsedSpec, SpeckitFeature, SpeckitPhase, SpeckitTask


def _feature(tmp_path, task_ids: list[str]) -> SpeckitFeature:
    tasks = tuple(
        SpeckitTask(
            task_id=tid,
            description=f"Task {tid}",
            completed=False,
            parallel=False,
            phase_number=1,
            line_number=i + 1,
        )
        for i, tid in enumerate(task_ids)
    )
    return SpeckitFeature(
        feature_dir=tmp_path,
        feature_name="052-conditional-landing",
        spec=ParsedSpec(),
        phases=(SpeckitPhase(number=1, title="Setup", tasks=tasks),),
    )


class TestComputeWithdrawnTasks:
    def test_empty_on_first_run(self, tmp_path) -> None:
        feature = _feature(tmp_path, ["T001", "T002"])
        withdrawn = compute_withdrawn_tasks(feature, existing_task_map={}, bead_status={})
        assert withdrawn == ()

    def test_empty_when_nothing_withdrawn(self, tmp_path) -> None:
        feature = _feature(tmp_path, ["T001", "T002"])
        existing_task_map = {"T001": "mv-1", "T002": "mv-2"}
        bead_status = {"mv-1": "open", "mv-2": "closed"}
        withdrawn = compute_withdrawn_tasks(feature, existing_task_map, bead_status)
        assert withdrawn == ()

    def test_exactly_the_set_difference(self, tmp_path) -> None:
        # T001 remains in the feature; T017 is gone (withdrawn).
        feature = _feature(tmp_path, ["T001"])
        existing_task_map = {"T001": "mv-1", "T017": "mv-17"}
        bead_status = {"mv-1": "open", "mv-17": "in_progress"}
        withdrawn = compute_withdrawn_tasks(feature, existing_task_map, bead_status)
        assert len(withdrawn) == 1
        assert withdrawn[0].task_id == "T017"
        assert withdrawn[0].bead_id == "mv-17"
        assert withdrawn[0].bead_status == "in_progress"
        assert withdrawn[0].closable is False

    def test_closable_true_only_when_open(self, tmp_path) -> None:
        feature = _feature(tmp_path, [])
        existing_task_map = {"T001": "mv-1", "T002": "mv-2"}
        bead_status = {"mv-1": "open", "mv-2": "closed"}
        withdrawn = compute_withdrawn_tasks(feature, existing_task_map, bead_status)
        by_id = {w.task_id: w for w in withdrawn}
        assert by_id["T001"].closable is True
        assert by_id["T002"].closable is False

    def test_ordered_by_task_id_for_determinism(self, tmp_path) -> None:
        feature = _feature(tmp_path, [])
        existing_task_map = {"T020": "mv-20", "T003": "mv-3", "T100": "mv-100"}
        bead_status = {"mv-20": "open", "mv-3": "open", "mv-100": "open"}
        withdrawn = compute_withdrawn_tasks(feature, existing_task_map, bead_status)
        assert [w.task_id for w in withdrawn] == ["T003", "T020", "T100"]

    def test_missing_bead_status_defaults_not_closable(self, tmp_path) -> None:
        feature = _feature(tmp_path, [])
        existing_task_map = {"T017": "mv-17"}
        withdrawn = compute_withdrawn_tasks(feature, existing_task_map, bead_status={})
        assert withdrawn[0].bead_status == ""
        assert withdrawn[0].closable is False
