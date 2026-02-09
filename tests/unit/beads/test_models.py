"""Unit tests for bead data models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from maverick.beads.models import (
    BeadCategory,
    BeadDefinition,
    BeadDependency,
    BeadDetails,
    BeadGenerationResult,
    BeadSummary,
    BeadType,
    ClosedBead,
    CreatedBead,
    DependencyType,
    ReadyBead,
)


class TestBeadType:
    """Tests for BeadType enum."""

    def test_epic_value(self) -> None:
        assert BeadType.EPIC.value == "epic"

    def test_task_value(self) -> None:
        assert BeadType.TASK.value == "task"

    def test_from_string(self) -> None:
        assert BeadType("epic") == BeadType.EPIC


class TestBeadCategory:
    """Tests for BeadCategory enum."""

    def test_foundation_value(self) -> None:
        assert BeadCategory.FOUNDATION.value == "foundation"

    def test_user_story_value(self) -> None:
        assert BeadCategory.USER_STORY.value == "user_story"

    def test_cleanup_value(self) -> None:
        assert BeadCategory.CLEANUP.value == "cleanup"

    def test_validation_value(self) -> None:
        assert BeadCategory.VALIDATION.value == "validation"

    def test_review_value(self) -> None:
        assert BeadCategory.REVIEW.value == "review"


class TestDependencyType:
    """Tests for DependencyType enum."""

    def test_blocks_value(self) -> None:
        assert DependencyType.BLOCKS.value == "blocks"


class TestBeadDefinition:
    """Tests for BeadDefinition model."""

    def test_basic_creation(self) -> None:
        defn = BeadDefinition(
            title="Foundation",
            bead_type=BeadType.TASK,
            priority=1,
            category=BeadCategory.FOUNDATION,
        )
        assert defn.title == "Foundation"
        assert defn.bead_type == BeadType.TASK
        assert defn.priority == 1
        assert defn.category == BeadCategory.FOUNDATION

    def test_frozen(self) -> None:
        defn = BeadDefinition(
            title="Test",
            bead_type=BeadType.TASK,
            priority=1,
            category=BeadCategory.USER_STORY,
        )
        with pytest.raises(ValidationError):
            defn.title = "Changed"  # type: ignore[misc]

    def test_defaults(self) -> None:
        defn = BeadDefinition(
            title="Test",
            bead_type=BeadType.TASK,
            priority=1,
            category=BeadCategory.USER_STORY,
        )
        assert defn.description == ""
        assert defn.phase_names == []
        assert defn.user_story_id is None
        assert defn.task_ids == []

    def test_full_creation(self) -> None:
        defn = BeadDefinition(
            title="Basic Feature",
            bead_type=BeadType.TASK,
            priority=2,
            category=BeadCategory.USER_STORY,
            description="Implement basic feature",
            phase_names=["Phase 3: User Story 1"],
            user_story_id="US1",
            task_ids=["T006", "T007"],
        )
        assert defn.user_story_id == "US1"
        assert defn.task_ids == ["T006", "T007"]

    def test_empty_title_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BeadDefinition(
                title="",
                bead_type=BeadType.TASK,
                priority=1,
                category=BeadCategory.FOUNDATION,
            )

    def test_zero_priority_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BeadDefinition(
                title="Test",
                bead_type=BeadType.TASK,
                priority=0,
                category=BeadCategory.FOUNDATION,
            )


class TestCreatedBead:
    """Tests for CreatedBead model."""

    def test_creation(self, sample_task_definition: BeadDefinition) -> None:
        bead = CreatedBead(bd_id="abc123", definition=sample_task_definition)
        assert bead.bd_id == "abc123"
        assert bead.definition.title == "Foundation"

    def test_frozen(self, sample_task_definition: BeadDefinition) -> None:
        bead = CreatedBead(bd_id="abc123", definition=sample_task_definition)
        with pytest.raises(ValidationError):
            bead.bd_id = "changed"  # type: ignore[misc]

    def test_empty_bd_id_rejected(self, sample_task_definition: BeadDefinition) -> None:
        with pytest.raises(ValidationError):
            CreatedBead(bd_id="", definition=sample_task_definition)


class TestBeadDependency:
    """Tests for BeadDependency model."""

    def test_creation(self) -> None:
        dep = BeadDependency(blocker_id="a", blocked_id="b")
        assert dep.blocker_id == "a"
        assert dep.blocked_id == "b"
        assert dep.dep_type == DependencyType.BLOCKS

    def test_frozen(self) -> None:
        dep = BeadDependency(blocker_id="a", blocked_id="b")
        with pytest.raises(ValidationError):
            dep.blocker_id = "changed"  # type: ignore[misc]

    def test_explicit_dep_type(self) -> None:
        dep = BeadDependency(
            blocker_id="a", blocked_id="b", dep_type=DependencyType.BLOCKS
        )
        assert dep.dep_type == DependencyType.BLOCKS


class TestBeadGenerationResult:
    """Tests for BeadGenerationResult model."""

    def test_empty_result(self) -> None:
        result = BeadGenerationResult()
        assert result.epic is None
        assert result.work_beads == []
        assert result.dependencies == []
        assert result.errors == []
        assert not result.success
        assert result.total_beads == 0

    def test_success_with_epic(self, sample_created_bead: CreatedBead) -> None:
        epic_def = BeadDefinition(
            title="epic",
            bead_type=BeadType.EPIC,
            priority=1,
            category=BeadCategory.FOUNDATION,
        )
        epic = CreatedBead(bd_id="epic1", definition=epic_def)
        result = BeadGenerationResult(
            epic=epic,
            work_beads=[sample_created_bead],
        )
        assert result.success
        assert result.total_beads == 2

    def test_not_success_with_errors(self, sample_created_bead: CreatedBead) -> None:
        epic_def = BeadDefinition(
            title="epic",
            bead_type=BeadType.EPIC,
            priority=1,
            category=BeadCategory.FOUNDATION,
        )
        epic = CreatedBead(bd_id="epic1", definition=epic_def)
        result = BeadGenerationResult(
            epic=epic,
            work_beads=[sample_created_bead],
            errors=["Something failed"],
        )
        assert not result.success
        assert result.total_beads == 2

    def test_not_success_without_epic(self) -> None:
        result = BeadGenerationResult(errors=["Epic creation failed"])
        assert not result.success


class TestReadyBead:
    """Tests for ReadyBead model."""

    def test_creation(self) -> None:
        bead = ReadyBead(
            id="bead-001",
            title="Fix lint errors",
            priority=5,
            bead_type="task",
            description="Fix all lint errors",
            parent_id="epic-001",
        )
        assert bead.id == "bead-001"
        assert bead.title == "Fix lint errors"
        assert bead.priority == 5
        assert bead.parent_id == "epic-001"

    def test_frozen(self) -> None:
        bead = ReadyBead(id="bead-001", title="Test", priority=1)
        with pytest.raises(ValidationError):
            bead.id = "changed"  # type: ignore[misc]

    def test_defaults(self) -> None:
        bead = ReadyBead(id="bead-001", title="Test", priority=1)
        assert bead.bead_type == "task"
        assert bead.description == ""
        assert bead.parent_id is None


class TestClosedBead:
    """Tests for ClosedBead model."""

    def test_creation(self) -> None:
        bead = ClosedBead(
            id="bead-001",
            status="closed",
            closed_at="2025-01-01T00:00:00Z",
        )
        assert bead.id == "bead-001"
        assert bead.status == "closed"
        assert bead.closed_at == "2025-01-01T00:00:00Z"

    def test_frozen(self) -> None:
        bead = ClosedBead(id="bead-001", status="closed")
        with pytest.raises(ValidationError):
            bead.status = "open"  # type: ignore[misc]


class TestBeadDetails:
    """Tests for BeadDetails model."""

    def test_creation(self) -> None:
        details = BeadDetails(
            id="bead-001",
            title="Implementation task",
            description="Full description",
            bead_type="task",
            priority=3,
            status="open",
            parent_id="epic-001",
            labels=["feature", "core"],
            state={"branch": "main"},
        )
        assert details.id == "bead-001"
        assert details.labels == ["feature", "core"]
        assert details.state == {"branch": "main"}

    def test_defaults(self) -> None:
        details = BeadDetails(id="bead-001", title="Test")
        assert details.description == ""
        assert details.bead_type == "task"
        assert details.priority == 1
        assert details.status == "open"
        assert details.parent_id is None
        assert details.labels == []
        assert details.state == {}


class TestBeadSummary:
    """Tests for BeadSummary model."""

    def test_creation(self) -> None:
        summary = BeadSummary(
            id="bead-001",
            title="Test task",
            status="open",
            priority=2,
            bead_type="task",
        )
        assert summary.id == "bead-001"
        assert summary.title == "Test task"
        assert summary.status == "open"

    def test_defaults(self) -> None:
        summary = BeadSummary(id="bead-001", title="Test")
        assert summary.status == "open"
        assert summary.priority == 1
        assert summary.bead_type == "task"
