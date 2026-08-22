"""Unit tests for the ``maverick critique`` command surface (T015).

Contract: ``specs/058-standalone-code-review/contracts/cli-critique.md``.

House convention (mirrors ``tests/unit/cli/commands/test_notify_json.py`` and
``tests/unit/cli/test_land_command.py``): invoke through the *root* group so
``LazyGroup`` resolution and ``ctx.obj`` population are exercised — a command
that works under a direct ``invoke(critique, ...)`` but is unreachable from
``maverick critique`` is still broken.

Scope resolution, the reviewer, and persistence are patched at their import
sites in ``maverick.cli.commands.critique``; the module's own logic — scope
validation, exit-code policy, and the degraded-persistence path — runs for
real. JSON mode is deliberately absent here: it belongs to
``tests/unit/cli/commands/test_critique_json.py``.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maverick.cli.context import ExitCode
from maverick.critique.models import (
    CritiqueReport,
    CritiqueScopeKind,
    LensOutcome,
    ResolvedScope,
    order_findings,
)
from maverick.main import cli
from maverick.payloads import ReviewFindingPayload

if TYPE_CHECKING:
    from collections.abc import Iterator

    from click.testing import CliRunner, Result

_MODULE = "maverick.cli.commands.critique"


# ── Builders ────────────────────────────────────────────────────────


def _finding(
    *,
    severity: str = "major",
    issue: str = "something is off",
    file: str = "src/a.py",
    line: int | None = 42,
) -> ReviewFindingPayload:
    return ReviewFindingPayload(
        severity=severity,  # type: ignore[arg-type]
        issue=issue,
        file=file,
        line=line,
        reviewer="correctness",
    )


def _scope(
    *,
    kind: CritiqueScopeKind = CritiqueScopeKind.DIFF,
    summary: str = "working copy vs main",
    paths: tuple[str, ...] = ("src/a.py",),
) -> ResolvedScope:
    return ResolvedScope(
        kind=kind,
        summary=summary,
        paths=paths,
        diff_text="diff --git a b",
        base="main" if kind is CritiqueScopeKind.DIFF else None,
    )


def _report(
    *,
    scope: ResolvedScope | None = None,
    findings: tuple[ReviewFindingPayload, ...] = (),
) -> CritiqueReport:
    return CritiqueReport(
        run_id="a1b2c3d4",
        created_at="2026-08-22T18:04:11.913204+00:00",
        scope=scope if scope is not None else _scope(),
        lenses=(
            LensOutcome(lens="correctness", approved=not findings),
            LensOutcome(lens="completeness", approved=not findings),
        ),
        findings=order_findings(findings),
    )


class _Patched:
    """Handles for the patched collaborators, for call assertions."""

    def __init__(self, **mocks: Any) -> None:
        self.__dict__.update(mocks)

    diff: AsyncMock
    epic: AsyncMock
    paths: MagicMock
    run: AsyncMock
    persist: MagicMock


@contextmanager
def _patch_pipeline(
    *,
    report: CritiqueReport | None = None,
    scope: ResolvedScope | None = None,
    persist_error: OSError | None = None,
) -> Iterator[_Patched]:
    """Patch scope resolution, the reviewer, and persistence."""
    resolved = scope if scope is not None else _scope()
    result = report if report is not None else _report(scope=resolved)

    persist = MagicMock(
        return_value=(
            Path(".maverick/runs/a1b2c3d4/critique-report.json"),
            Path(".maverick/runs/a1b2c3d4/critique-report.md"),
        )
    )
    if persist_error is not None:
        persist.side_effect = persist_error

    with ExitStack() as stack:
        mocks = _Patched(
            diff=stack.enter_context(
                patch(f"{_MODULE}.resolve_diff_scope", new=AsyncMock(return_value=resolved))
            ),
            epic=stack.enter_context(
                patch(f"{_MODULE}.resolve_epic_scope", new=AsyncMock(return_value=resolved))
            ),
            paths=stack.enter_context(
                patch(f"{_MODULE}.resolve_paths_scope", new=MagicMock(return_value=resolved))
            ),
            run=stack.enter_context(
                patch(f"{_MODULE}.run_critique", new=AsyncMock(return_value=result))
            ),
            persist=stack.enter_context(patch(f"{_MODULE}.persist_report", new=persist)),
        )
        yield mocks


def _text(result: Result) -> str:
    """Everything the invocation printed, on either stream."""
    return f"{result.output}\n{result.stderr}"


@pytest.fixture(autouse=True)
def _in_temp_cwd(temp_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The command resolves ``Path.cwd()``; keep every run off the real repo."""
    monkeypatch.chdir(temp_dir)


# ── Reachability ────────────────────────────────────────────────────


class TestReachableThroughTheRootGroup:
    def test_help_resolves_through_the_lazy_group(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(cli, ["critique", "--help"])

        assert result.exit_code == ExitCode.SUCCESS
        for option in ["--base", "--epic", "--fail-on", "--json"]:
            assert option in result.output, f"missing {option}"

    def test_listed_in_the_root_group_help(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(cli, ["--help"])

        assert result.exit_code == ExitCode.SUCCESS
        assert "critique" in result.output


# ── Scope selection ─────────────────────────────────────────────────


class TestScopeSelection:
    def test_default_invocation_resolves_the_diff_against_main(
        self, cli_runner: CliRunner
    ) -> None:
        with _patch_pipeline() as mocks:
            result = cli_runner.invoke(cli, ["critique"])

        assert result.exit_code == ExitCode.SUCCESS, _text(result)
        mocks.diff.assert_awaited_once()
        assert mocks.diff.await_args.kwargs["base"] == "main"
        mocks.epic.assert_not_awaited()
        mocks.paths.assert_not_called()
        mocks.run.assert_awaited_once()

    def test_base_is_threaded_through_to_the_diff_resolver(self, cli_runner: CliRunner) -> None:
        with _patch_pipeline() as mocks:
            result = cli_runner.invoke(cli, ["critique", "--base", "origin/main"])

        assert result.exit_code == ExitCode.SUCCESS, _text(result)
        assert mocks.diff.await_args.kwargs["base"] == "origin/main"

    def test_paths_scope_uses_the_paths_resolver(self, cli_runner: CliRunner) -> None:
        scope = _scope(kind=CritiqueScopeKind.PATHS, summary="paths: src/maverick/jj/")
        with _patch_pipeline(scope=scope, report=_report(scope=scope)) as mocks:
            result = cli_runner.invoke(cli, ["critique", "src/maverick/jj/"])

        assert result.exit_code == ExitCode.SUCCESS, _text(result)
        mocks.paths.assert_called_once()
        assert mocks.paths.call_args.kwargs["paths"] == ("src/maverick/jj/",)
        mocks.diff.assert_not_awaited()

    def test_scope_summary_is_rendered_verbatim(self, cli_runner: CliRunner) -> None:
        scope = _scope(summary="working copy vs origin/main")
        with _patch_pipeline(scope=scope, report=_report(scope=scope)):
            result = cli_runner.invoke(cli, ["critique", "--base", "origin/main"])

        assert "Reviewing working copy vs origin/main" in result.output


class TestConflictingScopesAreRejected:
    """FR-004: an ambiguous invocation is rejected, never guessed.

    There is deliberately no precedence rule, so each case asserts that
    *both* selections are named — a message naming only the loser would read
    like the winner was intended.
    """

    @pytest.mark.parametrize(
        ("argv", "expected"),
        [
            (["critique", "--epic", "mv-0041", "--base", "origin/main"], ("--epic", "--base")),
            (["critique", "--epic", "mv-0041", "src/a.py"], ("--epic", "PATH arguments")),
            (["critique", "--base", "origin/main", "src/a.py"], ("--base", "PATH arguments")),
        ],
        ids=["epic+base", "epic+paths", "base+paths"],
    )
    def test_conflicting_selection_exits_non_zero_naming_both(
        self,
        cli_runner: CliRunner,
        argv: list[str],
        expected: tuple[str, str],
    ) -> None:
        with _patch_pipeline() as mocks:
            result = cli_runner.invoke(cli, argv)

        assert result.exit_code != ExitCode.SUCCESS
        output = _text(result)
        for name in expected:
            assert name in output, f"{name} missing from: {output}"
        # Rejected before any review is attempted.
        mocks.run.assert_not_awaited()


# ── Exit-code policy ────────────────────────────────────────────────


class TestFindingsAreNotFailure:
    """A completed review exits 0 no matter what it found.

    This is the single most important behavioral statement in the contract:
    ``critique`` is advisory, and a tool whose advice fails your shell by
    default gets wrapped in ``|| true`` and stops being read.
    """

    def test_critical_finding_still_exits_zero(self, cli_runner: CliRunner) -> None:
        report = _report(findings=(_finding(severity="critical", issue="unbounded read"),))
        with _patch_pipeline(report=report):
            result = cli_runner.invoke(cli, ["critique"])

        assert result.exit_code == ExitCode.SUCCESS, _text(result)
        assert "unbounded read" in result.output

    def test_empty_scope_exits_zero(self, cli_runner: CliRunner) -> None:
        empty = ResolvedScope(kind=CritiqueScopeKind.DIFF, summary="working copy vs main")
        with _patch_pipeline(scope=empty, report=_report(scope=empty)):
            result = cli_runner.invoke(cli, ["critique"])

        assert result.exit_code == ExitCode.SUCCESS, _text(result)
        assert "Nothing to review" in result.output


class TestFailOn:
    def test_critical_threshold_fails_on_a_critical_finding(self, cli_runner: CliRunner) -> None:
        report = _report(findings=(_finding(severity="critical"),))
        with _patch_pipeline(report=report):
            result = cli_runner.invoke(cli, ["critique", "--fail-on", "critical"])

        assert result.exit_code == ExitCode.FAILURE
        assert "--fail-on" in _text(result)
        # The findings are still reported — gating is not suppression.
        assert "something is off" in result.output

    def test_critical_threshold_passes_on_a_major_finding(self, cli_runner: CliRunner) -> None:
        report = _report(findings=(_finding(severity="major"),))
        with _patch_pipeline(report=report):
            result = cli_runner.invoke(cli, ["critique", "--fail-on", "critical"])

        assert result.exit_code == ExitCode.SUCCESS, _text(result)

    def test_major_threshold_fails_on_a_critical_finding(self, cli_runner: CliRunner) -> None:
        report = _report(findings=(_finding(severity="critical"),))
        with _patch_pipeline(report=report):
            result = cli_runner.invoke(cli, ["critique", "--fail-on", "major"])

        assert result.exit_code == ExitCode.FAILURE

    def test_no_threshold_never_gates(self, cli_runner: CliRunner) -> None:
        report = _report(findings=(_finding(severity="critical"),))
        with _patch_pipeline(report=report):
            result = cli_runner.invoke(cli, ["critique"])

        assert result.exit_code == ExitCode.SUCCESS, _text(result)

    def test_unknown_threshold_is_rejected_by_click(self, cli_runner: CliRunner) -> None:
        result = cli_runner.invoke(cli, ["critique", "--fail-on", "nit"])
        assert result.exit_code != ExitCode.SUCCESS


# ── Degraded persistence (FR-018) ───────────────────────────────────


class TestPersistenceFailureIsNotAFailure:
    def test_oserror_still_exits_zero_and_renders_the_findings(
        self, cli_runner: CliRunner
    ) -> None:
        report = _report(findings=(_finding(severity="critical", issue="unbounded read"),))
        with _patch_pipeline(report=report, persist_error=OSError("disk full")):
            result = cli_runner.invoke(cli, ["critique"])

        assert result.exit_code == ExitCode.SUCCESS, _text(result)
        assert "unbounded read" in result.output
        assert "1 finding — 1 critical, 0 major, 0 minor" in result.output

    def test_oserror_warns_and_suppresses_the_artifact_line(self, cli_runner: CliRunner) -> None:
        with _patch_pipeline(persist_error=OSError("disk full")):
            result = cli_runner.invoke(cli, ["critique"])

        output = _text(result)
        assert "could not write the findings artifact" in output
        assert "disk full" in output
        assert "critique-report.md" not in result.output

    def test_oserror_does_not_defeat_fail_on(self, cli_runner: CliRunner) -> None:
        report = _report(findings=(_finding(severity="critical"),))
        with _patch_pipeline(report=report, persist_error=OSError("disk full")):
            result = cli_runner.invoke(cli, ["critique", "--fail-on", "critical"])

        assert result.exit_code == ExitCode.FAILURE

    def test_successful_persistence_prints_the_artifact_path(self, cli_runner: CliRunner) -> None:
        with _patch_pipeline() as mocks:
            result = cli_runner.invoke(cli, ["critique"])

        assert result.exit_code == ExitCode.SUCCESS, _text(result)
        mocks.persist.assert_called_once()
        assert "critique-report.md" in result.output
