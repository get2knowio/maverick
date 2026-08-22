"""Unit tests for ``maverick.critique.render`` (T009).

Contract: ``specs/058-standalone-code-review/contracts/cli-critique.md``,
"Human output" — the section order is fixed, the grouping is fixed, and the
two empty outcomes are deliberately different sentences (FR-016).

Rendering goes into a ``Console`` wrapping a ``StringIO`` so the assertions
are on the text a user actually sees. ``width=200`` keeps long finding lines
off the wrap boundary (an assertion on a wrapped substring is an assertion on
the terminal width, not on the renderer), and ``no_color=True`` keeps the
capture free of style codes.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

from maverick.critique.models import (
    CritiqueReport,
    CritiqueScopeKind,
    LensOutcome,
    ResolvedScope,
    order_findings,
)
from maverick.critique.render import render_report
from maverick.payloads import ReviewFindingPayload

# ── Builders ────────────────────────────────────────────────────────


def _finding(
    *,
    severity: str = "major",
    issue: str = "something is off",
    file: str = "src/a.py",
    line: int | None = 42,
    reviewer: str | None = "correctness",
) -> ReviewFindingPayload:
    return ReviewFindingPayload(
        severity=severity,  # type: ignore[arg-type]
        issue=issue,
        file=file,
        line=line,
        reviewer=reviewer,  # type: ignore[arg-type]
    )


def _scope(
    *,
    summary: str = "working copy vs main",
    paths: tuple[str, ...] = ("src/a.py", "src/b.py"),
    diff_text: str = "diff --git a b",
    truncated: bool = False,
) -> ResolvedScope:
    return ResolvedScope(
        kind=CritiqueScopeKind.DIFF,
        summary=summary,
        paths=paths,
        diff_text=diff_text,
        diff_truncated=truncated,
        base="main",
    )


def _report(
    *,
    scope: ResolvedScope | None = None,
    findings: tuple[ReviewFindingPayload, ...] = (),
    lenses: tuple[LensOutcome, ...] = (),
    degraded_persistence: bool = False,
) -> CritiqueReport:
    return CritiqueReport(
        run_id="a1b2c3d4",
        created_at="2026-08-22T18:04:11.913204+00:00",
        scope=scope if scope is not None else _scope(),
        lenses=lenses,
        # The runner hands the renderer canonically ordered findings; ordering
        # them here keeps these tests exercising the same input shape.
        findings=order_findings(findings),
        degraded_persistence=degraded_persistence,
    )


def _render(report: CritiqueReport, *, artifact_path: Path | None = None) -> str:
    buffer = io.StringIO()
    console = Console(file=buffer, width=200, no_color=True)
    render_report(report, console=console, artifact_path=artifact_path)
    return buffer.getvalue()


@pytest.fixture
def artifact() -> Path:
    return Path(".maverick/runs/a1b2c3d4/critique-report.md")


# ── Section order ───────────────────────────────────────────────────


class TestSectionOrder:
    """Every section is always present in the contract's fixed order."""

    def test_all_sections_render_in_contract_order(self, artifact: Path) -> None:
        report = _report(
            scope=_scope(truncated=True),
            lenses=(
                LensOutcome(lens="correctness", approved=False),
                LensOutcome(lens="completeness", error="provider timeout"),
            ),
            findings=(_finding(severity="critical", issue="unbounded read"),),
        )

        output = _render(report, artifact_path=artifact)

        positions = [
            output.index("Reviewing working copy vs main"),
            output.index("diff exceeded the embedding budget"),
            output.index("completeness lens failed"),
            output.index("src/a.py"),
            output.index("1 finding —"),
            output.index("Report:"),
        ]
        assert positions == sorted(positions), output

    def test_scope_line_reports_the_file_count(self) -> None:
        output = _render(_report(scope=_scope(paths=("src/a.py", "src/b.py"))))
        assert "Reviewing working copy vs main — 2 files" in output

    def test_scope_line_singularizes_one_file(self) -> None:
        output = _render(_report(scope=_scope(paths=("src/a.py",))))
        assert "— 1 file" in output
        assert "1 files" not in output

    def test_summary_counts_every_severity(self) -> None:
        report = _report(
            findings=(
                _finding(severity="critical"),
                _finding(severity="major", line=7),
                _finding(severity="major", line=9),
            )
        )
        output = _render(report)
        assert "3 findings — 1 critical, 2 major, 0 minor" in output


# ── Grouping ────────────────────────────────────────────────────────


class TestGrouping:
    """Files ascending, severity descending within a file, unattributed last."""

    def test_files_render_in_ascending_path_order(self) -> None:
        report = _report(
            findings=(
                _finding(file="src/z.py", issue="last file"),
                _finding(file="src/a.py", issue="first file"),
                _finding(file="src/m.py", issue="middle file"),
            )
        )
        output = _render(report)
        assert output.index("src/a.py") < output.index("src/m.py") < output.index("src/z.py")

    def test_findings_within_a_file_run_critical_major_minor(self) -> None:
        report = _report(
            findings=(
                _finding(severity="minor", issue="minor issue"),
                _finding(severity="critical", issue="critical issue"),
                _finding(severity="major", issue="major issue"),
            )
        )
        output = _render(report)
        assert (
            output.index("critical issue")
            < output.index("major issue")
            < output.index("minor issue")
        )

    def test_unattributed_bucket_renders_last(self) -> None:
        report = _report(
            findings=(
                _finding(file="", issue="no file for this one", severity="critical"),
                _finding(file="src/z.py", issue="this one has a file", severity="minor"),
            )
        )
        output = _render(report)

        assert "(unattributed)" in output
        # Last even though its finding is the more severe of the two.
        assert output.index("src/z.py") < output.index("(unattributed)")
        assert output.index("this one has a file") < output.index("no file for this one")

    def test_finding_line_carries_location_and_lens(self) -> None:
        report = _report(findings=(_finding(line=88, reviewer="completeness"),))
        output = _render(report)
        assert "L88" in output
        assert "(completeness)" in output

    def test_missing_line_renders_a_dash_placeholder(self) -> None:
        output = _render(_report(findings=(_finding(line=None, issue="no line"),)))
        finding_line = next(line for line in output.splitlines() if "no line" in line)
        assert "—" in finding_line
        assert "LNone" not in output


# ── Markup escaping ─────────────────────────────────────────────────


class TestMarkupEscaping:
    """Issue text is passed through ``rich.markup.escape`` before rendering."""

    def test_bracketed_issue_text_renders_literally(self) -> None:
        report = _report(findings=(_finding(issue="prefer [bold] over manual styling"),))

        output = _render(report)

        # Unescaped, rich would consume ``[bold]`` as a style tag and it would
        # vanish from the capture entirely.
        assert "prefer [bold] over manual styling" in output
        assert "\x1b" not in output

    def test_closing_tag_in_issue_text_survives(self) -> None:
        report = _report(findings=(_finding(issue="drop the [/red] suffix"),))
        output = _render(report)
        assert "drop the [/red] suffix" in output

    def test_bracketed_scope_summary_renders_literally(self) -> None:
        report = _report(scope=_scope(summary="paths: src/[bold]/"))
        output = _render(report)
        assert "paths: src/[bold]/" in output


# ── The two empty outcomes (FR-016) ─────────────────────────────────


class TestEmptyOutcomes:
    """ "Nothing was reviewed" and "reviewed, nothing found" are distinct.

    A user must never have to guess whether the reviewer was silent or absent.
    """

    def test_unreviewed_report_says_nothing_to_review(self) -> None:
        empty = ResolvedScope(
            kind=CritiqueScopeKind.DIFF,
            summary="working copy vs main",
            paths=(),
            diff_text="",
        )
        output = _render(_report(scope=empty))

        assert "Nothing to review" in output
        assert "working copy vs main" in output

    def test_unreviewed_report_renders_no_findings_section(self) -> None:
        empty = ResolvedScope(
            kind=CritiqueScopeKind.DIFF, summary="working copy vs main", paths=()
        )
        output = _render(_report(scope=empty), artifact_path=Path("report.md"))

        assert "No findings." not in output
        assert "Reviewing" not in output
        assert "Report:" not in output

    def test_reviewed_with_zero_findings_says_no_findings(self) -> None:
        output = _render(_report(findings=()))

        assert "Reviewing working copy vs main — 2 files" in output
        assert "No findings." in output
        assert "Nothing to review" not in output

    def test_the_two_empty_outcomes_are_different_text(self) -> None:
        reviewed = _render(_report(findings=()))
        unreviewed = _render(
            _report(
                scope=ResolvedScope(kind=CritiqueScopeKind.DIFF, summary="working copy vs main")
            )
        )
        assert reviewed != unreviewed

    def test_zero_findings_renders_no_summary_count(self) -> None:
        output = _render(_report(findings=()))
        assert "0 findings" not in output


# ── Truncation ──────────────────────────────────────────────────────


class TestTruncationNotice:
    def test_notice_renders_when_truncated(self) -> None:
        output = _render(_report(scope=_scope(truncated=True)))
        assert "diff exceeded the embedding budget" in output
        assert "read the remainder" in output

    def test_notice_absent_when_not_truncated(self) -> None:
        output = _render(_report(scope=_scope(truncated=False)))
        assert "embedding budget" not in output


# ── Lens failures ───────────────────────────────────────────────────


class TestLensFailures:
    def test_failure_names_the_lens_and_the_survivor(self) -> None:
        report = _report(
            lenses=(
                LensOutcome(lens="correctness", approved=True),
                LensOutcome(lens="completeness", error="provider timeout"),
            ),
            findings=(_finding(),),
        )

        output = _render(report)

        assert "the completeness lens failed" in output
        assert "provider timeout" in output
        assert "from the correctness lens only" in output

    def test_no_warning_when_every_lens_succeeded(self) -> None:
        report = _report(
            lenses=(
                LensOutcome(lens="correctness", approved=True),
                LensOutcome(lens="completeness", approved=True),
            )
        )
        output = _render(report)
        assert "lens failed" not in output

    def test_missing_error_text_degrades_to_unknown_error(self) -> None:
        # ``failed`` keys off ``error``, so this shape can only arrive from a
        # hand-built report — the renderer must still not interpolate ``None``.
        report = _report(lenses=(LensOutcome(lens="completeness", error=""),))
        output = _render(report)
        assert "unknown error" in output
        assert "None" not in output

    def test_error_text_is_escaped(self) -> None:
        report = _report(lenses=(LensOutcome(lens="completeness", error="bad [tag] here"),))
        output = _render(report)
        assert "bad [tag] here" in output


# ── Artifact line ───────────────────────────────────────────────────


class TestArtifactLine:
    def test_path_renders_when_given(self, artifact: Path) -> None:
        output = _render(_report(), artifact_path=artifact)
        assert f"Report: {artifact}" in output

    def test_no_line_when_no_artifact_path(self) -> None:
        output = _render(_report(), artifact_path=None)
        assert "Report:" not in output

    def test_degraded_persistence_warns_and_suppresses_the_path(self, artifact: Path) -> None:
        report = _report(degraded_persistence=True, findings=(_finding(),))

        output = _render(report, artifact_path=artifact)

        assert "findings artifact could not be written" in output
        assert "the findings above are complete" in output
        assert "Report:" not in output
        assert str(artifact) not in output

    def test_degraded_persistence_still_renders_the_findings(self) -> None:
        report = _report(
            degraded_persistence=True,
            findings=(_finding(issue="still reported", severity="critical"),),
        )
        output = _render(report, artifact_path=None)
        assert "still reported" in output
        assert "1 finding — 1 critical, 0 major, 0 minor" in output
