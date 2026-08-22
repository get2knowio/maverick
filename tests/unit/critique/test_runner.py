"""Unit tests for :mod:`maverick.critique.runner`.

Contracts: ``specs/058-standalone-code-review/contracts/cli-critique.md`` and
``contracts/critique-report-schema.md``.

The load-bearing assertion in this file is
:meth:`TestEmptyScope.test_empty_scope_never_constructs_a_squadron`: it
replaces ``CritiqueSquadron`` with a callable that raises, which is the only
way to *prove* FR-009/SC-004's "an empty scope costs zero model calls" rather
than assert it about a mock that was never checked.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest

from maverick.config import MaverickConfig
from maverick.critique.models import (
    LENS_ORDER,
    CritiqueScopeKind,
    ResolvedScope,
)
from maverick.critique.runner import (
    AllLensesFailedError,
    build_change_summary,
    run_critique,
)
from maverick.payloads import ReviewFindingPayload, SubmitReviewPayload

if TYPE_CHECKING:
    from pathlib import Path

RUN_ID = "a1b2c3d4"


def _finding(
    *,
    severity: str = "major",
    issue: str = "something",
    file: str = "a.py",
    line: int | None = None,
    reviewer: str = "correctness",
) -> ReviewFindingPayload:
    return ReviewFindingPayload(
        severity=severity,  # type: ignore[arg-type]
        issue=issue,
        file=file,
        line=line,
        reviewer=reviewer,  # type: ignore[arg-type]
    )


def _payload(
    *findings: ReviewFindingPayload,
    approved: bool | None = None,
) -> SubmitReviewPayload:
    return SubmitReviewPayload(
        approved=not findings if approved is None else approved,
        findings=findings,
    )


def _scope(
    *,
    kind: CritiqueScopeKind = CritiqueScopeKind.DIFF,
    summary: str = "working copy vs main",
    paths: tuple[str, ...] = ("a.py", "b.py"),
    diff_text: str = "diff --git a/a.py b/a.py",
    diff_truncated: bool = False,
    diff_stat: str = " a.py | 2 +1 -1",
) -> ResolvedScope:
    return ResolvedScope(
        kind=kind,
        summary=summary,
        paths=paths,
        diff_text=diff_text,
        diff_truncated=diff_truncated,
        diff_stat=diff_stat,
    )


class _FakeReviewer:
    """One lens: a ``critique()`` that answers with a payload or raises.

    Mirrors ``tests/unit/agents/airframe_stubs.py``'s stub style — canned
    responses and a call log — but stays local because the runner only ever
    touches the single ``critique`` method.
    """

    def __init__(
        self,
        *,
        payload: SubmitReviewPayload | None = None,
        error: BaseException | None = None,
        delay: float = 0.0,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._payload = payload
        self._error = error
        self._delay = delay
        self.critique = self._critique

    async def _critique(self, **kwargs: Any) -> SubmitReviewPayload:
        self.calls.append(kwargs)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._error is not None:
            raise self._error
        assert self._payload is not None
        return self._payload


def _install_squadron(
    monkeypatch: pytest.MonkeyPatch,
    *,
    correctness: _FakeReviewer,
    completeness: _FakeReviewer,
) -> dict[str, Any]:
    """Patch the runner's ``CritiqueSquadron`` with an async-context fake.

    Returns a record dict so a test can assert the squadron was constructed
    with the threaded ``cwd``/``config`` and was closed on the way out.
    """
    record: dict[str, Any] = {"kwargs": None, "entered": 0, "exited": 0}

    class _FakeSquadron:
        correctness_reviewer = correctness
        completeness_reviewer = completeness

        def __init__(self, **kwargs: Any) -> None:
            record["kwargs"] = kwargs

        async def __aenter__(self) -> _FakeSquadron:
            record["entered"] += 1
            return self

        async def __aexit__(self, *exc_info: object) -> bool:
            record["exited"] += 1
            return False

    monkeypatch.setattr("maverick.critique.runner.CritiqueSquadron", _FakeSquadron)
    return record


async def _run(scope: ResolvedScope, *, cwd: Path) -> Any:
    return await run_critique(
        cwd=cwd,
        config=MaverickConfig(),
        scope=scope,
        run_id=RUN_ID,
    )


class TestBothLenses:
    async def test_findings_from_both_lenses_are_unioned_in_canonical_order(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        correctness = _FakeReviewer(
            payload=_payload(
                _finding(file="b.py", severity="minor", issue="c-b-minor", line=3),
                _finding(file="a.py", severity="critical", issue="c-a-crit", line=7),
            )
        )
        completeness = _FakeReviewer(
            payload=_payload(
                _finding(
                    file="a.py",
                    severity="critical",
                    issue="p-a-crit",
                    line=1,
                    reviewer="completeness",
                ),
            )
        )
        record = _install_squadron(monkeypatch, correctness=correctness, completeness=completeness)

        report = await _run(_scope(), cwd=tmp_path)

        # File ascending, then severity, then lens, then line — the one order
        # the terminal, the markdown, and the JSON all share.
        assert [(f.file, f.severity, f.reviewer) for f in report.findings] == [
            ("a.py", "critical", "correctness"),
            ("a.py", "critical", "completeness"),
            ("b.py", "minor", "correctness"),
        ]
        assert record["entered"] == 1
        assert record["exited"] == 1

    async def test_findings_are_the_payload_objects_not_copies(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """SC-003: critique reports the same payload type fly produces.

        Identity, not just equality — a parallel finding type or a defensive
        copy would satisfy equality while quietly forking the projection the
        artifact and the ``--json`` envelope share.
        """
        c_finding = _finding(file="a.py", issue="correctness finding")
        p_finding = _finding(file="b.py", issue="completeness finding", reviewer="completeness")
        c_payload = _payload(c_finding)
        p_payload = _payload(p_finding)
        _install_squadron(
            monkeypatch,
            correctness=_FakeReviewer(payload=c_payload),
            completeness=_FakeReviewer(payload=p_payload),
        )

        report = await _run(_scope(), cwd=tmp_path)

        assert all(isinstance(f, ReviewFindingPayload) for f in report.findings)
        assert report.findings[0] is c_payload.findings[0]
        assert report.findings[1] is p_payload.findings[0]
        # And the per-lens outcomes carry the very same objects.
        by_lens = {outcome.lens: outcome for outcome in report.lenses}
        assert by_lens["correctness"].findings[0] is c_finding
        assert by_lens["completeness"].findings[0] is p_finding

    async def test_lenses_carry_approval_and_the_squadron_gets_the_threaded_cwd(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        config = MaverickConfig()
        record = _install_squadron(
            monkeypatch,
            correctness=_FakeReviewer(payload=_payload(_finding(), approved=False)),
            completeness=_FakeReviewer(payload=_payload(approved=True)),
        )

        report = await run_critique(cwd=tmp_path, config=config, scope=_scope(), run_id=RUN_ID)

        assert record["kwargs"] == {"cwd": tmp_path, "config": config}
        assert report.run_id == RUN_ID
        assert report.reviewed is True
        by_lens = {outcome.lens: outcome for outcome in report.lenses}
        assert by_lens["correctness"].approved is False
        assert by_lens["completeness"].approved is True
        assert report.lens_failures == ()

    async def test_each_lens_receives_the_scope_summary_and_change_summary(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        correctness = _FakeReviewer(payload=_payload())
        completeness = _FakeReviewer(payload=_payload())
        _install_squadron(monkeypatch, correctness=correctness, completeness=completeness)
        scope = _scope(summary="epic mv-0041 (3 commits)")

        await _run(scope, cwd=tmp_path)

        expected = {
            "scope_summary": "epic mv-0041 (3 commits)",
            "change_summary": build_change_summary(scope),
        }
        assert correctness.calls == [expected]
        assert completeness.calls == [expected]

    async def test_lenses_are_in_lens_order_regardless_of_completion_order(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Completeness finishes first; the report still leads with correctness.

        The persisted artifact must be byte-stable across runs, so the array
        order comes from :data:`LENS_ORDER`, never from whichever adapter
        happened to answer first.
        """
        _install_squadron(
            monkeypatch,
            correctness=_FakeReviewer(payload=_payload(), delay=0.02),
            completeness=_FakeReviewer(payload=_payload()),
        )

        report = await _run(_scope(), cwd=tmp_path)

        assert tuple(outcome.lens for outcome in report.lenses) == LENS_ORDER


class TestEmptyScope:
    async def test_empty_scope_never_constructs_a_squadron(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """FR-009 / SC-004: an empty scope costs zero model calls.

        The guarantee is structural — the short-circuit returns *before* the
        squadron is built — so the test makes construction itself fatal.
        """

        def _explode(**kwargs: Any) -> Any:
            raise AssertionError("an empty scope must never construct a squadron")

        monkeypatch.setattr("maverick.critique.runner.CritiqueSquadron", _explode)
        empty = ResolvedScope(
            kind=CritiqueScopeKind.DIFF,
            summary="working copy vs main",
        )
        assert empty.is_empty is True

        report = await _run(empty, cwd=tmp_path)

        assert report.reviewed is False
        assert report.lenses == ()
        assert report.findings == ()
        assert report.run_id == RUN_ID

    async def test_the_short_circuit_guard_is_reachable(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Negative control for the test above.

        Without this, a runner that never constructed a squadron at all —
        or a patch target that silently stopped matching — would pass the
        zero-model-call assertion vacuously.
        """

        def _explode(**kwargs: Any) -> Any:
            raise AssertionError("constructed")

        monkeypatch.setattr("maverick.critique.runner.CritiqueSquadron", _explode)

        with pytest.raises(AssertionError, match="constructed"):
            await _run(_scope(), cwd=tmp_path)

    async def test_paths_alone_are_enough_to_run(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """A ``--paths`` scope has no diff at all and still must be reviewed."""
        _install_squadron(
            monkeypatch,
            correctness=_FakeReviewer(payload=_payload()),
            completeness=_FakeReviewer(payload=_payload()),
        )
        scope = ResolvedScope(
            kind=CritiqueScopeKind.PATHS,
            summary="paths: src/",
            paths=("src/",),
        )

        report = await _run(scope, cwd=tmp_path)

        assert report.reviewed is True
        assert len(report.lenses) == 2


class TestLensFailure:
    async def test_one_lens_failing_degrades_to_a_recorded_outcome(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """FR-011: one lens failing is a warning, never an exception."""
        survivor = _finding(file="a.py", issue="still reported", reviewer="completeness")
        _install_squadron(
            monkeypatch,
            correctness=_FakeReviewer(error=RuntimeError("provider exploded")),
            completeness=_FakeReviewer(payload=_payload(survivor)),
        )

        report = await _run(_scope(), cwd=tmp_path)

        failed, ok = report.lenses
        assert failed.lens == "correctness"
        assert failed.error == "provider exploded"
        assert failed.approved is None  # "did not run" ≠ "did not approve"
        assert failed.findings == ()
        assert failed.failed is True
        assert ok.lens == "completeness"
        assert ok.failed is False
        # The survivor's findings are untouched by its sibling's failure.
        assert report.findings == (survivor,)
        assert report.lens_failures == (failed,)

    async def test_lens_failure_catches_arbitrary_exception_types(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """The degrade promise cannot depend on enumerating adapter errors."""
        _install_squadron(
            monkeypatch,
            correctness=_FakeReviewer(payload=_payload()),
            completeness=_FakeReviewer(error=ValueError("malformed structured output")),
        )

        report = await _run(_scope(), cwd=tmp_path)

        assert report.lens_failures[0].error == "malformed structured output"

    async def test_both_lenses_failing_raises_and_names_both_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        _install_squadron(
            monkeypatch,
            correctness=_FakeReviewer(error=RuntimeError("first boom")),
            completeness=_FakeReviewer(error=RuntimeError("second boom")),
        )

        with pytest.raises(AllLensesFailedError) as excinfo:
            await _run(_scope(), cwd=tmp_path)

        message = str(excinfo.value)
        assert "correctness: first boom" in message
        assert "completeness: second boom" in message


class TestBuildChangeSummary:
    def test_file_list_comes_before_the_diff(self) -> None:
        """The truncatable part goes last, so a cut prompt keeps the extent."""
        summary = build_change_summary(_scope())

        files_at = summary.index("## Files in scope")
        stat_at = summary.index("## Diff stat")
        diff_at = summary.index("## Diff\n")
        assert files_at < stat_at < diff_at

    def test_file_list_is_complete_and_counted(self) -> None:
        summary = build_change_summary(_scope(paths=("a.py", "b.py", "c.py")))

        assert "## Files in scope (3)" in summary
        for path in ("- a.py", "- b.py", "- c.py"):
            assert path in summary

    def test_truncation_note_only_appears_when_truncated(self) -> None:
        note = "Diff truncated at the embedding budget"

        assert note not in build_change_summary(_scope())
        assert note in build_change_summary(_scope(diff_truncated=True))

    def test_truncation_note_is_absent_when_there_is_no_diff_section(self) -> None:
        # A truncated flag with no diff text can't produce a dangling note.
        summary = build_change_summary(_scope(diff_text="", diff_truncated=True))

        assert "Diff truncated" not in summary

    def test_sections_are_omitted_when_their_data_is_absent(self) -> None:
        paths_only = build_change_summary(_scope(diff_text="", diff_stat="", paths=("src/",)))
        assert "## Files in scope (1)" in paths_only
        assert "## Diff stat" not in paths_only
        assert "## Diff" not in paths_only

        diff_only = build_change_summary(_scope(paths=(), diff_stat=""))
        assert "## Files in scope" not in diff_only
        assert "## Diff stat" not in diff_only
        assert "## Diff" in diff_only

    def test_empty_scope_summarizes_to_nothing(self) -> None:
        assert build_change_summary(ResolvedScope(kind=CritiqueScopeKind.DIFF, summary="s")) == ""
