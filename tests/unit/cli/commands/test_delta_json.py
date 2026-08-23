"""CLI contract tests for ``maverick delta --json`` per
specs/059-spec-delta-layer/contracts/cli-delta-json.md.

Covers all four verbs (``delta.list``, ``delta.validate``, ``delta.apply``,
``delta.dry-run``): exactly one JSON document on stdout on every path,
the ``confirmation-required`` refusal envelope with ``outstanding``,
``delta.dry-run``'s ``would_block`` living in the result rather than an
error, already-applied as ``ok: true``, and every emitted ``error.kind``
being an existing :class:`ErrorKind` member.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from maverick.beads.models import BeadDetails, BeadSummary
from maverick.cli.json_output import ErrorKind
from maverick.main import cli

_SPEC_MD = """\
# Feature Specification: Sample

### Functional Requirements

- **FR-002**: The gate MUST evaluate the frontier before curating.
- **FR-021**: The gate MUST offer a `--force` bypass for operators.

### Key Entities
"""

_TASKS_MD = "## Phase 1: Setup\n\n- [ ] T017 An in-flight task\n"

_VALID_DELTA = (
    "# Delta: reword\n\n**Target**: 052-conditional-landing\n\n"
    "## MODIFIED FR-002\n\n### Before\n\n"
    "- **FR-002**: The gate MUST evaluate the frontier before curating.\n\n"
    "### After\n\n- **FR-002**: The gate MUST evaluate the assumption frontier "
    "before any curation step runs, on all three curation paths.\n"
)

_BAD_DELTA = (
    "# Delta: bad\n\n**Target**: 052-conditional-landing\n\n"
    "## MODIFIED FR-999\n\n### Before\n\n- **FR-999**: Nope.\n\n"
    "### After\n\n- **FR-999**: Still nope.\n"
)

_WITHDRAW_DELTA = (
    "# Delta: withdraw\n\n**Target**: 052-conditional-landing\n\n## TASKS\n\n- WITHDRAWN: T017\n"
)


@pytest.fixture
def feature_env(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(temp_dir)
    feature_dir = temp_dir / "specs" / "052-conditional-landing"
    (feature_dir / "deltas").mkdir(parents=True)
    (feature_dir / "spec.md").write_text(_SPEC_MD, encoding="utf-8")
    (feature_dir / "tasks.md").write_text(_TASKS_MD, encoding="utf-8")
    return feature_dir


@pytest.fixture(autouse=True)
def _mock_bd():
    epic = BeadSummary(id="mv-epic", title="epic", status="open", bead_type="epic")
    epic_details = BeadDetails(
        id="mv-epic",
        title="epic",
        status="open",
        state={"speckit_feature": "052-conditional-landing"},
    )
    children = [BeadSummary(id="mv-0417", title="T017 task", status="in_progress")]
    details_by_id = {
        "mv-epic": epic_details,
        "mv-0417": BeadDetails(
            id="mv-0417",
            title="T017 task",
            status="in_progress",
            state={"speckit_task_id": "T017"},
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
            "maverick.beads.client.BeadClient.verify_available", new=AsyncMock(return_value=True)
        ),
        patch("maverick.beads.client.BeadClient.query", new=AsyncMock(side_effect=_query)),
        patch("maverick.beads.client.BeadClient.children", new=AsyncMock(side_effect=_children)),
        patch("maverick.beads.client.BeadClient.show", new=AsyncMock(side_effect=_show)),
    ):
        yield


def _one_json_document(output: str) -> dict:
    """Assert stdout carries exactly one JSON document and return it."""
    lines = [line for line in output.splitlines() if line.strip()]
    assert len(lines) == 1, f"expected exactly one JSON line, got: {output!r}"
    return json.loads(lines[0])


class TestValidateVerb:
    def test_success_envelope(self, cli_runner: CliRunner, feature_env: Path) -> None:
        (feature_env / "deltas" / "001-reword.md").write_text(_VALID_DELTA, encoding="utf-8")
        result = cli_runner.invoke(cli, ["delta", "validate", "052/001-reword", "--json"])
        doc = _one_json_document(result.stdout)
        assert doc["ok"] is True
        assert doc["verb"] == "delta.validate"
        assert doc["result"]["requirements"]["modified"] == ["FR-002"]

    def test_failure_envelope_carries_problem_codes(
        self, cli_runner: CliRunner, feature_env: Path
    ) -> None:
        (feature_env / "deltas" / "002-bad.md").write_text(_BAD_DELTA, encoding="utf-8")
        result = cli_runner.invoke(cli, ["delta", "validate", "052/002-bad", "--json"])
        doc = _one_json_document(result.stdout)
        assert doc["ok"] is False
        assert doc["error"]["kind"] == "validation"
        codes = {p["code"] for p in doc["error"]["details"]["problems"]}
        assert "dangling-requirement" in codes
        assert ErrorKind(doc["error"]["kind"]) in ErrorKind


class TestApplyVerbConfirmationRequired:
    def test_unacknowledged_impacts_envelope(
        self, cli_runner: CliRunner, feature_env: Path
    ) -> None:
        (feature_env / "deltas" / "001-withdraw.md").write_text(_WITHDRAW_DELTA, encoding="utf-8")
        result = cli_runner.invoke(cli, ["delta", "apply", "052/001-withdraw", "--json"])
        doc = _one_json_document(result.stdout)
        assert doc["ok"] is False
        assert doc["error"]["kind"] == "confirmation-required"
        assert doc["error"]["details"]["outstanding"] == ["T017"]
        assert ErrorKind(doc["error"]["kind"]) in ErrorKind
        # Nothing written.
        assert (feature_env / "deltas" / "001-withdraw.md").exists()

    def test_unstamped_impact_never_appears_in_outstanding(
        self, cli_runner: CliRunner, feature_env: Path
    ) -> None:
        # An unstamped-bead impact (task_id == "") can never be cleared via
        # --ack (--ack only accepts task ids); `outstanding` must exclude
        # it rather than surface a bogus "" a scripted consumer can't act
        # on. The human renderer already filtered it; the JSON path must
        # match.
        mystery = BeadSummary(id="mv-mystery", title="mystery", status="open")
        mystery_details = BeadDetails(id="mv-mystery", title="mystery", status="open", state={})

        async def _children(parent_id: str):
            return [
                BeadSummary(id="mv-0417", title="T017 task", status="in_progress"),
                mystery,
            ]

        async def _show(bead_id: str):
            if bead_id == "mv-mystery":
                return mystery_details
            if bead_id == "mv-0417":
                return BeadDetails(
                    id="mv-0417",
                    title="T017 task",
                    status="in_progress",
                    state={"speckit_task_id": "T017"},
                )
            return BeadDetails(
                id="mv-epic",
                title="epic",
                status="open",
                state={"speckit_feature": "052-conditional-landing"},
            )

        (feature_env / "deltas" / "001-withdraw.md").write_text(_WITHDRAW_DELTA, encoding="utf-8")
        with (
            patch(
                "maverick.beads.client.BeadClient.children", new=AsyncMock(side_effect=_children)
            ),
            patch("maverick.beads.client.BeadClient.show", new=AsyncMock(side_effect=_show)),
        ):
            result = cli_runner.invoke(
                cli, ["delta", "apply", "052/001-withdraw", "--ack", "T017", "--json"]
            )
        doc = _one_json_document(result.stdout)
        assert doc["ok"] is False
        assert doc["error"]["kind"] == "confirmation-required"
        # T017 was acked; the unstamped bead has no task id and must not
        # leak into `outstanding` as an empty string.
        assert doc["error"]["details"]["outstanding"] == []
        reasons = {i["reason"] for i in doc["error"]["details"]["impacts"]}
        assert "unstamped" in reasons


class TestDryRunVerb:
    def test_would_block_lives_in_result_not_error(
        self, cli_runner: CliRunner, feature_env: Path
    ) -> None:
        (feature_env / "deltas" / "001-withdraw.md").write_text(_WITHDRAW_DELTA, encoding="utf-8")
        result = cli_runner.invoke(
            cli, ["delta", "apply", "052/001-withdraw", "--dry-run", "--json"]
        )
        doc = _one_json_document(result.stdout)
        assert doc["ok"] is True
        assert doc["verb"] == "delta.dry-run"
        assert doc["result"]["would_block"] is True
        assert doc["result"]["wrote_nothing"] is True
        # Nothing written even though would_block is true.
        assert (feature_env / "deltas" / "001-withdraw.md").exists()


class TestAlreadyApplied:
    def test_already_applied_is_ok_true(self, cli_runner: CliRunner, feature_env: Path) -> None:
        archive_dir = feature_env / "deltas" / "archive"
        archive_dir.mkdir(parents=True)
        text = (
            _VALID_DELTA.rstrip("\n")
            + "\n\n---\n\n## Applied\n\n**At**: 2026-08-19T00:00:00+00:00\n"
        )
        (archive_dir / "001-reword.md").write_text(text, encoding="utf-8")

        result = cli_runner.invoke(cli, ["delta", "apply", "052/001-reword", "--json"])
        doc = _one_json_document(result.stdout)
        assert doc["ok"] is True
        assert doc["verb"] == "delta.apply"
        assert doc["result"]["already_applied"] is True
        assert doc["result"]["applied_at"] == "2026-08-19T00:00:00+00:00"

    def test_dry_run_on_already_applied_reports_dry_run_verb(
        self, cli_runner: CliRunner, feature_env: Path
    ) -> None:
        # The Verbs table maps the *invocation* to the verb unconditionally
        # (`delta apply <d> --dry-run --json` -> `delta.dry-run`), not the
        # outcome — this must hold even when the delta turns out to already
        # be applied.
        archive_dir = feature_env / "deltas" / "archive"
        archive_dir.mkdir(parents=True)
        text = (
            _VALID_DELTA.rstrip("\n")
            + "\n\n---\n\n## Applied\n\n**At**: 2026-08-19T00:00:00+00:00\n"
        )
        (archive_dir / "001-reword.md").write_text(text, encoding="utf-8")

        result = cli_runner.invoke(
            cli, ["delta", "apply", "052/001-reword", "--dry-run", "--json"]
        )
        doc = _one_json_document(result.stdout)
        assert doc["ok"] is True
        assert doc["verb"] == "delta.dry-run"
        assert doc["result"]["already_applied"] is True


class TestListVerb:
    def test_list_json_shape(self, cli_runner: CliRunner, feature_env: Path) -> None:
        (feature_env / "deltas" / "001-reword.md").write_text(_VALID_DELTA, encoding="utf-8")
        result = cli_runner.invoke(cli, ["delta", "list", "052", "--json"])
        doc = _one_json_document(result.stdout)
        assert doc["ok"] is True
        feature = doc["result"]["features"][0]
        assert feature["feature"] == "052-conditional-landing"
        assert feature["pending"][0]["delta"] == "001-reword"


class TestNotFound:
    def test_unresolvable_feature_is_not_found(
        self, cli_runner: CliRunner, feature_env: Path
    ) -> None:
        result = cli_runner.invoke(cli, ["delta", "validate", "999/001-nope", "--json"])
        doc = _one_json_document(result.stdout)
        assert doc["ok"] is False
        assert doc["error"]["kind"] == "not-found"
        assert ErrorKind(doc["error"]["kind"]) in ErrorKind
