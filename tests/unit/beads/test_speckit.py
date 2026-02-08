"""Unit tests for speckit phase classification, grouping, and context."""

from __future__ import annotations

from pathlib import Path

from maverick.beads.models import BeadCategory, BeadDefinition, BeadType
from maverick.beads.speckit import (
    PhaseCategory,
    SpecKitContextExtractor,
    _extract_story_title,
    _extract_user_story_id,
    classify_phase,
    group_phases_into_beads,
)
from maverick.models.implementation import Task, TaskFile

# =============================================================================
# classify_phase
# =============================================================================


class TestClassifyPhase:
    """Tests for classify_phase()."""

    def test_user_story_by_name(self) -> None:
        result = classify_phase("Phase 3: User Story 1 - Basic Feature", 2, 10)
        assert result == PhaseCategory.USER_STORY

    def test_foundation_by_keyword_setup(self) -> None:
        result = classify_phase("Phase 1: Setup (Shared Infrastructure)", 0, 10)
        assert result == PhaseCategory.FOUNDATION

    def test_foundation_by_keyword_foundational(self) -> None:
        result = classify_phase("Phase 2: Foundational (Blocking Prerequisites)", 1, 10)
        assert result == PhaseCategory.FOUNDATION

    def test_foundation_by_keyword_infrastructure(self) -> None:
        result = classify_phase("Infrastructure Phase", 0, 5)
        assert result == PhaseCategory.FOUNDATION

    def test_cleanup_by_keyword_polish(self) -> None:
        result = classify_phase("Phase 13: Polish & Cross-Cutting Concerns", 12, 13)
        assert result == PhaseCategory.CLEANUP

    def test_cleanup_by_keyword_cleanup(self) -> None:
        result = classify_phase("Cleanup Phase", 4, 5)
        assert result == PhaseCategory.CLEANUP

    def test_cleanup_by_keyword_finalize(self) -> None:
        result = classify_phase("Finalize", 4, 5)
        assert result == PhaseCategory.CLEANUP

    def test_positional_first_phase_foundation(self) -> None:
        result = classify_phase("Phase 1: Getting Started", 0, 5)
        assert result == PhaseCategory.FOUNDATION

    def test_positional_second_phase_foundation(self) -> None:
        result = classify_phase("Phase 2: Core Models", 1, 5)
        assert result == PhaseCategory.FOUNDATION

    def test_positional_last_phase_cleanup(self) -> None:
        result = classify_phase("Phase 5: Final Touches", 4, 5)
        assert result == PhaseCategory.CLEANUP

    def test_positional_not_applied_for_few_phases(self) -> None:
        result = classify_phase("Phase 1: Getting Started", 0, 3)
        assert result == PhaseCategory.USER_STORY

    def test_default_user_story(self) -> None:
        result = classify_phase("Phase 3: Feature Implementation", 2, 5)
        assert result == PhaseCategory.USER_STORY

    def test_case_insensitive(self) -> None:
        result = classify_phase("USER STORY 5 - Grid Layout", 4, 10)
        assert result == PhaseCategory.USER_STORY


# =============================================================================
# _extract_user_story_id
# =============================================================================


class TestExtractUserStoryId:
    """Tests for _extract_user_story_id()."""

    def test_full_user_story_reference(self) -> None:
        result = _extract_user_story_id("Phase 3: User Story 1 - Basic Feature")
        assert result == "US1"

    def test_user_story_with_high_number(self) -> None:
        result = _extract_user_story_id("Phase 12: User Story 10 - Decorative Box")
        assert result == "US10"

    def test_us_shorthand(self) -> None:
        assert _extract_user_story_id("Phase 3: US1 - Basic") == "US1"

    def test_no_user_story(self) -> None:
        assert _extract_user_story_id("Phase 1: Setup") is None


# =============================================================================
# _extract_story_title
# =============================================================================


class TestExtractStoryTitle:
    """Tests for _extract_story_title()."""

    def test_full_phase_name(self) -> None:
        result = _extract_story_title(
            "Phase 3: User Story 1 - Basic Multilingual Greeting Display (Priority: P1)"
        )
        assert result == "Basic Multilingual Greeting Display"

    def test_simple_phase_name(self) -> None:
        result = _extract_story_title("Phase 5: User Story 3 - Display Customization")
        assert result == "Display Customization"

    def test_no_prefix(self) -> None:
        result = _extract_story_title("Custom Feature")
        assert result == "Custom Feature"


# =============================================================================
# group_phases_into_beads
# =============================================================================

# Phase name constants for readability
_SETUP = "Phase 1: Setup (Shared Infrastructure)"
_FOUND = "Phase 2: Foundational (Blocking Prerequisites)"
_US1 = "Phase 3: User Story 1 - Basic Feature (Priority: P1)"
_US2 = "Phase 4: User Story 2 - Advanced Feature (Priority: P2)"
_POLISH = "Phase 5: Polish & Cross-Cutting Concerns"


class TestGroupPhasesIntoBeads:
    """Tests for group_phases_into_beads()."""

    def test_basic_grouping(self) -> None:
        phases: dict[str, list[Task]] = {
            _SETUP: [
                Task(id="T001", description="Init", phase=_SETUP),
            ],
            _FOUND: [
                Task(id="T002", description="Core", phase=_FOUND),
            ],
            _US1: [
                Task(
                    id="T003",
                    description="Feat A",
                    user_story="US1",
                    phase=_US1,
                ),
            ],
            _US2: [
                Task(
                    id="T004",
                    description="Feat B",
                    user_story="US2",
                    phase=_US2,
                ),
            ],
            _POLISH: [
                Task(id="T005", description="Lint", phase=_POLISH),
            ],
        }

        beads = group_phases_into_beads(phases)

        assert len(beads) == 4

        # Foundation (merged setup + foundational)
        assert beads[0].title == "Foundation"
        assert beads[0].category == BeadCategory.FOUNDATION
        assert "T001" in beads[0].task_ids
        assert "T002" in beads[0].task_ids

        # User stories
        assert beads[1].category == BeadCategory.USER_STORY
        assert beads[1].user_story_id == "US1"
        assert beads[2].category == BeadCategory.USER_STORY
        assert beads[2].user_story_id == "US2"

        # Cleanup
        assert beads[3].title == "Cleanup"
        assert beads[3].category == BeadCategory.CLEANUP

    def test_priorities_are_sequential(self) -> None:
        phases: dict[str, list[Task]] = {
            "Phase 1: Setup": [
                Task(id="T001", description="x"),
            ],
            "Phase 2: User Story 1 - A": [
                Task(
                    id="T002",
                    description="x",
                    user_story="US1",
                ),
            ],
            "Phase 3: Cleanup": [
                Task(id="T003", description="x"),
            ],
        }
        beads = group_phases_into_beads(phases)
        priorities = [b.priority for b in beads]
        assert priorities == [1, 2, 3]

    def test_no_foundation_phases(self) -> None:
        phases: dict[str, list[Task]] = {
            "Phase 1: User Story 1 - A": [
                Task(
                    id="T001",
                    description="x",
                    user_story="US1",
                ),
            ],
            "Phase 2: User Story 2 - B": [
                Task(
                    id="T002",
                    description="x",
                    user_story="US2",
                ),
            ],
        }
        beads = group_phases_into_beads(phases)
        assert len(beads) == 2
        assert all(b.category == BeadCategory.USER_STORY for b in beads)

    def test_only_foundation(self) -> None:
        phases: dict[str, list[Task]] = {
            "Phase 1: Setup": [
                Task(id="T001", description="x"),
            ],
        }
        beads = group_phases_into_beads(phases)
        assert len(beads) == 1
        assert beads[0].category == BeadCategory.FOUNDATION


# =============================================================================
# SpecKitContextExtractor
# =============================================================================


class TestSpecKitContextExtractor:
    """Tests for SpecKitContextExtractor."""

    def test_build_epic_description(self, spec_dir_with_tasks: Path) -> None:
        tasks_path = spec_dir_with_tasks / "tasks.md"
        task_file = TaskFile.parse(tasks_path)
        extractor = SpecKitContextExtractor(spec_dir_with_tasks, task_file)

        desc = extractor.build_epic_description()

        assert "Spec directory" in desc
        assert "tasks.md" in desc
        assert "spec.md" in desc
        assert "Tasks" in desc

    def test_build_bead_description(self, spec_dir_with_tasks: Path) -> None:
        tasks_path = spec_dir_with_tasks / "tasks.md"
        task_file = TaskFile.parse(tasks_path)
        extractor = SpecKitContextExtractor(spec_dir_with_tasks, task_file)

        defn = BeadDefinition(
            title="Foundation",
            bead_type=BeadType.TASK,
            priority=1,
            category=BeadCategory.FOUNDATION,
            phase_names=[_SETUP],
            task_ids=["T001", "T002", "T003"],
        )

        desc = extractor.build_bead_description(defn)

        assert "Phases" in desc
        assert "Tasks" in desc
        assert "T001" in desc
        assert "Spec directory" in desc

    def test_extract_checkpoints_nonexistent_phase(
        self, spec_dir_with_tasks: Path
    ) -> None:
        tasks_path = spec_dir_with_tasks / "tasks.md"
        task_file = TaskFile.parse(tasks_path)
        extractor = SpecKitContextExtractor(spec_dir_with_tasks, task_file)

        checkpoints = extractor._extract_checkpoints(["Nonexistent Phase"])
        assert checkpoints == []
