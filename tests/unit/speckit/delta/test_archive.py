"""Unit tests for speckit/delta/archive.py."""

from __future__ import annotations

from pathlib import Path

from maverick.speckit.delta.archive import archive_delta, list_delta_files
from maverick.speckit.delta.models import Acknowledgement, ApplicationRecord


def _record(**overrides: object) -> ApplicationRecord:
    defaults: dict[str, object] = {
        "applied_at": "2026-08-23T09:14:02.113847+00:00",
        "counts": {"added": 1, "modified": 1, "removed": 1, "renamed": 1},
        "task_counts": {"added": 1, "withdrawn": 1},
    }
    defaults.update(overrides)
    return ApplicationRecord(**defaults)  # type: ignore[arg-type]


class TestArchiveDelta:
    def test_move_happens_last_conceptually_destination_is_under_archive(self) -> None:
        source = Path("specs/052-conditional-landing/deltas/001-x.md")
        _, destination = archive_delta("# Delta: x\n", record=_record(), source_path=source)
        assert destination == Path("specs/052-conditional-landing/deltas/archive/001-x.md")

    def test_applied_record_carries_all_four_operation_keys(self) -> None:
        text, _ = archive_delta(
            "# Delta: x\n\nBody.\n", record=_record(), source_path=Path("d/1-x.md")
        )
        assert "**Operations**: 1 added, 1 modified, 1 removed, 1 renamed" in text
        assert "**Tasks**: 1 added, 1 withdrawn" in text

    def test_task_counts_present(self) -> None:
        text, _ = archive_delta("# Delta: x\n", record=_record(), source_path=Path("d/1-x.md"))
        assert "1 added, 1 withdrawn" in text

    def test_shrink_intended_ids_listed_as_declared_reductions(self) -> None:
        text, _ = archive_delta(
            "# Delta: x\n",
            record=_record(shrink_intended_ids=("FR-014",)),
            source_path=Path("d/1-x.md"),
        )
        assert "**Declared reductions**: FR-014" in text

    def test_no_shrink_intended_ids_omits_the_line(self) -> None:
        text, _ = archive_delta("# Delta: x\n", record=_record(), source_path=Path("d/1-x.md"))
        assert "Declared reductions" not in text

    def test_acknowledgements_carry_bead_status_at_time_cleared(self) -> None:
        record = _record(
            acknowledgements=(
                Acknowledgement(
                    task_id="T017",
                    bead_id="mv-0417",
                    bead_status="in_progress",
                    acknowledged_at="2026-08-23T09:13:55+00:00",
                ),
            )
        )
        text, _ = archive_delta("# Delta: x\n", record=record, source_path=Path("d/1-x.md"))
        assert "### Acknowledged impacts" in text
        assert "T017" in text and "mv-0417" in text and "in_progress" in text

    def test_original_document_body_is_preserved(self) -> None:
        text, _ = archive_delta(
            "# Delta: x\n\n**Target**: 052\n\n## ADDED FR-001\n",
            record=_record(),
            source_path=Path("d/1-x.md"),
        )
        assert text.startswith("# Delta: x\n\n**Target**: 052\n\n## ADDED FR-001")


class TestListDeltaFiles:
    def test_orders_by_numeric_prefix_not_alpha(self, tmp_path: Path) -> None:
        (tmp_path / "002-second.md").write_text("x", encoding="utf-8")
        (tmp_path / "010-tenth.md").write_text("x", encoding="utf-8")
        (tmp_path / "001-first.md").write_text("x", encoding="utf-8")
        names = [p.name for p in list_delta_files(tmp_path)]
        assert names == ["001-first.md", "002-second.md", "010-tenth.md"]

    def test_missing_directory_returns_empty(self, tmp_path: Path) -> None:
        assert list_delta_files(tmp_path / "nonexistent") == ()

    def test_ignores_non_markdown_files(self, tmp_path: Path) -> None:
        (tmp_path / "001-x.md").write_text("x", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
        names = [p.name for p in list_delta_files(tmp_path)]
        assert names == ["001-x.md"]


class TestPendingVsAppliedIsLocationOnly:
    def test_document_status_never_read_from_content(self, tmp_path: Path) -> None:
        # FR-023: a delta whose body literally contains the applied-record
        # markers is still "pending" while its path is outside archive/,
        # and "applied" once moved — location alone decides, never content.
        from maverick.speckit.delta.models import DeltaDocument

        deceptive_text = (
            "# Delta: looks applied but isn't\n\n**Target**: 052\n\n"
            "## Applied\n\n**At**: 2020-01-01T00:00:00+00:00\n"
        )
        pending_path = tmp_path / "deltas" / "001-x.md"
        pending_path.parent.mkdir(parents=True)
        pending_path.write_text(deceptive_text, encoding="utf-8")
        pending_doc = DeltaDocument(path=pending_path, title="t", target_feature="f", sequence=1)
        assert pending_doc.is_applied is False

        archived_path = tmp_path / "deltas" / "archive" / "002-y.md"
        archived_path.parent.mkdir(parents=True)
        archived_path.write_text(
            "# Delta: no applied marker at all\n\n**Target**: 052\n", encoding="utf-8"
        )
        archived_doc = DeltaDocument(path=archived_path, title="t", target_feature="f", sequence=2)
        assert archived_doc.is_applied is True
