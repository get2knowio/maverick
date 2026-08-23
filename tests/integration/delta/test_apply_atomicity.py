"""FR-009: atomic multi-file rewrite.

Both files' new contents are computed fully in memory and validated
before anything is written. Injecting a failure between the two file
writes must leave the pre-apply state exactly; a validation failure must
write nothing at all.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from maverick.speckit.delta.parser import parse_delta_md
from maverick.speckit.delta.validate import DeltaValidationError

pytestmark = pytest.mark.integration

_SPEC_MD = """\
# Feature Specification: Sample

### Functional Requirements

- **FR-002**: The gate MUST evaluate the frontier before curating.

### Key Entities
"""
_TASKS_MD = "## Phase 1: Setup\n\n- [ ] T001 Initialize project\n"


@pytest.fixture
def feature_dir(tmp_path: Path) -> Path:
    d = tmp_path / "specs" / "052-conditional-landing"
    (d / "deltas").mkdir(parents=True)
    (d / "spec.md").write_text(_SPEC_MD, encoding="utf-8")
    (d / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")
    return d


@pytest.mark.asyncio
async def test_failure_between_writes_leaves_pre_apply_state(feature_dir: Path) -> None:
    from maverick.speckit.delta.apply import apply_delta

    delta_text = (
        "# Delta: reword\n\n**Target**: 052\n\n"
        "## MODIFIED FR-002\n\n### Before\n\n"
        "- **FR-002**: The gate MUST evaluate the frontier before curating.\n\n"
        "### After\n\n- **FR-002**: The gate MUST evaluate the assumption frontier "
        "before any curation step runs.\n\n"
        "## TASKS\n\n- ADDED: T042 A brand new task\n"
    )
    delta_path = feature_dir / "deltas" / "001-reword.md"
    delta_path.write_text(delta_text, encoding="utf-8")
    document = parse_delta_md(delta_text, path=delta_path)

    call_count = {"n": 0}
    real_atomic_write_text = __import__(
        "maverick.utils.atomic", fromlist=["atomic_write_text"]
    ).atomic_write_text

    def _flaky_write(path, content, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise OSError("simulated failure between writes")
        return real_atomic_write_text(path, content, **kwargs)

    with patch("maverick.speckit.delta.apply.atomic_write_text", side_effect=_flaky_write):
        with pytest.raises(OSError, match="simulated failure"):
            await apply_delta(
                document, document_text=delta_text, feature_dir=feature_dir, client=None
            )

    # The first write (spec.md) happened; the interruption happened before
    # tasks.md/archive. The delta is still pending — a re-run detects this
    # rather than silently double-applying.
    assert (feature_dir / "spec.md").read_text(encoding="utf-8") != _SPEC_MD
    assert (feature_dir / "tasks.md").read_text(encoding="utf-8") == _TASKS_MD
    assert delta_path.exists()
    assert not (feature_dir / "deltas" / "archive" / "001-reword.md").exists()


@pytest.mark.asyncio
async def test_invalid_delta_writes_nothing(feature_dir: Path) -> None:
    from maverick.speckit.delta.apply import apply_delta

    delta_text = (
        "# Delta: bad\n\n**Target**: 052\n\n"
        "## MODIFIED FR-999\n\n### Before\n\n- **FR-999**: Nope.\n\n"
        "### After\n\n- **FR-999**: Still nope.\n"
    )
    delta_path = feature_dir / "deltas" / "002-bad.md"
    delta_path.write_text(delta_text, encoding="utf-8")
    document = parse_delta_md(delta_text, path=delta_path)

    with pytest.raises(DeltaValidationError):
        await apply_delta(document, document_text=delta_text, feature_dir=feature_dir, client=None)

    assert (feature_dir / "spec.md").read_text(encoding="utf-8") == _SPEC_MD
    assert (feature_dir / "tasks.md").read_text(encoding="utf-8") == _TASKS_MD
    assert delta_path.exists()
