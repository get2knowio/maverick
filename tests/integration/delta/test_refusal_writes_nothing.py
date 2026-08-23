"""FR-014/FR-016: every refusing apply path writes nothing.

Snapshots ``git status --porcelain``, a content hash of both artifacts,
and the full bead list before and after every refusing path, asserting
byte-identical. The snapshot helper is itself mutation-tested (fed a
deliberate change) so it is proven to be a real assertion, not a rubber
stamp.
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from maverick.beads.client import BeadClient
from maverick.speckit.delta.apply import apply_delta
from maverick.speckit.delta.parser import parse_delta_md
from maverick.speckit.delta.validate import DeltaValidationError
from tests.integration.delta.conftest import git_commit_all, git_status_porcelain, make_feature_dir

pytestmark = pytest.mark.integration


@dataclass(frozen=True, slots=True)
class _Snapshot:
    git_status: str
    spec_hash: str
    tasks_hash: str
    bead_ids: tuple[str, ...]


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


#: "Every bead regardless of status" — bd's query language has no
#: universal wildcard, so this enumerates the full status vocabulary.
_ALL_STATUSES_QUERY = (
    "status=open OR status=in_progress OR status=blocked OR status=deferred OR status=closed"
)


async def _snapshot(cwd: Path, feature_dir: Path, client: BeadClient) -> _Snapshot:
    beads = await client.query(_ALL_STATUSES_QUERY)
    return _Snapshot(
        git_status=git_status_porcelain(cwd),
        spec_hash=_hash(feature_dir / "spec.md"),
        tasks_hash=_hash(feature_dir / "tasks.md"),
        bead_ids=tuple(sorted(b.id for b in beads)),
    )


@pytest.mark.asyncio
async def test_snapshot_helper_is_not_a_rubber_stamp(bd_repo: Path) -> None:
    """Mutation test: a real change must make two snapshots differ."""
    feature_dir = make_feature_dir(bd_repo)
    git_commit_all(bd_repo)
    client = BeadClient(cwd=bd_repo)

    before = await _snapshot(bd_repo, feature_dir, client)
    (feature_dir / "spec.md").write_text("mutated", encoding="utf-8")
    after = await _snapshot(bd_repo, feature_dir, client)

    assert before != after
    assert before.spec_hash != after.spec_hash


@pytest.mark.asyncio
async def test_stale_before_refusal_writes_nothing(bd_repo: Path) -> None:
    feature_dir = make_feature_dir(bd_repo)
    git_commit_all(bd_repo)
    client = BeadClient(cwd=bd_repo)

    delta_text = (
        "# Delta: stale\n\n**Target**: 052-conditional-landing\n\n"
        "## MODIFIED FR-002\n\n### Before\n\n"
        "- **FR-002**: This does not match the current spec at all.\n\n"
        "### After\n\n- **FR-002**: Something new and long enough to pass the guard.\n"
    )
    delta_path = feature_dir / "deltas" / "001-stale.md"
    delta_path.write_text(delta_text, encoding="utf-8")
    document = parse_delta_md(delta_text, path=delta_path)

    before = await _snapshot(bd_repo, feature_dir, client)
    with pytest.raises(DeltaValidationError):
        await apply_delta(
            document, document_text=delta_text, feature_dir=feature_dir, client=client
        )
    after = await _snapshot(bd_repo, feature_dir, client)

    assert before == after
    assert delta_path.exists()


@pytest.mark.asyncio
async def test_unacknowledged_impact_refusal_writes_nothing(bd_repo: Path) -> None:
    feature_dir = make_feature_dir(bd_repo)
    client = BeadClient(cwd=bd_repo)

    epic = await client.create_bead(_epic_definition())
    await client.set_state(epic.bd_id, {"speckit_feature": "052-conditional-landing"})
    t017 = await client.create_bead(_task_definition("T017"), parent_id=epic.bd_id)
    await client.set_state(t017.bd_id, {"speckit_task_id": "T017"})
    subprocess.run(
        ["bd", "update", t017.bd_id, "--status", "in_progress"],
        cwd=bd_repo,
        check=True,
        capture_output=True,
    )
    git_commit_all(bd_repo)

    delta_text = (
        "# Delta: withdraw\n\n**Target**: 052-conditional-landing\n\n"
        "## TASKS\n\n- WITHDRAWN: T017\n"
    )
    delta_path = feature_dir / "deltas" / "002-withdraw.md"
    delta_path.write_text(delta_text, encoding="utf-8")
    document = parse_delta_md(delta_text, path=delta_path)

    before = await _snapshot(bd_repo, feature_dir, client)
    outcome = await apply_delta(
        document, document_text=delta_text, feature_dir=feature_dir, client=client
    )
    after = await _snapshot(bd_repo, feature_dir, client)

    assert outcome.status == "blocked"
    assert before == after
    assert delta_path.exists()


def _epic_definition():
    from maverick.beads.models import BeadCategory, BeadDefinition, BeadType

    return BeadDefinition(
        title="052 epic", bead_type=BeadType.EPIC, priority=1, category=BeadCategory.USER_STORY
    )


def _task_definition(task_id: str):
    from maverick.beads.models import BeadCategory, BeadDefinition, BeadType

    return BeadDefinition(
        title=f"{task_id} task",
        bead_type=BeadType.TASK,
        priority=2,
        category=BeadCategory.USER_STORY,
        task_ids=[task_id],
    )
