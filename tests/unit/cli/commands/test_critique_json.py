"""CLI contract tests for ``maverick critique --json`` (T019-T022) per
specs/058-standalone-code-review/contracts/cli-critique-json.md.

House pattern (mirrors ``test_notify_json.py`` / ``test_reconcile_json.py``):
invoke through the root group so the real Click wiring, config load, and
``async_command`` bridge are exercised; ``monkeypatch.setattr(Path, "home",
...)`` points user config at ``temp_dir`` so a developer's own
``~/.maverick`` can never leak into an assertion.

Two seams are stubbed, both in the command's own namespace:

* ``resolve_diff_scope`` / ``BeadClient.children`` / ``bd_ready_reason`` —
  the VCS and ``bd`` reads. ``resolve_paths_scope`` is deliberately *not*
  stubbed: it is pure filesystem work against ``temp_dir``, so the
  nonexistent-path case can run for real.
* ``run_critique`` — the model call. Lens execution and report assembly are
  covered directly in ``tests/unit/critique/``; what these tests own is the
  CLI's envelope layer: one document on stdout, the right verb, the right
  ``ErrorKind``, and the exit code.

The one exception is :class:`TestEmptyScopeCostsNothing`, which lets
``run_critique`` run for real against an empty scope with the squadron
booby-trapped — the "zero model calls" promise (FR-009/SC-004) is not
provable against a canned report.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner, Result

from maverick.beads.models import BeadSummary
from maverick.cli.common import BD_MISSING
from maverick.cli.context import ExitCode
from maverick.cli.json_output import ErrorKind
from maverick.critique.models import (
    CritiqueReport,
    CritiqueScopeKind,
    LensOutcome,
    ResolvedScope,
)
from maverick.critique.runner import AllLensesFailedError
from maverick.critique.scope import ScopeResolutionError
from maverick.main import cli
from maverick.payloads import ReviewFindingPayload

_CONFIG_YAML = """
github:
  owner: "test-org"
  repo: "test-repo"
  default_branch: "main"

notifications:
  enabled: false
"""

#: Every ``error.kind`` string this contract is allowed to emit. FR-021: no
#: new ``ErrorKind`` value is introduced by this feature, so every member of
#: this set must already exist in the shared enum (asserted in
#: :class:`TestNoNewErrorKind`).
_EXPECTED_KINDS = {
    ErrorKind.VALIDATION,
    ErrorKind.NOT_FOUND,
    ErrorKind.BD_UNAVAILABLE,
    ErrorKind.VCS,
    ErrorKind.INTERNAL,
}


# --- fixtures / helpers ------------------------------------------------------


def _setup(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    os.chdir(temp_dir)
    monkeypatch.setattr(Path, "home", lambda: temp_dir)
    (temp_dir / "maverick.yaml").write_text(_CONFIG_YAML)


def _invoke(cli_runner: CliRunner, *args: str) -> Result:
    return cli_runner.invoke(cli, ["critique", *args])


def _sole_document(result: Result) -> dict[str, Any]:
    """Parse stdout, asserting it holds exactly one JSON document (SC-005).

    The count check is the load-bearing half: ``json.loads`` alone would
    happily accept a document that had progress narration appended after it
    only if the narration were unparseable — a single trailing line of prose
    can otherwise slip through a laxer assertion.
    """
    assert result.stdout.count("\n") == 1, f"stdout was not one line: {result.stdout!r}"
    data = json.loads(result.stdout)
    assert isinstance(data, dict)
    return data


def _scope(
    *,
    kind: CritiqueScopeKind = CritiqueScopeKind.DIFF,
    summary: str = "working copy vs main",
    paths: tuple[str, ...] = ("src/maverick/jj/client.py",),
    diff_text: str = "--- a\n+++ b\n",
    base: str | None = "main",
) -> ResolvedScope:
    return ResolvedScope(
        kind=kind,
        summary=summary,
        paths=paths,
        diff_text=diff_text,
        diff_stat=" src/maverick/jj/client.py |     3 +2 -1",
        base=base,
    )


def _empty_scope() -> ResolvedScope:
    return ResolvedScope(
        kind=CritiqueScopeKind.DIFF,
        summary="working copy vs main",
        paths=(),
        diff_text="",
        base="main",
    )


def _finding(
    *,
    severity: str = "major",
    issue: str = "unbounded retry loop",
    file: str = "src/maverick/jj/client.py",
    line: int | None = 42,
    reviewer: str = "correctness",
) -> ReviewFindingPayload:
    return ReviewFindingPayload(
        severity=severity,  # type: ignore[arg-type]
        issue=issue,
        file=file,
        line=line,
        reviewer=reviewer,  # type: ignore[arg-type]
    )


def _report(
    *,
    scope: ResolvedScope | None = None,
    lenses: tuple[LensOutcome, ...] = (),
    findings: tuple[ReviewFindingPayload, ...] = (),
    run_id: str = "ab12cd34",
) -> CritiqueReport:
    return CritiqueReport(
        run_id=run_id,
        created_at="2026-08-20T00:00:00+00:00",
        scope=scope if scope is not None else _scope(),
        lenses=lenses,
        findings=findings,
    )


def _both_lenses_clean() -> tuple[LensOutcome, ...]:
    return (
        LensOutcome(lens="correctness", approved=True),
        LensOutcome(lens="completeness", approved=True),
    )


def _stub_diff_scope(monkeypatch: pytest.MonkeyPatch, scope: ResolvedScope) -> None:
    monkeypatch.setattr(
        "maverick.cli.commands.critique.resolve_diff_scope",
        AsyncMock(return_value=scope),
    )


def _stub_run_critique(monkeypatch: pytest.MonkeyPatch, report: CritiqueReport) -> None:
    monkeypatch.setattr(
        "maverick.cli.commands.critique.run_critique",
        AsyncMock(return_value=report),
    )


def _stub_run_critique_raises(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    monkeypatch.setattr("maverick.cli.commands.critique.run_critique", AsyncMock(side_effect=exc))


def _stub_bd(monkeypatch: pytest.MonkeyPatch, *, children: list[BeadSummary]) -> None:
    monkeypatch.setattr("maverick.cli.commands.critique.bd_ready_reason", lambda cwd: None)
    monkeypatch.setattr(
        "maverick.beads.client.BeadClient.children",
        AsyncMock(return_value=children),
    )


def _success(
    cli_runner: CliRunner,
    temp_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    report: CritiqueReport,
    *args: str,
) -> tuple[Result, dict[str, Any]]:
    """Run a stubbed successful critique and return ``(result, document)``."""
    _setup(temp_dir, monkeypatch)
    _stub_diff_scope(monkeypatch, report.scope)
    _stub_run_critique(monkeypatch, report)
    result = _invoke(cli_runner, "--json", *args)
    return result, _sole_document(result)


# --- T019/T020: success envelopes -------------------------------------------


class TestSuccessEnvelope:
    def test_result_is_exactly_report_to_dict(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``result`` is the same projection the persisted artifact carries.

        Asserting equality against ``report.to_dict()`` rather than
        field-by-field is the point: the contract says the envelope and
        ``critique-report.json`` are the *same* body, and only a whole-body
        comparison can catch the CLI quietly adding or dropping a key.
        """
        report = _report(lenses=_both_lenses_clean(), findings=(_finding(),))

        result, data = _success(cli_runner, temp_dir, monkeypatch, report)

        assert result.exit_code == ExitCode.SUCCESS
        assert data["ok"] is True
        assert data["verb"] == "critique.run"
        assert data["schema_version"] == 1
        assert data["result"] == report.to_dict()
        assert "error" not in data

        # ...and the artifact on disk carries that same body, byte for byte.
        artifact = temp_dir / ".maverick" / "runs" / report.run_id / "critique-report.json"
        assert json.loads(artifact.read_text()) == data["result"]

    def test_findings_are_reported_with_severity_counts(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = _report(
            lenses=(
                LensOutcome(lens="correctness", approved=False, findings=(_finding(),)),
                LensOutcome(lens="completeness", approved=True),
            ),
            findings=(_finding(severity="critical"), _finding(severity="minor")),
        )

        result, data = _success(cli_runner, temp_dir, monkeypatch, report)

        assert result.exit_code == ExitCode.SUCCESS
        assert data["result"]["reviewed"] is True
        assert len(data["result"]["findings"]) == 2
        # Every severity key is present, zeros included.
        assert data["result"]["severity_counts"] == {"critical": 1, "major": 0, "minor": 1}

    def test_zero_findings_is_still_a_completed_review(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = _report(lenses=_both_lenses_clean())

        result, data = _success(cli_runner, temp_dir, monkeypatch, report)

        assert result.exit_code == ExitCode.SUCCESS
        assert data["ok"] is True
        assert data["verb"] == "critique.run"
        assert data["result"]["reviewed"] is True
        assert data["result"]["findings"] == []
        assert len(data["result"]["lenses"]) == 2
        assert [lens["lens"] for lens in data["result"]["lenses"]] == [
            "correctness",
            "completeness",
        ]
        assert all(lens["finding_count"] == 0 for lens in data["result"]["lenses"])


class TestEmptyScope:
    def test_empty_scope_is_success_not_reviewed(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = _report(scope=_empty_scope())

        result, data = _success(cli_runner, temp_dir, monkeypatch, report)

        assert result.exit_code == ExitCode.SUCCESS
        assert data["ok"] is True
        assert data["verb"] == "critique.run"
        assert data["result"]["reviewed"] is False
        assert data["result"]["lenses"] == []
        assert data["result"]["findings"] == []

    def test_empty_scope_is_distinguishable_from_reviewed_with_no_findings(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Both are ``ok: true`` with ``findings: []`` and exit 0 — the
        contract's stated way to tell them apart is ``reviewed`` plus the
        ``lenses`` array, so assert on both documents side by side rather
        than trusting either in isolation."""
        _setup(temp_dir, monkeypatch)

        empty = _report(scope=_empty_scope(), run_id="empty001")
        _stub_diff_scope(monkeypatch, empty.scope)
        _stub_run_critique(monkeypatch, empty)
        empty_doc = _sole_document(_invoke(cli_runner, "--json"))

        clean = _report(lenses=_both_lenses_clean(), run_id="clean001")
        _stub_diff_scope(monkeypatch, clean.scope)
        _stub_run_critique(monkeypatch, clean)
        clean_doc = _sole_document(_invoke(cli_runner, "--json"))

        assert empty_doc["ok"] == clean_doc["ok"] is True
        assert empty_doc["result"]["findings"] == clean_doc["result"]["findings"] == []

        assert empty_doc["result"]["reviewed"] is False
        assert empty_doc["result"]["lenses"] == []
        assert clean_doc["result"]["reviewed"] is True
        assert len(clean_doc["result"]["lenses"]) == 2


class TestEmptyScopeCostsNothing:
    """FR-009/SC-004: an empty scope must never reach a model. Unlike the
    rest of this file, ``run_critique`` runs for real here — a canned report
    cannot prove that the squadron was never constructed."""

    def test_empty_scope_never_builds_a_squadron(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        _stub_diff_scope(monkeypatch, _empty_scope())

        def _explode(*args: object, **kwargs: object) -> None:
            raise AssertionError("an empty scope must not construct a squadron")

        monkeypatch.setattr("maverick.critique.runner.CritiqueSquadron", _explode)

        result = _invoke(cli_runner, "--json")

        data = _sole_document(result)
        assert result.exit_code == ExitCode.SUCCESS
        assert data["ok"] is True
        assert data["result"]["reviewed"] is False
        assert data["result"]["lenses"] == []


class TestPartialLensFailure:
    def test_one_failed_lens_is_a_success_envelope(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """FR-011: one lens failing degrades the review, it does not void it.

        Making this a failure envelope was rejected by the contract for a
        concrete reason: the findings the surviving lens produced are real
        and useful, and discarding them because the other lens timed out
        would be strictly worse for the caller than handing them over with
        an ``error`` marker attached to the lens that died.
        """
        surviving = _finding(severity="critical", issue="dropped exception")
        report = _report(
            lenses=(
                LensOutcome(lens="correctness", approved=False, findings=(surviving,)),
                LensOutcome(lens="completeness", error="runtime timeout after 600s"),
            ),
            findings=(surviving,),
        )

        result, data = _success(cli_runner, temp_dir, monkeypatch, report)

        assert result.exit_code == ExitCode.SUCCESS
        assert data["ok"] is True
        assert data["verb"] == "critique.run"
        assert "error" not in data

        lenses = data["result"]["lenses"]
        assert lenses[1]["error"] == "runtime timeout after 600s"
        # A failed lens carries no verdict at all — "did not approve" and
        # "did not run" are different facts.
        assert "approved" not in lenses[1]
        assert "finding_count" not in lenses[1]

        # The surviving lens's findings are present, not discarded.
        assert lenses[0]["finding_count"] == 1
        assert len(data["result"]["findings"]) == 1
        assert data["result"]["findings"][0]["issue"] == "dropped exception"
        assert data["result"]["severity_counts"]["critical"] == 1


# --- T021: failure kinds (research R11) --------------------------------------


class TestFailureKinds:
    def test_conflicting_scopes_is_validation(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)

        result = _invoke(cli_runner, "--json", "--epic", "mv-0041", "src/")

        data = _sole_document(result)
        assert result.exit_code == ExitCode.FAILURE
        assert data["ok"] is False
        assert data["verb"] == "critique.run"
        assert data["error"]["kind"] == "validation"
        assert "result" not in data

    def test_base_with_paths_is_validation(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        (temp_dir / "src").mkdir()

        result = _invoke(cli_runner, "--json", "--base", "origin/main", "src")

        data = _sole_document(result)
        assert result.exit_code == ExitCode.FAILURE
        assert data["error"]["kind"] == "validation"

    def test_nonexistent_path_is_validation_not_not_found(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """research R11: a bad path is a bad *argument*, not a missing
        resource — ``not-found`` is reserved for the named epic."""
        _setup(temp_dir, monkeypatch)

        result = _invoke(cli_runner, "--json", "does/not/exist")

        data = _sole_document(result)
        assert result.exit_code == ExitCode.FAILURE
        assert data["ok"] is False
        assert data["error"]["kind"] == "validation"
        assert "does/not/exist" in data["error"]["message"]

    def test_unknown_epic_is_not_found_with_epic_id_detail(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        _stub_bd(monkeypatch, children=[])

        result = _invoke(cli_runner, "--json", "--epic", "mv-9999")

        data = _sole_document(result)
        assert result.exit_code == ExitCode.FAILURE
        assert data["ok"] is False
        assert data["verb"] == "critique.run"
        assert data["error"]["kind"] == "not-found"
        assert data["error"]["details"]["epic_id"] == "mv-9999"

    def test_bd_unavailable_on_epic_scope(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        monkeypatch.setattr(
            "maverick.cli.commands.critique.bd_ready_reason", lambda cwd: BD_MISSING
        )

        result = _invoke(cli_runner, "--json", "--epic", "mv-0041")

        data = _sole_document(result)
        assert result.exit_code == ExitCode.FAILURE
        assert data["ok"] is False
        assert data["error"]["kind"] == "bd-unavailable"

    def test_diff_scope_never_consults_bd(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """research R11: ``bd-unavailable`` is reachable on the epic scope
        only, so a repository without ``bd`` can still run the default
        invocation. A missing ``bd`` here must be invisible."""
        _setup(temp_dir, monkeypatch)
        monkeypatch.setattr(
            "maverick.cli.commands.critique.bd_ready_reason", lambda cwd: BD_MISSING
        )
        report = _report(lenses=_both_lenses_clean())
        _stub_diff_scope(monkeypatch, report.scope)
        _stub_run_critique(monkeypatch, report)

        result = _invoke(cli_runner, "--json")

        data = _sole_document(result)
        assert result.exit_code == ExitCode.SUCCESS
        assert data["ok"] is True

    def test_git_read_failure_is_vcs(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        monkeypatch.setattr(
            "maverick.cli.commands.critique.resolve_diff_scope",
            AsyncMock(
                side_effect=ScopeResolutionError(
                    "could not read the repository: bad revision 'main'"
                )
            ),
        )

        result = _invoke(cli_runner, "--json")

        data = _sole_document(result)
        assert result.exit_code == ExitCode.FAILURE
        assert data["ok"] is False
        assert data["verb"] == "critique.run"
        assert data["error"]["kind"] == "vcs"
        assert "could not read the repository" in data["error"]["message"]

    def test_both_lenses_failed_is_internal(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)
        _stub_diff_scope(monkeypatch, _scope())
        _stub_run_critique_raises(
            monkeypatch,
            AllLensesFailedError(
                "both reviewer lenses failed — correctness: boom; completeness: boom"
            ),
        )

        result = _invoke(cli_runner, "--json")

        data = _sole_document(result)
        assert result.exit_code == ExitCode.FAILURE
        assert data["ok"] is False
        assert data["verb"] == "critique.run"
        assert data["error"]["kind"] == "internal"
        assert "both reviewer lenses failed" in data["error"]["message"]


class TestNoNewErrorKind:
    """FR-021: this feature introduces no new ``ErrorKind`` value."""

    def test_every_expected_kind_is_an_existing_enum_member(self) -> None:
        existing = {kind.value for kind in ErrorKind}
        assert {kind.value for kind in _EXPECTED_KINDS} <= existing

    @pytest.mark.parametrize(
        ("args", "expected"),
        [
            (("--epic", "mv-0041", "src"), "validation"),
            (("does/not/exist",), "validation"),
        ],
    )
    def test_emitted_kinds_are_enum_members(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
        args: tuple[str, ...],
        expected: str,
    ) -> None:
        _setup(temp_dir, monkeypatch)

        result = _invoke(cli_runner, "--json", *args)

        data = _sole_document(result)
        kind = data["error"]["kind"]
        assert kind == expected
        assert kind in {member.value for member in ErrorKind}


# --- T022: --fail-on ---------------------------------------------------------


class TestFailOn:
    def test_met_threshold_is_success_envelope_with_nonzero_exit(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The one path where a non-zero exit carries ``ok: true``.

        The review *completed*; the non-zero exit is the gate the caller
        explicitly asked for, not a report that the command failed. A
        consumer that branches on the exit code alone will misread this as
        "the review could not be performed" and discard a perfectly good
        set of findings — so consumers must branch on ``ok`` and read the
        exit code only as the gate signal.
        """
        report = _report(
            lenses=(
                LensOutcome(lens="correctness", approved=False, findings=(_finding(),)),
                LensOutcome(lens="completeness", approved=True),
            ),
            findings=(_finding(severity="critical"),),
        )

        result, data = _success(cli_runner, temp_dir, monkeypatch, report, "--fail-on", "major")

        assert result.exit_code == ExitCode.FAILURE
        assert data["ok"] is True
        assert data["verb"] == "critique.run"
        assert "error" not in data
        assert data["result"] == report.to_dict()

    def test_unmet_threshold_exits_zero(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = _report(lenses=_both_lenses_clean(), findings=(_finding(severity="minor"),))

        result, data = _success(cli_runner, temp_dir, monkeypatch, report, "--fail-on", "major")

        assert result.exit_code == ExitCode.SUCCESS
        assert data["ok"] is True

    def test_fail_on_without_findings_exits_zero(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        report = _report(lenses=_both_lenses_clean())

        result, data = _success(cli_runner, temp_dir, monkeypatch, report, "--fail-on", "minor")

        assert result.exit_code == ExitCode.SUCCESS
        assert data["ok"] is True
        assert data["result"]["findings"] == []

    def test_invalid_fail_on_value_is_rejected_by_click(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """``--fail-on blocker`` never reaches the JSON layer: Click's
        ``Choice`` rejects it during parsing, so the usage error lands on
        stderr and stdout stays empty rather than carrying a half-envelope."""
        _setup(temp_dir, monkeypatch)

        result = _invoke(cli_runner, "--json", "--fail-on", "blocker")

        assert result.exit_code != ExitCode.SUCCESS
        assert result.stdout.strip() == ""


# --- Progress routing --------------------------------------------------------


class TestProgressRouting:
    def test_persistence_warning_goes_to_stderr_only(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """FR-018: a failed artifact write is a warning, never an outcome
        change — and in JSON mode that warning must not touch stdout, which
        carries exactly one document and nothing else."""
        _setup(temp_dir, monkeypatch)
        report = _report(lenses=_both_lenses_clean())
        _stub_diff_scope(monkeypatch, report.scope)
        _stub_run_critique(monkeypatch, report)
        monkeypatch.setattr(
            "maverick.cli.commands.critique.persist_report",
            lambda report, *, cwd: (_ for _ in ()).throw(OSError("read-only file system")),
        )

        result = _invoke(cli_runner, "--json")

        data = _sole_document(result)
        assert result.exit_code == ExitCode.SUCCESS
        assert data["ok"] is True
        assert "read-only file system" not in result.stdout
        assert "read-only file system" in result.stderr

    def test_degraded_persistence_reaches_the_envelope(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A machine consumer must be able to tell the artifact was not written.

        The human at the terminal gets a warning; without this key the JSON
        consumer would get a document indistinguishable from a clean run and
        would go looking for an artifact that does not exist. The key is
        envelope-only per the schema contract — the on-disk artifact, by
        definition, persisted.
        """
        _setup(temp_dir, monkeypatch)
        report = _report(lenses=_both_lenses_clean())
        _stub_diff_scope(monkeypatch, report.scope)
        _stub_run_critique(monkeypatch, report)
        monkeypatch.setattr(
            "maverick.cli.commands.critique.persist_report",
            lambda report, *, cwd: (_ for _ in ()).throw(OSError("read-only file system")),
        )

        data = _sole_document(_invoke(cli_runner, "--json"))

        assert data["ok"] is True
        assert data["result"]["degraded_persistence"] is True

    def test_clean_persistence_omits_the_degraded_key(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Absent rather than ``false`` — the contract omits absent keys."""
        _setup(temp_dir, monkeypatch)
        report = _report(lenses=_both_lenses_clean())
        _stub_diff_scope(monkeypatch, report.scope)
        _stub_run_critique(monkeypatch, report)

        data = _sole_document(_invoke(cli_runner, "--json"))

        assert "degraded_persistence" not in data["result"]

    def test_failure_envelope_stdout_holds_no_diagnostics(
        self,
        cli_runner: CliRunner,
        temp_dir: Path,
        clean_env: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _setup(temp_dir, monkeypatch)

        result = _invoke(cli_runner, "--json", "does/not/exist")

        data = _sole_document(result)
        assert data["ok"] is False
        # Nothing outside the envelope reached stdout.
        assert result.stdout.strip() == json.dumps(data, separators=(",", ":"))
