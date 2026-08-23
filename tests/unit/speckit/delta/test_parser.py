"""Unit tests for speckit/delta/parser.py — the grammar in
contracts/delta-document-format.md."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.speckit.delta.errors import DeltaFormatError
from maverick.speckit.delta.models import DeltaOperation
from maverick.speckit.delta.parser import parse_delta_md

_PATH = Path("specs/052-conditional-landing/deltas/001-sample.md")


def _parse(text: str) -> object:
    return parse_delta_md(text, path=_PATH)


class TestHeader:
    def test_title_and_target(self) -> None:
        doc = _parse(
            "# Delta: tighten the frontier gate\n\n"
            "**Target**: 052-conditional-landing\n\n"
            "## ADDED FR-026\n\n### After\n\n- **FR-026**: A new requirement.\n"
        )
        assert doc.title == "tighten the frontier gate"
        assert doc.target_feature == "052-conditional-landing"

    def test_missing_title_rejected(self) -> None:
        with pytest.raises(DeltaFormatError) as exc_info:
            _parse("**Target**: 052-conditional-landing\n")
        assert exc_info.value.code == "malformed-document"

    def test_missing_target_rejected(self) -> None:
        with pytest.raises(DeltaFormatError) as exc_info:
            _parse("# Delta: no target here\n\n## ADDED FR-001\n\n### After\n\n- **FR-001**: X.\n")
        assert exc_info.value.code == "malformed-document"


class TestOperations:
    def test_added_requires_after_only(self) -> None:
        doc = _parse(
            "# Delta: add one\n\n**Target**: 052\n\n"
            "## ADDED FR-026\n\n### After\n\n- **FR-026**: New requirement.\n"
        )
        (entry,) = doc.requirement_entries
        assert entry.operation is DeltaOperation.ADDED
        assert entry.after == "- **FR-026**: New requirement.\n"
        assert entry.before is None

    def test_modified_requires_before_and_after(self) -> None:
        doc = _parse(
            "# Delta: modify one\n\n**Target**: 052\n\n"
            "## MODIFIED FR-014\n\n"
            "### Before\n\n- **FR-014**: Old text.\n\n"
            "### After\n\n- **FR-014**: New text.\n"
        )
        (entry,) = doc.requirement_entries
        assert entry.operation is DeltaOperation.MODIFIED
        assert entry.before == "- **FR-014**: Old text.\n"
        assert entry.after == "- **FR-014**: New text.\n"

    def test_removed_requires_before_only(self) -> None:
        doc = _parse(
            "# Delta: remove one\n\n**Target**: 052\n\n"
            "## REMOVED FR-021\n\n### Before\n\n- **FR-021**: Gone.\n"
        )
        (entry,) = doc.requirement_entries
        assert entry.operation is DeltaOperation.REMOVED
        assert entry.before == "- **FR-021**: Gone.\n"
        assert entry.after is None

    def test_shrink_intended_marker(self) -> None:
        doc = _parse(
            "# Delta: shrink one\n\n**Target**: 052\n\n"
            "## MODIFIED FR-014 [shrink-intended]\n\n"
            "### Before\n\n- **FR-014**: A very long requirement text here.\n\n"
            "### After\n\n- **FR-014**: Short.\n"
        )
        (entry,) = doc.requirement_entries
        assert entry.shrink_intended is True

    def test_multiline_before_after_block(self) -> None:
        doc = _parse(
            "# Delta: multiline\n\n**Target**: 052\n\n"
            "## MODIFIED FR-014\n\n"
            "### Before\n\n"
            "- **FR-014**: The gate MUST evaluate the frontier before\n"
            "  curating, on every path.\n\n"
            "### After\n\n"
            "- **FR-014**: The gate MUST evaluate the assumption frontier\n"
            "  before any curation step runs, on all three curation paths.\n"
        )
        (entry,) = doc.requirement_entries
        assert entry.before is not None
        assert "curating, on every path." in entry.before
        assert entry.after is not None
        assert "on all three curation paths." in entry.after

    def test_unknown_operation_keyword_rejected(self) -> None:
        with pytest.raises(DeltaFormatError) as exc_info:
            _parse(
                "# Delta: bad op\n\n**Target**: 052\n\n## DELETED FR-001\n\n"
                "### Before\n\n- **FR-001**: X.\n"
            )
        assert exc_info.value.code == "malformed-document"

    def test_added_with_before_rejected(self) -> None:
        # The model forbids ADDED carrying a 'before' block; the parser
        # must translate that rejection into a DeltaFormatError (not a
        # raw pydantic.ValidationError, which no CLI handler catches).
        with pytest.raises(DeltaFormatError) as exc_info:
            _parse(
                "# Delta: bad added\n\n**Target**: 052\n\n"
                "## ADDED FR-026\n\n"
                "### Before\n\n- **FR-026**: Should not be here.\n\n"
                "### After\n\n- **FR-026**: New.\n"
            )
        assert exc_info.value.code == "malformed-document"

    def test_shrink_intended_on_removed_rejected(self) -> None:
        # The grammar's [shrink-intended] suffix is syntactically legal
        # after any of ADDED/MODIFIED/REMOVED, but the model only honors
        # it for MODIFIED — the parser must translate that mismatch into
        # a DeltaFormatError too, not a raw pydantic.ValidationError.
        with pytest.raises(DeltaFormatError) as exc_info:
            _parse(
                "# Delta: bad shrink\n\n**Target**: 052\n\n"
                "## REMOVED FR-021 [shrink-intended]\n\n"
                "### Before\n\n- **FR-021**: Gone.\n"
            )
        assert exc_info.value.code == "malformed-document"


class TestRenamed:
    def test_single_pair(self) -> None:
        doc = _parse(
            "# Delta: rename\n\n**Target**: 052\n\n## RENAMED\n\n- FROM: FR-018\n- TO: FR-019\n"
        )
        (entry,) = doc.requirement_entries
        assert entry.operation is DeltaOperation.RENAMED
        assert entry.req_id == "FR-018"
        assert entry.new_req_id == "FR-019"

    def test_multiple_pairs(self) -> None:
        doc = _parse(
            "# Delta: rename many\n\n**Target**: 052\n\n"
            "## RENAMED\n\n"
            "- FROM: FR-018\n- TO: FR-019\n"
            "- FROM: FR-030\n- TO: FR-031\n"
        )
        assert len(doc.requirement_entries) == 2

    def test_unbalanced_from_without_to_rejected(self) -> None:
        with pytest.raises(DeltaFormatError) as exc_info:
            _parse("# Delta: bad rename\n\n**Target**: 052\n\n## RENAMED\n\n- FROM: FR-018\n")
        assert exc_info.value.code == "unbalanced-rename"

    def test_to_without_from_rejected(self) -> None:
        with pytest.raises(DeltaFormatError) as exc_info:
            _parse("# Delta: bad rename\n\n**Target**: 052\n\n## RENAMED\n\n- TO: FR-019\n")
        assert exc_info.value.code == "unbalanced-rename"

    def test_empty_renamed_section_rejected(self) -> None:
        with pytest.raises(DeltaFormatError):
            _parse(
                "# Delta: empty rename\n\n**Target**: 052\n\n## RENAMED\n\n"
                "## TASKS\n\n- WITHDRAWN: T001\n"
            )


class TestTasks:
    def test_added_and_withdrawn(self) -> None:
        doc = _parse(
            "# Delta: tasks\n\n**Target**: 052\n\n"
            "## ADDED FR-026\n\n### After\n\n- **FR-026**: New.\n\n"
            "## TASKS\n\n"
            "- ADDED: T042 [P] [US3] Widen the severity filter in `src/x.py`\n"
            "- WITHDRAWN: T017\n"
        )
        added = [t for t in doc.task_entries if t.kind == "added"]
        withdrawn = [t for t in doc.task_entries if t.kind == "withdrawn"]
        assert added[0].task_id == "T042"
        assert added[0].line == "T042 [P] [US3] Widen the severity filter in `src/x.py`"
        assert withdrawn[0].task_id == "T017"

    def test_absent_tasks_section_is_normal(self) -> None:
        # FR-007b: an absent ## TASKS section parses as normal, not an error.
        doc = _parse(
            "# Delta: no tasks\n\n**Target**: 052\n\n"
            "## MODIFIED FR-002\n\n### Before\n\n- **FR-002**: Old.\n\n"
            "### After\n\n- **FR-002**: New.\n"
        )
        assert doc.task_entries == ()

    def test_malformed_added_task_line_rejected(self) -> None:
        with pytest.raises(DeltaFormatError) as exc_info:
            _parse(
                "# Delta: bad task\n\n**Target**: 052\n\n"
                "## TASKS\n\n- ADDED: not a real task line\n"
            )
        assert exc_info.value.code == "malformed-task-line"

    def test_malformed_withdrawn_task_id_rejected(self) -> None:
        # _TASK_WITHDRAWN_RE captures any \S+ after 'WITHDRAWN:'; the
        # model's own T\d{3,} validator is what actually rejects a
        # malformed id — the parser must translate that into a
        # DeltaFormatError, not a raw pydantic.ValidationError.
        with pytest.raises(DeltaFormatError) as exc_info:
            _parse(
                "# Delta: bad withdrawn\n\n**Target**: 052\n\n"
                "## TASKS\n\n- WITHDRAWN: not-a-real-id\n"
            )
        assert exc_info.value.code == "malformed-document"

    def test_unknown_tasks_entry_rejected(self) -> None:
        with pytest.raises(DeltaFormatError):
            _parse("# Delta: bad tasks entry\n\n**Target**: 052\n\n## TASKS\n\n- MOVED: T001\n")
