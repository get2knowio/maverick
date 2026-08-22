"""Unit tests for ``maverick.critique.models``.

Contract: ``specs/058-standalone-code-review/data-model.md`` and
``contracts/critique-report-schema.md``.
"""

from __future__ import annotations

import pytest

from maverick.critique.models import (
    MAX_EMBEDDED_DIFF_CHARS,
    SEVERITY_ORDER,
    CritiqueReport,
    CritiqueScopeKind,
    LensOutcome,
    ResolvedScope,
    ScopedCommit,
    counts_summary,
    order_findings,
    severity_rank,
)
from maverick.payloads import ReviewFindingPayload


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


def _report(
    *,
    scope: ResolvedScope | None = None,
    findings: tuple[ReviewFindingPayload, ...] = (),
    lenses: tuple[LensOutcome, ...] = (),
) -> CritiqueReport:
    return CritiqueReport(
        run_id="a1b2c3d4",
        created_at="2026-08-22T18:04:11.913204+00:00",
        scope=scope or ResolvedScope(kind=CritiqueScopeKind.DIFF, summary="s", paths=("a.py",)),
        lenses=lenses,
        findings=findings,
    )


class TestSeverityOrdering:
    def test_order_is_explicit_not_alphabetical(self) -> None:
        # The values happen to sort alphabetically today; the constant exists
        # so that stays a coincidence rather than a dependency.
        assert SEVERITY_ORDER == ("critical", "major", "minor")
        assert severity_rank("critical") < severity_rank("major") < severity_rank("minor")

    def test_unknown_severity_sorts_last(self) -> None:
        assert severity_rank("cosmetic") == len(SEVERITY_ORDER)
        assert severity_rank("minor") < severity_rank("cosmetic")


class TestOrderFindings:
    def test_orders_by_file_then_severity_then_lens_then_line(self) -> None:
        findings = (
            _finding(file="b.py", severity="minor", line=1),
            _finding(file="a.py", severity="minor", line=5),
            _finding(file="a.py", severity="critical", line=9),
            _finding(file="a.py", severity="critical", line=2, reviewer="completeness"),
        )
        ordered = order_findings(findings)
        assert [(f.file, f.severity, f.reviewer, f.line) for f in ordered] == [
            ("a.py", "critical", "correctness", 9),
            ("a.py", "critical", "completeness", 2),
            ("a.py", "minor", "correctness", 5),
            ("b.py", "minor", "correctness", 1),
        ]

    def test_unattributed_findings_sort_last(self) -> None:
        findings = (_finding(file=""), _finding(file="zzz.py"))
        assert [f.file for f in order_findings(findings)] == ["zzz.py", ""]

    def test_is_stable_for_identical_keys(self) -> None:
        findings = (_finding(issue="alpha"), _finding(issue="beta"))
        assert [f.issue for f in order_findings(findings)] == ["alpha", "beta"]
        # And ordering is idempotent.
        once = order_findings(findings)
        assert order_findings(once) == once


class TestResolvedScope:
    def test_is_empty_when_no_paths_and_no_diff(self) -> None:
        scope = ResolvedScope(kind=CritiqueScopeKind.DIFF, summary="nothing")
        assert scope.is_empty

    def test_is_not_empty_with_paths_only(self) -> None:
        scope = ResolvedScope(kind=CritiqueScopeKind.PATHS, summary="p", paths=("a.py",))
        assert not scope.is_empty

    def test_to_dict_omits_absent_optional_keys(self) -> None:
        data = ResolvedScope(kind=CritiqueScopeKind.PATHS, summary="p", paths=("a.py",)).to_dict()
        assert data == {"kind": "paths", "summary": "p", "paths": ["a.py"]}
        assert "base" not in data
        assert "epic_id" not in data
        assert "commits" not in data

    def test_to_dict_includes_commits_only_for_epic_scope(self) -> None:
        commit = ScopedCommit(sha="9de3a34", subject="bead(mv-1): x", bead_ids=("mv-1",))
        epic = ResolvedScope(
            kind=CritiqueScopeKind.EPIC,
            summary="epic mv-0",
            paths=("a.py",),
            epic_id="mv-0",
            commits=(commit,),
        )
        assert epic.to_dict()["commits"] == [
            {"sha": "9de3a34", "subject": "bead(mv-1): x", "bead_ids": ["mv-1"]}
        ]

    def test_diff_text_is_never_persisted(self) -> None:
        scope = ResolvedScope(
            kind=CritiqueScopeKind.DIFF,
            summary="s",
            paths=("a.py",),
            diff_text="a" * 1000,
            diff_stat="1 file changed",
        )
        assert "diff_text" not in scope.to_dict()
        assert "diff_stat" not in scope.to_dict()


class TestLensOutcome:
    def test_success_projection(self) -> None:
        outcome = LensOutcome(lens="correctness", findings=(_finding(),), approved=False)
        assert outcome.to_dict() == {
            "lens": "correctness",
            "approved": False,
            "finding_count": 1,
        }
        assert not outcome.failed

    def test_failure_projection_carries_no_approval(self) -> None:
        outcome = LensOutcome(lens="completeness", error="timeout after 600s")
        assert outcome.to_dict() == {"lens": "completeness", "error": "timeout after 600s"}
        assert outcome.failed

    def test_approved_none_is_distinct_from_false(self) -> None:
        # "did not approve" and "did not run" are different facts.
        assert LensOutcome(lens="correctness", error="x").approved is None
        assert LensOutcome(lens="correctness", approved=False).approved is False


class TestCritiqueReport:
    def test_reviewed_false_for_empty_scope(self) -> None:
        report = _report(scope=ResolvedScope(kind=CritiqueScopeKind.DIFF, summary="nothing"))
        assert not report.reviewed

    def test_severity_counts_always_have_every_key(self) -> None:
        report = _report(findings=(_finding(severity="major"),))
        assert report.severity_counts == {"critical": 0, "major": 1, "minor": 0}

    def test_severity_counts_ignore_unknown_severities(self) -> None:
        odd = ReviewFindingPayload(severity="major", issue="x", file="a.py")
        report = _report(findings=(odd,))
        assert sum(report.severity_counts.values()) == 1

    @pytest.mark.parametrize(
        ("threshold", "expected"),
        [("critical", True), ("major", True), ("minor", True)],
    )
    def test_exceeds_is_at_or_above(self, threshold: str, expected: bool) -> None:
        report = _report(findings=(_finding(severity="critical"),))
        assert report.exceeds(threshold) is expected

    def test_exceeds_false_when_below_threshold(self) -> None:
        report = _report(findings=(_finding(severity="minor"),))
        assert report.exceeds("critical") is False
        assert report.exceeds("major") is False
        assert report.exceeds("minor") is True

    def test_lens_failures(self) -> None:
        lenses = (
            LensOutcome(lens="correctness", approved=True),
            LensOutcome(lens="completeness", error="boom"),
        )
        assert [lens.lens for lens in _report(lenses=lenses).lens_failures] == ["completeness"]

    def test_findings_by_file_groups_in_canonical_order(self) -> None:
        findings = order_findings(
            (
                _finding(file="b.py", severity="minor"),
                _finding(file="a.py", severity="critical"),
                _finding(file="a.py", severity="major"),
            )
        )
        groups = list(_report(findings=findings).findings_by_file())
        assert [name for name, _ in groups] == ["a.py", "b.py"]
        assert [f.severity for f in groups[0][1]] == ["critical", "major"]

    def test_to_dict_schema_version_is_first_key(self) -> None:
        data = _report().to_dict()
        assert next(iter(data)) == "schema_version"
        assert data["schema_version"] == 1

    def test_to_dict_omits_line_when_unknown(self) -> None:
        data = _report(findings=(_finding(line=None),)).to_dict()
        assert "line" not in data["findings"][0]

    def test_to_dict_enumerates_exactly_the_contract_keys(self) -> None:
        data = _report(findings=(_finding(line=7),)).to_dict()
        assert set(data["findings"][0]) == {"severity", "issue", "file", "line", "reviewer"}

    def test_truncated_mirrors_the_scope(self) -> None:
        scope = ResolvedScope(
            kind=CritiqueScopeKind.DIFF,
            summary="s",
            paths=("a.py",),
            diff_text="x",
            diff_truncated=True,
        )
        assert _report(scope=scope).truncated is True


class TestConstants:
    def test_embedded_diff_budget_is_bounded(self) -> None:
        assert MAX_EMBEDDED_DIFF_CHARS == 200_000


class TestCountsSummary:
    def test_renders_every_severity(self) -> None:
        assert counts_summary({"critical": 1, "major": 2, "minor": 0}) == (
            "1 critical, 2 major, 0 minor"
        )

    def test_missing_keys_render_as_zero(self) -> None:
        assert counts_summary({}) == "0 critical, 0 major, 0 minor"
