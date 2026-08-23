"""Unit tests for speckit/delta/validate.py — every row of the validation
table in contracts/delta-document-format.md, plus both sides of the
content-loss guard (SC-008, SC-008a)."""

from __future__ import annotations

from pathlib import Path

from maverick.speckit.delta.parser import parse_delta_md
from maverick.speckit.delta.validate import validate_delta
from maverick.speckit.parser import parse_tasks_md
from maverick.speckit.requirements import parse_requirements

_SPEC_MD = """\
# Feature Specification: Sample

### Functional Requirements

- **FR-001**: The system MUST do the first thing.
- **FR-002**: The gate MUST evaluate the frontier before curating.
- **FR-014**: The land gate MUST block on any open entry of medium or
  higher severity, including open legacy escalation beads, and MUST
  additionally check that curation has not already started before this
  point in the pipeline.
- **FR-021**: The gate MUST offer a `--force` bypass for operators.

### Key Entities
"""

_TASKS_MD = """\
## Phase 1: Setup

- [ ] T001 Initialize project
- [ ] T017 An in-flight task in src/x.py
"""

_PATH = Path("specs/052-conditional-landing/deltas/001-sample.md")


def _validate(delta_text: str) -> tuple:
    doc = parse_delta_md(delta_text, path=_PATH)
    section = parse_requirements(_SPEC_MD)
    phases, _ = parse_tasks_md(_TASKS_MD)
    return validate_delta(doc, spec_section=section, tasks_phases=phases)


def _codes(problems: tuple) -> list[str]:
    return [p.code for p in problems]


class TestValidDelta:
    def test_well_formed_modified_has_no_problems(self) -> None:
        problems = _validate(
            "# Delta: reword\n\n**Target**: 052\n\n"
            "## MODIFIED FR-002\n\n"
            "### Before\n\n- **FR-002**: The gate MUST evaluate the frontier before curating.\n\n"
            "### After\n\n- **FR-002**: The gate MUST evaluate the assumption frontier before "
            "any curation step runs, on all three curation paths.\n"
        )
        assert problems == ()


class TestDanglingRequirement:
    def test_modified_unknown_requirement(self) -> None:
        problems = _validate(
            "# Delta: bad\n\n**Target**: 052\n\n"
            "## MODIFIED FR-999\n\n### Before\n\n- **FR-999**: Nope.\n\n"
            "### After\n\n- **FR-999**: Still nope.\n"
        )
        assert "dangling-requirement" in _codes(problems)

    def test_removed_unknown_requirement(self) -> None:
        problems = _validate(
            "# Delta: bad\n\n**Target**: 052\n\n## REMOVED FR-999\n\n"
            "### Before\n\n- **FR-999**: Nope.\n"
        )
        assert "dangling-requirement" in _codes(problems)


class TestDuplicateRequirement:
    def test_added_id_already_defined(self) -> None:
        problems = _validate(
            "# Delta: bad\n\n**Target**: 052\n\n## ADDED FR-001\n\n"
            "### After\n\n- **FR-001**: Dup.\n"
        )
        assert "duplicate-requirement" in _codes(problems)

    def test_renamed_to_id_already_defined(self) -> None:
        problems = _validate(
            "# Delta: bad rename\n\n**Target**: 052\n\n## RENAMED\n\n"
            "- FROM: FR-021\n- TO: FR-001\n"
        )
        assert "duplicate-requirement" in _codes(problems)


class TestRenamedThenTouchedByNewId:
    """RENAMED runs first (OPERATION_ORDER); a later MODIFIED/REMOVED in
    the same document naming the RENAMED entry's *new* id must validate
    cleanly even though that id doesn't exist in the pre-apply spec —
    apply_requirement_operations already supports this pattern
    (test_apply.py's test_renamed_before_removed_before_modified_before_added);
    validate_delta must not refuse it as a false dangling-requirement."""

    def test_renamed_then_modified_by_new_id(self) -> None:
        problems = _validate(
            "# Delta: rename then reword\n\n**Target**: 052\n\n"
            "## RENAMED\n\n- FROM: FR-021\n- TO: FR-025\n\n"
            "## MODIFIED FR-025\n\n### Before\n\n"
            "- **FR-025**: Placeholder, not checked against the old spec.\n\n"
            "### After\n\n- **FR-025**: The gate MUST offer an override for operators.\n"
        )
        assert problems == ()

    def test_renamed_then_removed_by_new_id(self) -> None:
        problems = _validate(
            "# Delta: rename then remove\n\n**Target**: 052\n\n"
            "## RENAMED\n\n- FROM: FR-021\n- TO: FR-025\n\n"
            "## REMOVED FR-025\n\n### Before\n\n"
            "- **FR-025**: Placeholder, not checked against the old spec.\n"
        )
        assert problems == ()

    def test_modified_by_an_id_no_rename_ever_produces_still_dangling(self) -> None:
        # Guard the fix's precision: an id that is neither pre-existing
        # nor a same-document RENAMED target must still be dangling.
        problems = _validate(
            "# Delta: unrelated\n\n**Target**: 052\n\n"
            "## MODIFIED FR-777\n\n### Before\n\n- **FR-777**: Nope.\n\n"
            "### After\n\n- **FR-777**: Still nope.\n"
        )
        assert "dangling-requirement" in _codes(problems)


class TestConflictingOperations:
    def test_same_id_named_twice(self) -> None:
        problems = _validate(
            "# Delta: conflict\n\n**Target**: 052\n\n"
            "## MODIFIED FR-002\n\n### Before\n\n- **FR-002**: The gate MUST evaluate the "
            "frontier before curating.\n\n### After\n\n- **FR-002**: Changed once.\n\n"
            "## REMOVED FR-002\n\n### Before\n\n- **FR-002**: The gate MUST evaluate the "
            "frontier before curating.\n"
        )
        assert "conflicting-operations" in _codes(problems)


class TestContentLossGuard:
    """SC-008: catches truncation. SC-008a: does NOT fire on ordinary
    tightening — the test that matters more, since a guard that fires on
    routine edits trains authors to mark everything."""

    def test_sc008_shrink_past_floor_is_rejected(self) -> None:
        problems = _validate(
            "# Delta: over-shrink\n\n**Target**: 052\n\n"
            "## MODIFIED FR-014\n\n"
            "### Before\n\n"
            "- **FR-014**: The land gate MUST block on any open entry of medium or\n"
            "  higher severity, including open legacy escalation beads, and MUST\n"
            "  additionally check that curation has not already started before this\n"
            "  point in the pipeline.\n\n"
            "### After\n\n- **FR-014**: The gate MUST block.\n"
        )
        assert "content-loss" in _codes(problems)

    def test_sc008_dropped_sub_bullet_is_rejected(self) -> None:
        problems = _validate(
            "# Delta: drop bullet\n\n**Target**: 052\n\n"
            "## MODIFIED FR-002\n\n"
            "### Before\n\n"
            "- **FR-002**: The gate MUST evaluate the frontier before curating:\n"
            "  - Check one.\n"
            "  - Check two.\n\n"
            "### After\n\n"
            "- **FR-002**: The gate MUST evaluate the frontier before curating:\n"
            "  - Check one.\n"
        )
        assert "content-loss" in _codes(problems)

    def test_sc008a_ordinary_tightening_is_not_rejected(self) -> None:
        # One redundant clause removed — a normal edit, not truncation.
        problems = _validate(
            "# Delta: tighten\n\n**Target**: 052\n\n"
            "## MODIFIED FR-014\n\n"
            "### Before\n\n"
            "- **FR-014**: The land gate MUST block on any open entry of medium or\n"
            "  higher severity, including open legacy escalation beads, and MUST\n"
            "  additionally check that curation has not already started before this\n"
            "  point in the pipeline.\n\n"
            "### After\n\n"
            "- **FR-014**: The land gate MUST block on any open entry of medium or\n"
            "  higher severity, including open legacy escalation beads, and MUST\n"
            "  check that curation has not already started before this point in\n"
            "  the pipeline.\n"
        )
        assert "content-loss" not in _codes(problems)

    def test_shrink_intended_suppresses_the_guard(self) -> None:
        problems = _validate(
            "# Delta: declared shrink\n\n**Target**: 052\n\n"
            "## MODIFIED FR-014 [shrink-intended]\n\n"
            "### Before\n\n"
            "- **FR-014**: The land gate MUST block on any open entry of medium or\n"
            "  higher severity, including open legacy escalation beads, and MUST\n"
            "  additionally check that curation has not already started before this\n"
            "  point in the pipeline.\n\n"
            "### After\n\n- **FR-014**: The gate MUST block.\n"
        )
        assert "content-loss" not in _codes(problems)


class TestTaskEntries:
    def test_withdrawn_unknown_task(self) -> None:
        problems = _validate(
            "# Delta: bad task\n\n**Target**: 052\n\n"
            "## MODIFIED FR-002\n\n### Before\n\n- **FR-002**: The gate MUST evaluate the "
            "frontier before curating.\n\n### After\n\n- **FR-002**: Reworded.\n\n"
            "## TASKS\n\n- WITHDRAWN: T099\n"
        )
        assert "unknown-task" in _codes(problems)

    def test_withdrawn_known_task_is_fine(self) -> None:
        problems = _validate(
            "# Delta: fine\n\n**Target**: 052\n\n"
            "## ADDED FR-026\n\n### After\n\n- **FR-026**: A brand new requirement.\n\n"
            "## TASKS\n\n- WITHDRAWN: T017\n"
        )
        assert problems == ()

    def test_added_task_id_collision(self) -> None:
        problems = _validate(
            "# Delta: collide\n\n**Target**: 052\n\n## TASKS\n\n- ADDED: T001 Duplicate id\n"
        )
        assert "duplicate-task" in _codes(problems)

    def test_duplicate_task_within_delta(self) -> None:
        problems = _validate(
            "# Delta: dupe\n\n**Target**: 052\n\n"
            "## TASKS\n\n- WITHDRAWN: T017\n- WITHDRAWN: T017\n"
        )
        assert "duplicate-task" in _codes(problems)


class TestEmptyDelta:
    def test_zero_entries_is_rejected(self) -> None:
        doc = parse_delta_md("# Delta: nothing\n\n**Target**: 052\n", path=_PATH)
        section = parse_requirements(_SPEC_MD)
        problems = validate_delta(doc, spec_section=section)
        assert _codes(problems) == ["empty-delta"]
