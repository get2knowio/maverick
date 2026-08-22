"""Unit tests for :mod:`maverick.critique.report`.

Contract: ``specs/058-standalone-code-review/contracts/critique-report-schema.md``.

The pairing assertion — every finding in the JSON also appears in the
markdown (:meth:`TestMarkdownAgreesWithJson`) — is what makes SC-006
checkable: the two artifacts are one projection rendered twice, never two
sets of findings that could drift.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from maverick.critique.models import (
    CritiqueReport,
    CritiqueScopeKind,
    LensOutcome,
    ResolvedScope,
    ScopedCommit,
)
from maverick.critique.report import persist_report, render_markdown, report_paths
from maverick.payloads import ReviewFindingPayload

if TYPE_CHECKING:
    from pathlib import Path

RUN_ID = "a1b2c3d4"
CREATED_AT = "2026-08-22T18:04:11.913204+00:00"


def _finding(
    *,
    severity: str = "major",
    issue: str = "something",
    file: str = "a.py",
    line: int | None = None,
    reviewer: str | None = "correctness",
) -> ReviewFindingPayload:
    return ReviewFindingPayload(
        severity=severity,  # type: ignore[arg-type]
        issue=issue,
        file=file,
        line=line,
        reviewer=reviewer,  # type: ignore[arg-type]
    )


def _diff_scope(*, truncated: bool = False) -> ResolvedScope:
    return ResolvedScope(
        kind=CritiqueScopeKind.DIFF,
        summary="working copy vs main",
        paths=("a.py", "b.py"),
        diff_text="diff --git a/a.py b/a.py",
        diff_truncated=truncated,
        base="main",
    )


def _epic_scope() -> ResolvedScope:
    return ResolvedScope(
        kind=CritiqueScopeKind.EPIC,
        summary="epic mv-0041 (2 commits)",
        paths=("a.py",),
        diff_text="### 9de3a34",
        epic_id="mv-0041",
        commits=(
            ScopedCommit(
                sha="9de3a34",
                subject="bead(mv-0042): resolve epic scope",
                bead_ids=("mv-0042",),
            ),
            ScopedCommit(
                sha="1f0c9bb",
                subject="bead(mv-0043): render the report",
                bead_ids=("mv-0043", "mv-0044"),
            ),
        ),
    )


def _report(
    *,
    scope: ResolvedScope | None = None,
    findings: tuple[ReviewFindingPayload, ...] = (),
    lenses: tuple[LensOutcome, ...] | None = None,
) -> CritiqueReport:
    return CritiqueReport(
        run_id=RUN_ID,
        created_at=CREATED_AT,
        scope=scope if scope is not None else _diff_scope(),
        lenses=(
            lenses
            if lenses is not None
            else (
                LensOutcome(lens="correctness", approved=not findings, findings=findings),
                LensOutcome(lens="completeness", approved=True),
            )
        ),
        findings=findings,
    )


def _populated_report(**kwargs: object) -> CritiqueReport:
    """A report with findings spread over two files and all three severities."""
    findings = (
        _finding(file="a.py", severity="critical", issue="unbounded log read", line=88),
        _finding(
            file="a.py",
            severity="major",
            issue="missing timeout on the adapter call",
            reviewer="completeness",
        ),
        _finding(file="b.py", severity="minor", issue="stale docstring", line=4),
    )
    return _report(findings=findings, **kwargs)  # type: ignore[arg-type]


class TestReportPaths:
    def test_paths_hang_off_the_run_directory(self, tmp_path: Path) -> None:
        json_path, md_path = report_paths(RUN_ID, cwd=tmp_path)

        run_dir = tmp_path / ".maverick" / "runs" / RUN_ID
        assert json_path == run_dir / "critique-report.json"
        assert md_path == run_dir / "critique-report.md"

    def test_paths_are_run_scoped(self, tmp_path: Path) -> None:
        first, _ = report_paths("aaaaaaaa", cwd=tmp_path)
        second, _ = report_paths("bbbbbbbb", cwd=tmp_path)

        assert first != second


class TestPersistReport:
    def test_writes_both_artifacts(self, tmp_path: Path) -> None:
        report = _populated_report()

        json_path, md_path = persist_report(report, cwd=tmp_path)

        assert (json_path, md_path) == report_paths(RUN_ID, cwd=tmp_path)
        assert json_path.exists()
        assert md_path.exists()

    def test_json_is_exactly_the_projection(self, tmp_path: Path) -> None:
        report = _populated_report(scope=_epic_scope())

        json_path, _ = persist_report(report, cwd=tmp_path)

        assert json.loads(json_path.read_text(encoding="utf-8")) == report.to_dict()

    def test_markdown_is_exactly_the_rendering(self, tmp_path: Path) -> None:
        report = _populated_report()

        _, md_path = persist_report(report, cwd=tmp_path)

        assert md_path.read_text(encoding="utf-8") == render_markdown(report)

    def test_creates_the_run_directory(self, tmp_path: Path) -> None:
        assert not (tmp_path / ".maverick").exists()

        persist_report(_report(), cwd=tmp_path)

        assert (tmp_path / ".maverick" / "runs" / RUN_ID).is_dir()

    def test_os_error_propagates_to_the_caller(self, tmp_path: Path) -> None:
        """FR-018: the *caller* degrades this, so the writer must not swallow it.

        ``.maverick`` is a regular file here, so creating the run directory
        genuinely fails — no patching needed to produce the real failure mode.
        """
        (tmp_path / ".maverick").write_text("not a directory", encoding="utf-8")

        with pytest.raises(OSError):
            persist_report(_report(), cwd=tmp_path)

    def test_markdown_write_failure_also_propagates(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        def _boom(*args: object, **kwargs: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr("maverick.critique.report.atomic_write_text", _boom)

        with pytest.raises(OSError, match="disk full"):
            persist_report(_report(), cwd=tmp_path)


class TestRenderMarkdownHeader:
    def test_includes_scope_summary_and_run_id(self) -> None:
        md = render_markdown(_populated_report())

        assert "# Code review findings" in md
        assert "**Scope**: working copy vs main" in md
        assert f"**Run**: `{RUN_ID}`" in md
        assert f"**Generated**: {CREATED_AT}" in md

    def test_empty_scope_renders_nothing_to_review(self) -> None:
        empty = ResolvedScope(kind=CritiqueScopeKind.DIFF, summary="working copy vs main")
        md = render_markdown(_report(scope=empty, lenses=()))

        assert "Nothing to review" in md
        # None of the reviewed-path sections leak into the empty rendering.
        assert "No findings." not in md
        assert "## Commits reviewed" not in md
        assert "finding" not in md.split("Nothing to review")[1]

    def test_reviewed_with_no_findings_says_so(self) -> None:
        md = render_markdown(_report())

        assert "No findings." in md
        assert "Nothing to review" not in md


class TestRenderMarkdownFindings:
    def test_groups_findings_by_file_in_canonical_order(self) -> None:
        md = render_markdown(_populated_report())

        assert "### a.py" in md
        assert "### b.py" in md
        assert md.index("### a.py") < md.index("### b.py")
        # Within a file: critical before major.
        assert md.index("unbounded log read") < md.index("missing timeout")

    def test_renders_severity_counts_and_a_total(self) -> None:
        md = render_markdown(_populated_report())

        assert "## 3 findings — 1 critical, 1 major, 1 minor" in md

    def test_single_finding_is_not_pluralized(self) -> None:
        md = render_markdown(_report(findings=(_finding(),)))

        assert "## 1 finding — 0 critical, 1 major, 0 minor" in md

    def test_line_and_lens_are_rendered_when_known(self) -> None:
        md = render_markdown(_populated_report())

        assert "- **critical** (L88) _correctness_ — unbounded log read" in md
        # No line number degrades to a dash rather than a bogus location.
        assert "- **major** (—) _completeness_ — missing timeout on the adapter call" in md

    def test_unattributed_findings_get_their_own_heading(self) -> None:
        md = render_markdown(_report(findings=(_finding(file="", issue="global concern"),)))

        assert "### (unattributed)" in md
        assert "global concern" in md


class TestRenderMarkdownCommits:
    def test_commits_section_appears_only_for_an_epic_scope(self) -> None:
        epic_md = render_markdown(_populated_report(scope=_epic_scope()))
        diff_md = render_markdown(_populated_report())

        assert "## Commits reviewed" in epic_md
        assert "## Commits reviewed" not in diff_md

    def test_commits_list_sha_subject_and_attributed_beads(self) -> None:
        md = render_markdown(_populated_report(scope=_epic_scope()))

        assert "- `9de3a34` bead(mv-0042): resolve epic scope (mv-0042)" in md
        assert "- `1f0c9bb` bead(mv-0043): render the report (mv-0043, mv-0044)" in md


class TestRenderMarkdownWarnings:
    def test_truncation_note_only_when_truncated(self) -> None:
        note = "The embedded diff was truncated"

        assert note not in render_markdown(_populated_report())
        assert note in render_markdown(_populated_report(scope=_diff_scope(truncated=True)))

    def test_lens_failure_renders_a_blockquote(self) -> None:
        report = _report(
            findings=(_finding(issue="from the survivor"),),
            lenses=(
                LensOutcome(lens="correctness", error="provider exploded"),
                LensOutcome(
                    lens="completeness",
                    approved=False,
                    findings=(_finding(issue="from the survivor"),),
                ),
            ),
        )

        md = render_markdown(report)

        assert "> The correctness lens failed: provider exploded" in md
        # The surviving lens's findings still render in full.
        assert "from the survivor" in md

    def test_no_blockquote_when_every_lens_succeeded(self) -> None:
        md = render_markdown(_populated_report())

        assert "lens failed" not in md


class TestMarkdownAgreesWithJson:
    """SC-006: the artifact pair can never disagree about what was found."""

    @pytest.mark.parametrize("truncated", [False, True])
    def test_every_json_finding_appears_in_the_markdown(self, truncated: bool) -> None:
        report = _populated_report(scope=_diff_scope(truncated=truncated))

        md = render_markdown(report)
        payload = report.to_dict()

        assert payload["findings"]
        for finding in payload["findings"]:
            assert finding["issue"] in md
            assert f"**{finding['severity']}**" in md
            if finding["file"]:
                assert f"### {finding['file']}" in md
            else:
                assert "### (unattributed)" in md
            if "line" in finding:
                assert f"(L{finding['line']})" in md
            if "reviewer" in finding:
                assert f"_{finding['reviewer']}_" in md

    def test_persisted_pair_carries_the_same_findings(self, tmp_path: Path) -> None:
        report = _populated_report(scope=_epic_scope())

        json_path, md_path = persist_report(report, cwd=tmp_path)

        payload = json.loads(json_path.read_text(encoding="utf-8"))
        md = md_path.read_text(encoding="utf-8")
        assert len(payload["findings"]) == 3
        for finding in payload["findings"]:
            assert finding["issue"] in md

    def test_severity_counts_agree_with_the_rendered_summary(self) -> None:
        report = _populated_report()

        counts = report.to_dict()["severity_counts"]

        assert counts == {"critical": 1, "major": 1, "minor": 1}
        assert "1 critical, 1 major, 1 minor" in render_markdown(report)
