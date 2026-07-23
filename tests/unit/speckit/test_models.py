"""Tests for the frozen Pydantic models in maverick.speckit.models."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from maverick.speckit.models import ParsedSpec, SpeckitFeature, SpeckitPhase, SpeckitTask


class TestSpeckitTask:
    def test_valid_task(self) -> None:
        task = SpeckitTask(
            task_id="T001",
            description="Do the thing",
            completed=False,
            parallel=False,
            phase_number=1,
            line_number=5,
        )
        assert task.task_id == "T001"
        assert task.story_id is None
        assert task.file_paths == ()
        assert task.explicit_deps == ()

    @pytest.mark.parametrize("bad_id", ["T1", "T12", "X001", "t001", ""])
    def test_task_id_must_match_pattern(self, bad_id: str) -> None:
        with pytest.raises(ValidationError):
            SpeckitTask(
                task_id=bad_id,
                description="Do the thing",
                completed=False,
                parallel=False,
                phase_number=1,
                line_number=5,
            )

    def test_task_id_accepts_4_plus_digits(self) -> None:
        task = SpeckitTask(
            task_id="T1234",
            description="Do the thing",
            completed=False,
            parallel=False,
            phase_number=1,
            line_number=5,
        )
        assert task.task_id == "T1234"

    def test_description_must_not_be_empty(self) -> None:
        with pytest.raises(ValidationError):
            SpeckitTask(
                task_id="T001",
                description="   ",
                completed=False,
                parallel=False,
                phase_number=1,
                line_number=5,
            )

    def test_is_frozen(self) -> None:
        task = SpeckitTask(
            task_id="T001",
            description="Do the thing",
            completed=False,
            parallel=False,
            phase_number=1,
            line_number=5,
        )
        with pytest.raises((TypeError, ValidationError)):
            task.completed = True  # type: ignore[misc]


class TestSpeckitPhase:
    def test_valid_phase(self) -> None:
        task = SpeckitTask(
            task_id="T001",
            description="Do the thing",
            completed=False,
            parallel=False,
            phase_number=1,
            line_number=5,
        )
        phase = SpeckitPhase(number=1, title="Setup", tasks=(task,))
        assert phase.number == 1
        assert phase.tasks == (task,)

    def test_phase_can_be_empty(self) -> None:
        phase = SpeckitPhase(number=1, title="Empty phase")
        assert phase.tasks == ()

    def test_number_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            SpeckitPhase(number=0, title="Bad")


class TestParsedSpec:
    def test_defaults(self) -> None:
        spec = ParsedSpec()
        assert spec.title == ""
        assert spec.success_criteria == ()
        assert spec.story_scenarios == {}

    def test_story_scenarios_keyed_by_story_id(self) -> None:
        spec = ParsedSpec(
            title="My Feature",
            success_criteria=("**SC-001**: fast",),
            story_scenarios={"US1": ("scenario one",), "US2": ()},
        )
        assert spec.story_scenarios["US1"] == ("scenario one",)
        assert spec.story_scenarios["US2"] == ()


class TestSpeckitFeature:
    def test_valid_feature(self, tmp_path: Path) -> None:
        feature_dir = tmp_path / "specs" / "001-test"
        task = SpeckitTask(
            task_id="T001",
            description="Do the thing",
            completed=False,
            parallel=False,
            phase_number=1,
            line_number=5,
        )
        phase = SpeckitPhase(number=1, title="Setup", tasks=(task,))
        feature = SpeckitFeature(
            feature_dir=feature_dir,
            feature_name="001-test",
            spec=ParsedSpec(title="Test"),
            phases=(phase,),
        )
        assert feature.feature_name == "001-test"
        assert feature.has_plan is False
        assert feature.story_deps == ()
