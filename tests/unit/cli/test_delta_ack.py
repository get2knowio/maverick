"""CLI tests for ``maverick delta apply --ack`` (FR-014, FR-015, FR-015b).

Partial ``--ack`` still refuses; every impact named lets the apply
proceed; an ``--ack`` naming a non-impact fails rather than being
ignored; there is no blanket override flag.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from maverick.beads.models import BeadDetails, BeadSummary
from maverick.main import cli

_SPEC_MD = """\
# Feature Specification: Sample

### Functional Requirements

- **FR-021**: The gate MUST offer a `--force` bypass for operators.

### Key Entities
"""

_TASKS_MD = "## Phase 1: Setup\n\n- [ ] T017 An in-flight task\n- [ ] T019 A closed task\n"

_DELTA_TEXT = (
    "# Delta: withdraw two\n\n**Target**: 052-conditional-landing\n\n"
    "## TASKS\n\n- WITHDRAWN: T017\n- WITHDRAWN: T019\n"
)


@pytest.fixture
def feature_env(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(temp_dir)
    feature_dir = temp_dir / "specs" / "052-conditional-landing"
    (feature_dir / "deltas").mkdir(parents=True)
    (feature_dir / "spec.md").write_text(_SPEC_MD, encoding="utf-8")
    (feature_dir / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")
    (feature_dir / "deltas" / "001-withdraw.md").write_text(_DELTA_TEXT, encoding="utf-8")
    return feature_dir


@pytest.fixture(autouse=True)
def _mock_bd(feature_env: Path):
    epic = BeadSummary(id="mv-epic", title="epic", status="open", bead_type="epic")
    epic_details = BeadDetails(
        id="mv-epic",
        title="epic",
        status="open",
        state={"speckit_feature": "052-conditional-landing"},
    )
    children = [
        BeadSummary(id="mv-0417", title="T017 task", status="in_progress"),
        BeadSummary(id="mv-0419", title="T019 task", status="closed"),
    ]
    details_by_id = {
        "mv-epic": epic_details,
        "mv-0417": BeadDetails(
            id="mv-0417",
            title="T017 task",
            status="in_progress",
            state={"speckit_task_id": "T017"},
        ),
        "mv-0419": BeadDetails(
            id="mv-0419", title="T019 task", status="closed", state={"speckit_task_id": "T019"}
        ),
    }

    async def _query(expr: str):
        return [epic]

    async def _children(parent_id: str):
        return children

    async def _show(bead_id: str):
        return details_by_id[bead_id]

    with (
        patch("shutil.which", return_value="/usr/bin/bd"),
        patch("maverick.beads.client.BeadClient.is_initialized", return_value=True),
        patch(
            "maverick.beads.client.BeadClient.verify_available",
            new=AsyncMock(return_value=True),
        ),
        patch("maverick.beads.client.BeadClient.query", new=AsyncMock(side_effect=_query)),
        patch("maverick.beads.client.BeadClient.children", new=AsyncMock(side_effect=_children)),
        patch("maverick.beads.client.BeadClient.show", new=AsyncMock(side_effect=_show)),
    ):
        yield


class TestPartialAck:
    def test_partial_ack_still_refuses(self, cli_runner: CliRunner, feature_env: Path) -> None:
        result = cli_runner.invoke(cli, ["delta", "apply", "052/001-withdraw", "--ack", "T017"])
        assert result.exit_code == 1
        assert "T019" in result.output
        # Nothing written.
        assert (feature_env / "deltas" / "001-withdraw.md").exists()
        assert (feature_env / "tasks.md").read_text(encoding="utf-8") == _TASKS_MD


class TestFullAck:
    def test_every_impact_acknowledged_lets_apply_proceed(
        self, cli_runner: CliRunner, feature_env: Path
    ) -> None:
        result = cli_runner.invoke(
            cli, ["delta", "apply", "052/001-withdraw", "--ack", "T017", "--ack", "T019"]
        )
        assert result.exit_code == 0, result.output
        assert not (feature_env / "deltas" / "001-withdraw.md").exists()
        assert (feature_env / "deltas" / "archive" / "001-withdraw.md").is_file()


class TestStaleAck:
    def test_ack_naming_a_non_impact_fails(self, cli_runner: CliRunner, feature_env: Path) -> None:
        result = cli_runner.invoke(
            cli, ["delta", "apply", "052/001-withdraw", "--ack", "T017", "--ack", "T099"]
        )
        assert result.exit_code == 1
        assert "T099" in result.output
        # Nothing written — a stale ack must fail, not be ignored.
        assert (feature_env / "deltas" / "001-withdraw.md").exists()


class TestNoBlanketOverride:
    def test_no_force_flag_exists(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(cli, ["delta", "apply", "--help"])
        assert result.exit_code == 0
        assert "--force" not in result.output
