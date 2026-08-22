"""Terminal rendering for ``maverick critique``.

Contract: ``specs/058-standalone-code-review/contracts/cli-critique.md``.

The console is injected rather than imported so ``--json`` mode can redirect
every line to ``err_console`` — stdout carries exactly one JSON document
there (SC-005).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.markup import escape

from maverick.critique.models import counts_summary

if TYPE_CHECKING:
    from pathlib import Path

    from rich.console import Console

    from maverick.critique.models import CritiqueReport

__all__ = ["render_report"]

#: Rich style per severity. Keyed by the contract's three values; an unknown
#: severity renders unstyled rather than crashing the report that carries it.
_SEVERITY_STYLE = {
    "critical": "red",
    "major": "yellow",
    "minor": "dim",
}

#: Heading for findings the reviewer could not attribute to a file.
_UNATTRIBUTED = "(unattributed)"


def render_report(
    report: CritiqueReport,
    *,
    console: Console,
    artifact_path: Path | None = None,
) -> None:
    """Render *report* in the fixed section order the contract specifies.

    Args:
        report: The completed critique.
        console: Where to write. ``err_console`` in ``--json`` mode.
        artifact_path: The persisted markdown report, when it was written.
    """
    _render_scope_line(report, console=console)
    if not report.reviewed:
        return

    _render_truncation(report, console=console)
    _render_lens_failures(report, console=console)
    _render_findings(report, console=console)
    _render_summary(report, console=console)
    _render_artifact(report, console=console, artifact_path=artifact_path)


def _render_scope_line(report: CritiqueReport, *, console: Console) -> None:
    """The scope line, or the "nothing to review" outcome (FR-016, FR-019).

    These two are deliberately different sentences. A user must never have to
    guess whether the reviewer was silent or absent.
    """
    if not report.reviewed:
        console.print(f"Nothing to review — {escape(report.scope.summary)} is empty.")
        return
    count = len(report.scope.paths)
    plural = "" if count == 1 else "s"
    console.print(f"Reviewing {escape(report.scope.summary)} — {count} file{plural}")
    console.print()


def _render_truncation(report: CritiqueReport, *, console: Console) -> None:
    if not report.truncated:
        return
    console.print(
        "[yellow]Warning:[/yellow] diff exceeded the embedding budget; the "
        "reviewer was given the complete file list and read the remainder "
        "directly."
    )
    console.print()


def _render_lens_failures(report: CritiqueReport, *, console: Console) -> None:
    failures = report.lens_failures
    if not failures:
        return
    survivors = [lens.lens for lens in report.lenses if not lens.failed]
    for lens in failures:
        console.print(
            f"[yellow]Warning:[/yellow] the {lens.lens} lens failed "
            f"({escape(lens.error or 'unknown error')})."
        )
    if survivors:
        joined = " and ".join(survivors)
        console.print(f"Findings below are from the {joined} lens only.")
    console.print()


def _render_findings(report: CritiqueReport, *, console: Console) -> None:
    if not report.findings:
        console.print("No findings.")
        console.print()
        return

    for name, findings in report.findings_by_file():
        console.print(f"[bold]{escape(name or _UNATTRIBUTED)}[/bold]")
        for finding in findings:
            style = _SEVERITY_STYLE.get(finding.severity)
            severity = (
                f"[{style}]{finding.severity}[/{style}]" if style else escape(finding.severity)
            )
            location = f"L{finding.line}" if finding.line is not None else "—"
            lens = f"({finding.reviewer})" if finding.reviewer else ""
            console.print(f"  {severity}  {location}  {lens}  {escape(finding.issue)}")
        console.print()


def _render_summary(report: CritiqueReport, *, console: Console) -> None:
    total = len(report.findings)
    if total == 0:
        return
    plural = "" if total == 1 else "s"
    console.print(f"{total} finding{plural} — {counts_summary(report.severity_counts)}")


def _render_artifact(
    report: CritiqueReport,
    *,
    console: Console,
    artifact_path: Path | None,
) -> None:
    if report.degraded_persistence:
        console.print(
            "[yellow]Warning:[/yellow] the findings artifact could not be "
            "written; the findings above are complete."
        )
        return
    if artifact_path is not None:
        console.print(f"Report: {escape(str(artifact_path))}")
