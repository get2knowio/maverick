"""Unit tests for speckit/delta/apply.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.speckit.delta.apply import apply_delta, apply_requirement_operations
from maverick.speckit.delta.models import DeltaOperation, RequirementEntry
from maverick.speckit.delta.parser import parse_delta_md
from maverick.speckit.requirements import parse_requirements

_SPEC_MD = """\
# Feature Specification: Sample

### Functional Requirements

- **FR-001**: The first requirement, untouched by every test below.
- **FR-002**: The gate MUST evaluate the frontier before curating.
- **FR-014**: The land gate MUST block on any open entry of medium or
  higher severity, including open legacy escalation beads.
- **FR-018**: A requirement due to be renamed.
- **FR-021**: The gate MUST offer a `--force` bypass for operators.

### Key Entities
"""

_TASKS_MD = """\
## Phase 1: Setup

- [ ] T001 Initialize project
- [ ] T017 [US1] An in-flight task in src/x.py

## Phase 2: Core

- [ ] T020 [US1] Another story task
"""


class TestOperationOrder:
    def test_renamed_before_removed_before_modified_before_added(self) -> None:
        # A document that names FR-002 through two operations: RENAMED
        # (FR-002 -> FR-003, but FR-003 doesn't exist so no collision) is
        # not realistic here — instead prove ordering via a requirement
        # renamed then the *new* id modified in the same document, which
        # only produces the right text if RENAMED runs first.
        section = parse_requirements(_SPEC_MD)
        entries = (
            RequirementEntry(
                operation=DeltaOperation.RENAMED,
                req_id="FR-018",
                new_req_id="FR-019",
                line_number=1,
            ),
            RequirementEntry(
                operation=DeltaOperation.MODIFIED,
                req_id="FR-019",
                before="- **FR-019**: A requirement due to be renamed.\n",
                after="- **FR-019**: A requirement that was renamed and reworded.\n",
                line_number=2,
            ),
        )
        new_section, summary = apply_requirement_operations(section, entries)
        assert summary.renamed == (("FR-018", "FR-019"),)
        assert summary.modified == ("FR-019",)
        block = new_section.block_by_id("FR-019")
        assert block is not None
        assert "renamed and reworded" in block.header_line
        assert new_section.block_by_id("FR-018") is None

    def test_untouched_requirements_are_byte_identical(self) -> None:
        section = parse_requirements(_SPEC_MD)
        entries = (
            RequirementEntry(
                operation=DeltaOperation.REMOVED,
                req_id="FR-021",
                before="- **FR-021**: The gate MUST offer a `--force` bypass for operators.\n",
                line_number=1,
            ),
        )
        new_section, _summary = apply_requirement_operations(section, entries)
        for req_id in ("FR-001", "FR-002", "FR-014", "FR-018"):
            original_block = section.block_by_id(req_id)
            new_block = new_section.block_by_id(req_id)
            assert original_block is not None
            assert new_block is not None
            assert original_block.all_lines == new_block.all_lines

    def test_removed_then_added_same_id_yields_added_not_conflict(self) -> None:
        # Two operations naming FR-021: REMOVED then ADDED — order-defined
        # outcome is "present" (ADDED runs last), regardless of document order.
        section = parse_requirements(_SPEC_MD)
        entries = (
            RequirementEntry(
                operation=DeltaOperation.ADDED,
                req_id="FR-021",
                after="- **FR-021**: A brand new FR-021 replacing the old one.\n",
                line_number=1,
            ),
            RequirementEntry(
                operation=DeltaOperation.REMOVED,
                req_id="FR-021",
                before="- **FR-021**: The gate MUST offer a `--force` bypass for operators.\n",
                line_number=2,
            ),
        )
        new_section, _summary = apply_requirement_operations(section, entries)
        block = new_section.block_by_id("FR-021")
        assert block is not None
        assert "brand new FR-021" in block.header_line


class TestApplyFullFlow:
    @pytest.fixture
    def feature_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "specs" / "052-conditional-landing"
        d.mkdir(parents=True)
        (d / "spec.md").write_text(_SPEC_MD, encoding="utf-8")
        (d / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")
        (d / "deltas").mkdir()
        return d

    @pytest.mark.asyncio
    async def test_no_task_entries_applies_quietly_tasks_untouched(
        self, feature_dir: Path
    ) -> None:
        delta_text = (
            "# Delta: reword\n\n**Target**: 052\n\n"
            "## MODIFIED FR-002\n\n"
            "### Before\n\n- **FR-002**: The gate MUST evaluate the frontier before curating.\n\n"
            "### After\n\n- **FR-002**: The gate MUST evaluate the assumption frontier before "
            "any curation step runs.\n"
        )
        delta_path = feature_dir / "deltas" / "001-reword.md"
        delta_path.write_text(delta_text, encoding="utf-8")
        document = parse_delta_md(delta_text, path=delta_path)

        outcome = await apply_delta(
            document, document_text=delta_text, feature_dir=feature_dir, client=None
        )

        assert outcome.status == "applied"
        assert outcome.requirements.modified == ("FR-002",)
        new_tasks_text = (feature_dir / "tasks.md").read_text(encoding="utf-8")
        assert new_tasks_text == _TASKS_MD
        assert not delta_path.exists()
        archived = feature_dir / "deltas" / "archive" / "001-reword.md"
        assert archived.is_file()
        assert "assumption frontier" in (feature_dir / "spec.md").read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_added_task_inserted_after_matching_story(self, feature_dir: Path) -> None:
        delta_text = (
            "# Delta: add task\n\n**Target**: 052\n\n"
            "## TASKS\n\n- ADDED: T042 [P] [US1] A brand new task in src/y.py\n"
        )
        delta_path = feature_dir / "deltas" / "001-add.md"
        delta_path.write_text(delta_text, encoding="utf-8")
        document = parse_delta_md(delta_text, path=delta_path)

        outcome = await apply_delta(
            document, document_text=delta_text, feature_dir=feature_dir, client=None
        )

        assert outcome.status == "applied"
        assert outcome.tasks.added == ("T042",)
        new_tasks_text = (feature_dir / "tasks.md").read_text(encoding="utf-8")
        lines = new_tasks_text.splitlines()
        t020_idx = next(i for i, line in enumerate(lines) if "T020" in line)
        t042_idx = next(i for i, line in enumerate(lines) if "T042" in line)
        assert t042_idx == t020_idx + 1

    @pytest.mark.asyncio
    async def test_withdrawn_task_removed_line_identical_otherwise(
        self, feature_dir: Path
    ) -> None:
        delta_text = "# Delta: withdraw\n\n**Target**: 052\n\n## TASKS\n\n- WITHDRAWN: T020\n"
        delta_path = feature_dir / "deltas" / "001-withdraw.md"
        delta_path.write_text(delta_text, encoding="utf-8")
        document = parse_delta_md(delta_text, path=delta_path)

        outcome = await apply_delta(
            document, document_text=delta_text, feature_dir=feature_dir, client=None
        )

        assert outcome.status == "applied"
        assert outcome.tasks.withdrawn == ("T020",)
        new_tasks_text = (feature_dir / "tasks.md").read_text(encoding="utf-8")
        assert "T020" not in new_tasks_text
        assert "T001" in new_tasks_text and "T017" in new_tasks_text

    @pytest.mark.asyncio
    async def test_apply_raises_on_invalid_delta(self, feature_dir: Path) -> None:
        from maverick.speckit.delta.validate import DeltaValidationError

        delta_text = (
            "# Delta: bad\n\n**Target**: 052\n\n"
            "## MODIFIED FR-999\n\n### Before\n\n- **FR-999**: Nope.\n\n"
            "### After\n\n- **FR-999**: Still nope.\n"
        )
        delta_path = feature_dir / "deltas" / "001-bad.md"
        delta_path.write_text(delta_text, encoding="utf-8")
        document = parse_delta_md(delta_text, path=delta_path)

        with pytest.raises(DeltaValidationError):
            await apply_delta(
                document, document_text=delta_text, feature_dir=feature_dir, client=None
            )

        # Nothing written.
        assert (feature_dir / "spec.md").read_text(encoding="utf-8") == _SPEC_MD
        assert delta_path.exists()
