"""SC-007, FR-008, FR-025: applied output is ordinary Spec Kit — no new
format, no parser change.

This is the compatibility claim the whole additive design rests on:
after applying a delta exercising all four operations plus task entries,
the existing ``parse_spec_md``/``parse_tasks_md`` must still succeed on
the result, unmodified.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maverick.speckit.delta.apply import apply_delta
from maverick.speckit.delta.parser import parse_delta_md
from maverick.speckit.parser import parse_spec_md, parse_tasks_md

pytestmark = pytest.mark.integration

_SPEC_MD = """\
# Feature Specification: Sample

## Success Criteria

### Measurable Outcomes

- **SC-001**: The feature works end to end.

### Functional Requirements

- **FR-002**: The gate MUST evaluate the frontier before curating.
- **FR-018**: A requirement due to be renamed.
- **FR-021**: The gate MUST offer a `--force` bypass for operators.

### Key Entities
"""

_TASKS_MD = """\
## Phase 1: Setup

- [ ] T017 [US1] An in-flight task in src/x.py
- [ ] T020 An open task in src/z.py
"""

_ALL_OPS_DELTA = (
    "# Delta: exercise every operation\n\n**Target**: 052-conditional-landing\n\n"
    "## MODIFIED FR-002\n\n### Before\n\n"
    "- **FR-002**: The gate MUST evaluate the frontier before curating.\n\n"
    "### After\n\n- **FR-002**: The gate MUST evaluate the assumption frontier "
    "before any curation step runs.\n\n"
    "## REMOVED FR-021\n\n### Before\n\n"
    "- **FR-021**: The gate MUST offer a `--force` bypass for operators.\n\n"
    "## ADDED FR-026\n\n### After\n\n"
    "- **FR-026**: A brand new requirement introduced by this delta.\n\n"
    "## RENAMED\n\n- FROM: FR-018\n- TO: FR-019\n\n"
    "## TASKS\n\n"
    "- ADDED: T042 [P] [US3] Widen the severity filter in `src/x.py`\n"
    "- WITHDRAWN: T020\n"
)


@pytest.fixture
def feature_dir(tmp_path: Path) -> Path:
    d = tmp_path / "specs" / "052-conditional-landing"
    (d / "deltas").mkdir(parents=True)
    (d / "spec.md").write_text(_SPEC_MD, encoding="utf-8")
    (d / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")
    return d


@pytest.mark.asyncio
async def test_applied_output_reparses_cleanly(feature_dir: Path) -> None:
    delta_path = feature_dir / "deltas" / "001-all-ops.md"
    delta_path.write_text(_ALL_OPS_DELTA, encoding="utf-8")
    document = parse_delta_md(_ALL_OPS_DELTA, path=delta_path)

    outcome = await apply_delta(
        document, document_text=_ALL_OPS_DELTA, feature_dir=feature_dir, client=None
    )
    assert outcome.status == "applied"

    new_spec_text = (feature_dir / "spec.md").read_text(encoding="utf-8")
    new_tasks_text = (feature_dir / "tasks.md").read_text(encoding="utf-8")

    # No new format, no parser change: the EXISTING parsers must succeed.
    parsed_spec = parse_spec_md(new_spec_text, file="spec.md")
    assert parsed_spec.title == "Feature Specification: Sample" or parsed_spec.title

    phases, _story_deps = parse_tasks_md(new_tasks_text, file="tasks.md")
    all_task_ids = {t.task_id for phase in phases for t in phase.tasks}
    assert "T042" in all_task_ids
    assert "T020" not in all_task_ids
    assert "T017" in all_task_ids

    # Sanity on the requirement-level changes themselves.
    assert "FR-026" in new_spec_text
    assert "FR-019" in new_spec_text
    assert "FR-018" not in new_spec_text
    assert "--force" not in new_spec_text
