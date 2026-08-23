"""FR-010: applying an already-applied delta is a reported no-op, with
the artifacts unchanged."""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.speckit.delta.apply import apply_delta
from maverick.speckit.delta.archive import render_application_record
from maverick.speckit.delta.models import ApplicationRecord
from maverick.speckit.delta.parser import parse_delta_md

_SPEC_MD = """\
# Feature Specification: Sample

### Functional Requirements

- **FR-001**: The only requirement.

### Key Entities
"""

_TASKS_MD = "## Phase 1: Setup\n\n- [ ] T001 Initialize project\n"


@pytest.fixture
def feature_dir(tmp_path: Path) -> Path:
    d = tmp_path / "specs" / "052-conditional-landing"
    d.mkdir(parents=True)
    (d / "spec.md").write_text(_SPEC_MD, encoding="utf-8")
    (d / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")
    return d


@pytest.mark.asyncio
async def test_already_applied_delta_is_a_reported_noop(feature_dir: Path) -> None:
    original_text = (
        "# Delta: already done\n\n**Target**: 052\n\n## ADDED FR-002\n\n"
        "### After\n\n- **FR-002**: New.\n"
    )
    record = ApplicationRecord(
        applied_at="2026-08-19T00:00:00+00:00",
        counts={"added": 1, "modified": 0, "removed": 0, "renamed": 0},
        task_counts={"added": 0, "withdrawn": 0},
    )
    archived_text = original_text.rstrip("\n") + "\n" + render_application_record(record)
    archive_dir = feature_dir / "deltas" / "archive"
    archive_dir.mkdir(parents=True)
    archived_path = archive_dir / "001-already.md"
    archived_path.write_text(archived_text, encoding="utf-8")

    document = parse_delta_md(archived_text, path=archived_path)
    assert document.is_applied is True

    spec_before = (feature_dir / "spec.md").read_text(encoding="utf-8")
    tasks_before = (feature_dir / "tasks.md").read_text(encoding="utf-8")

    outcome = await apply_delta(
        document, document_text=archived_text, feature_dir=feature_dir, client=None
    )

    assert outcome.status == "already_applied"
    assert outcome.applied_at == "2026-08-19T00:00:00+00:00"
    # Nothing touched — spec.md/tasks.md unchanged, archived file untouched.
    assert (feature_dir / "spec.md").read_text(encoding="utf-8") == spec_before
    assert (feature_dir / "tasks.md").read_text(encoding="utf-8") == tasks_before
    assert archived_path.read_text(encoding="utf-8") == archived_text


@pytest.mark.asyncio
async def test_reapplying_twice_in_a_row_is_idempotent(feature_dir: Path) -> None:
    delta_text = (
        "# Delta: once\n\n**Target**: 052\n\n## ADDED FR-002\n\n### After\n\n- **FR-002**: New.\n"
    )
    pending_dir = feature_dir / "deltas"
    pending_dir.mkdir()
    pending_path = pending_dir / "001-once.md"
    pending_path.write_text(delta_text, encoding="utf-8")
    document = parse_delta_md(delta_text, path=pending_path)

    first = await apply_delta(
        document, document_text=delta_text, feature_dir=feature_dir, client=None
    )
    assert first.status == "applied"
    assert first.archived_to is not None

    # Re-resolve as the CLI would: pending is gone, archive now holds it.
    archived_text = first.archived_to.read_text(encoding="utf-8")
    second_document = parse_delta_md(archived_text, path=first.archived_to)
    second = await apply_delta(
        second_document, document_text=archived_text, feature_dir=feature_dir, client=None
    )
    assert second.status == "already_applied"
