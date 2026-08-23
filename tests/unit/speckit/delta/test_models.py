"""Unit tests for speckit/delta/models.py."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from maverick.speckit.delta.models import (
    OPERATION_ORDER,
    SHRINK_FLOOR,
    Acknowledgement,
    ApplicationRecord,
    DeltaDocument,
    DeltaOperation,
    Impact,
    RequirementEntry,
    TaskEntry,
)


class TestOperationOrder:
    def test_operation_order_is_renamed_removed_modified_added(self) -> None:
        assert OPERATION_ORDER == (
            DeltaOperation.RENAMED,
            DeltaOperation.REMOVED,
            DeltaOperation.MODIFIED,
            DeltaOperation.ADDED,
        )

    def test_operation_order_is_not_enum_declaration_order(self) -> None:
        # The enum declares ADDED, MODIFIED, REMOVED, RENAMED (document
        # grammar order) — OPERATION_ORDER must differ from it, proving
        # it's a deliberate module constant, not an accident of iteration.
        declaration_order = tuple(DeltaOperation)
        assert declaration_order != OPERATION_ORDER


class TestShrinkFloor:
    def test_shrink_floor_is_the_contract_constant(self) -> None:
        assert SHRINK_FLOOR == 0.6


class TestRequirementEntry:
    def test_added_requires_after_only(self) -> None:
        entry = RequirementEntry(
            operation=DeltaOperation.ADDED,
            req_id="FR-026",
            after="- **FR-026**: New requirement.\n",
            line_number=1,
        )
        assert entry.after is not None
        assert entry.before is None

    def test_added_with_before_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RequirementEntry(
                operation=DeltaOperation.ADDED,
                req_id="FR-026",
                before="- **FR-026**: Old.\n",
                after="- **FR-026**: New.\n",
                line_number=1,
            )

    def test_added_without_after_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RequirementEntry(operation=DeltaOperation.ADDED, req_id="FR-026", line_number=1)

    def test_modified_requires_both(self) -> None:
        entry = RequirementEntry(
            operation=DeltaOperation.MODIFIED,
            req_id="FR-014",
            before="- **FR-014**: Old.\n",
            after="- **FR-014**: New.\n",
            line_number=1,
        )
        assert entry.before and entry.after

    def test_modified_missing_before_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RequirementEntry(
                operation=DeltaOperation.MODIFIED,
                req_id="FR-014",
                after="- **FR-014**: New.\n",
                line_number=1,
            )

    def test_removed_requires_before_only(self) -> None:
        entry = RequirementEntry(
            operation=DeltaOperation.REMOVED,
            req_id="FR-021",
            before="- **FR-021**: Gone.\n",
            line_number=1,
        )
        assert entry.before is not None
        assert entry.after is None

    def test_removed_with_after_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RequirementEntry(
                operation=DeltaOperation.REMOVED,
                req_id="FR-021",
                before="- **FR-021**: Gone.\n",
                after="- **FR-021**: Still here?\n",
                line_number=1,
            )

    def test_renamed_requires_neither_before_nor_after(self) -> None:
        entry = RequirementEntry(
            operation=DeltaOperation.RENAMED,
            req_id="FR-018",
            new_req_id="FR-019",
            line_number=1,
        )
        assert entry.new_req_id == "FR-019"

    def test_renamed_without_new_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RequirementEntry(operation=DeltaOperation.RENAMED, req_id="FR-018", line_number=1)

    def test_renamed_with_before_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RequirementEntry(
                operation=DeltaOperation.RENAMED,
                req_id="FR-018",
                new_req_id="FR-019",
                before="- **FR-018**: Text.\n",
                line_number=1,
            )

    def test_shrink_intended_only_valid_on_modified(self) -> None:
        with pytest.raises(ValidationError):
            RequirementEntry(
                operation=DeltaOperation.REMOVED,
                req_id="FR-021",
                before="- **FR-021**: Gone.\n",
                shrink_intended=True,
                line_number=1,
            )

    def test_letter_suffixed_req_id_accepted(self) -> None:
        entry = RequirementEntry(
            operation=DeltaOperation.ADDED,
            req_id="FR-019c",
            after="- **FR-019c**: Clarified.\n",
            line_number=1,
        )
        assert entry.req_id == "FR-019c"

    def test_malformed_req_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RequirementEntry(
                operation=DeltaOperation.ADDED,
                req_id="FR-1",
                after="- **FR-1**: Bad id.\n",
                line_number=1,
            )


class TestTaskEntry:
    def test_added_carries_full_line(self) -> None:
        entry = TaskEntry(kind="added", task_id="T042", line="[P] [US3] Do the thing")
        assert entry.line == "[P] [US3] Do the thing"

    def test_added_without_line_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TaskEntry(kind="added", task_id="T042")

    def test_withdrawn_carries_no_line(self) -> None:
        entry = TaskEntry(kind="withdrawn", task_id="T017")
        assert entry.line is None

    def test_withdrawn_with_line_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TaskEntry(kind="withdrawn", task_id="T017", line="should not be here")

    def test_malformed_task_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TaskEntry(kind="withdrawn", task_id="X017")


class TestDeltaDocument:
    def _doc(self, path: Path, **overrides: object) -> DeltaDocument:
        defaults: dict[str, object] = {
            "path": path,
            "title": "Sample delta",
            "target_feature": "052-conditional-landing",
            "sequence": 1,
        }
        defaults.update(overrides)
        return DeltaDocument(**defaults)  # type: ignore[arg-type]

    def test_is_applied_true_under_archive(self, tmp_path: Path) -> None:
        doc = self._doc(tmp_path / "deltas" / "archive" / "001-x.md")
        assert doc.is_applied is True

    def test_is_applied_false_when_pending(self, tmp_path: Path) -> None:
        doc = self._doc(tmp_path / "deltas" / "001-x.md")
        assert doc.is_applied is False

    def test_is_empty_true_with_no_entries(self, tmp_path: Path) -> None:
        doc = self._doc(tmp_path / "deltas" / "001-x.md")
        assert doc.is_empty is True

    def test_is_empty_false_with_only_requirement_entries(self, tmp_path: Path) -> None:
        entry = RequirementEntry(
            operation=DeltaOperation.MODIFIED,
            req_id="FR-002",
            before="- **FR-002**: Old.\n",
            after="- **FR-002**: New.\n",
            line_number=5,
        )
        doc = self._doc(tmp_path / "deltas" / "001-x.md", requirement_entries=(entry,))
        assert doc.is_empty is False


class TestImpact:
    def test_blocking_impact_requires_task_id(self) -> None:
        with pytest.raises(ValidationError):
            Impact(bead_id="mv-1", bead_status="in_progress", reason="in-flight")

    def test_unstamped_impact_allows_empty_task_id(self) -> None:
        impact = Impact(bead_id="mv-1", bead_status="open", reason="unstamped")
        assert impact.task_id == ""

    def test_in_flight_impact(self) -> None:
        impact = Impact(
            task_id="T017", bead_id="mv-0417", bead_status="in_progress", reason="in-flight"
        )
        assert impact.reason == "in-flight"


class TestApplicationRecord:
    def test_carries_all_four_operation_keys(self) -> None:
        record = ApplicationRecord(
            applied_at="2026-08-23T09:14:02.113847+00:00",
            counts={"added": 1, "modified": 1, "removed": 1, "renamed": 1},
            task_counts={"added": 1, "withdrawn": 1},
            acknowledgements=(
                Acknowledgement(
                    task_id="T017",
                    bead_id="mv-0417",
                    bead_status="in_progress",
                    acknowledged_at="2026-08-23T09:13:55+00:00",
                ),
            ),
            shrink_intended_ids=("FR-014",),
        )
        assert set(record.counts) == {"added", "modified", "removed", "renamed"}
        assert record.shrink_intended_ids == ("FR-014",)
